# Which Particles Appear in EDM4hep MCParticles

When you run ddsim, Geant4 simulates every particle and interaction. But not
everything is written to the output. The MCParticles collection contains only
a filtered subset. These are the effective rules.

## The tracking cylinder

A virtual cylinder defined in the epic geometry controls most of the filtering.
It is NOT a physical detector — it's a filtering boundary for MC truth recording.

- Forward:  z_max = +335 cm  (EcalEndcapP_zmin)
- Backward: z_min = -175 cm  (EcalEndcapN_zmin)
- Radial:   r_max =  ~82 cm  (EcalBarrel_rmin)

The B0 tracker sits at z = 630 cm — almost twice the forward boundary.

## What IS saved

- **All primary particles** from the event generator — always, unconditionally
- **Decay products born inside the cylinder** with kinetic energy > 1 MeV,
  provided their parent is also above 1 MeV
- **Particles that created a hit in a tracker-type sensitive detector** AND are
  above 1 MeV — even if born outside the cylinder, as long as they end inside it

## What is NOT saved

- **Any non-primary particle born AND ending outside the cylinder** — dropped
  regardless of energy, regardless of being a decay product, **regardless of
  calorimeter hits**. A gamma hitting B0 ECal, a neutron hitting ZDC — if they
  were born outside the cylinder, they are dropped. Calorimeter hits have zero
  influence on the save decision; only tracker hits count.
- **Low-energy particles** (KE < 1 MeV) born inside the cylinder
- **Particles born outside the cylinder that enter it** — dropped unless they
  created a hit in a tracker-type sensitive detector

## What happens to dropped particles

When a particle is dropped from the record:
- Its children get **reparented** to the nearest surviving ancestor
- Its flags (hit information) are **merged** into the parent's flags

Example: if pi0 is dropped but its gammas survive, the gammas become direct
daughters of the Lambda in the output. But if pi0 is dropped and the
parent-daughter bookkeeping is not updated (see v01-35 bug below), the gammas
may become **orphaned** — present in the MCParticles collection but with no
parent link to Lambda.

## Consequences for Lambda decay

**Lambda → p + pi-** (63.9% BR):
- Both are long-lived and charged, create tracker hits → saved if born inside cylinder
- Pi- lifetime is 26 ns — it typically travels meters before decaying. Its decay
  products (mu, nu) are born far outside the cylinder, get dropped by the filter,
  and never interfere with pi- being saved

**Lambda → n + pi0** (35.8% BR):
- Neutron: above threshold, has "Decay" process tag → saved if born inside cylinder
- Pi0: always removed — see v01-35 bug below
- Gammas from pi0: above threshold, have "Decay" process tag → saved if born inside
  cylinder, but may be orphaned (parent pi0 was removed, link to Lambda is broken)

**Any decay outside the cylinder** (z > 335 cm):
- ALL daughters are dropped — neutron, pi0, gammas, proton, pi-, everything
- Lambda appears in MCParticles with zero daughters ("undecayed")
- This affects roughly half of all Lambdas in the simulation

## Why pi0 is always removed (v01-35 bug)

DD4hep v01-35 (the current Docker image version) has a bug in the end-of-event
cleanup function `recombineParents`. Two problems combine:

**Bug 1: unconditional removal.** When user particle handlers are present (which
they always are — `Geant4TCUserParticleHandler` is the default), ALL non-primary
particles are unconditionally marked for removal. Only particles that hit a
specific escape path (PRIMARY, KEEP_ALWAYS, KEEP_USER, or KEEP_PROCESS with an
energetic parent) survive.

**Bug 2: KEEP_PARENT masks KEEP_PROCESS.** The code checks particle flags in an
`if / else if` chain. KEEP_PARENT is checked BEFORE KEEP_PROCESS, but its
`continue` (which would save the particle) is **commented out**. So if a particle
has both flags, KEEP_PARENT matches first, does nothing, and KEEP_PROCESS is
never reached. The particle is removed.

**Why this specifically kills pi0:**

The cleanup runs in reverse track-ID order (latest particles first):
1. Gammas (from pi0 → γγ) are processed first. They have the "Decay" process
   tag, their parent (pi0) is above threshold → gammas are saved. As a
   side-effect, KEEP_PARENT is set on pi0.
2. Pi0 is processed next. It has BOTH KEEP_PARENT (just set) AND KEEP_PROCESS
   (from "Decay"). KEEP_PARENT matches first → does nothing → KEEP_PROCESS
   never reached → pi0 is removed.
3. Neutron is processed. It only has KEEP_PROCESS (no KEEP_PARENT, because
   neutron's children are from hadronic interactions, not "Decay") →
   KEEP_PROCESS fires → neutron is saved.

**Why pi- from p+pi- is NOT affected:** pi- is long-lived and typically does
not decay inside the tracking cylinder. Its hadronic interaction products don't
carry the "Decay" tag, so KEEP_PARENT is never set on pi-. It reaches the
KEEP_PROCESS branch and is saved.

**This bug was fixed** in DD4hep commit `1dc80f87` (2026-02-23), which is NOT
included in v01-35. The fix initializes the removal flag to false instead of
unconditionally setting it to true.

## Two independent problems for Lambda decays

There are TWO separate filtering problems. Fixing the v01-35 bug solves only one.

### Problem 1: v01-35 KEEP_PARENT bug (inside tracker)

Affects pi0 from decays that happen INSIDE the tracking cylinder (z < 335 cm).
Fixed in DD4hep commit `1dc80f87`. Not included in v01-35.

### Problem 2: Tracking cylinder boundary (outside tracker)

Affects ALL decay products from decays that happen OUTSIDE the tracking cylinder
(z > 335 cm). Not fixed by any existing commit. Would require changing `setReason()`
to also check `G4PARTICLE_CREATED_CALORIMETER_HIT`, or extending the cylinder.

## Comparison: v01-35 vs fixed DD4hep

### Lambda → p + pi- (inside tracker, z < 335 cm)

| Particle | v01-35 | Fixed | Why |
|---|---|---|---|
| proton | Saved | Saved | Tracker hits → KEEP_PROCESS works in both |
| pi- | Saved | Saved | Tracker hits → KEEP_PROCESS works in both |

No difference — this channel works correctly in both versions.

### Lambda → n + pi0 (inside tracker, z < 335 cm)

| Particle | v01-35 | Fixed | Why |
|---|---|---|---|
| neutron | Saved | Saved | Only has KEEP_PROCESS (no KEEP_PARENT) → survives in both |
| pi0 | **Dropped** | **Saved** | v01-35: KEEP_PARENT masks KEEP_PROCESS → removed. Fixed: remove_me=false from dropParticle → survives |
| gammas | Saved | Saved | KEEP_PROCESS fires before KEEP_PARENT is set on them |

The fix restores pi0 for this case. Gammas may be orphaned in v01-35 (parent pi0
removed, link to Lambda broken); in fixed version, parent chain is intact.

### Lambda → anything (outside tracker, z > 335 cm)

| Particle | v01-35 | Fixed | Why |
|---|---|---|---|
| ALL daughters | **Dropped** | **Dropped** | setReason zeros reason for all non-primary particles born+ending outside cylinder |
| Lambda itself | Appears with 0 daughters | Appears with 0 daughters | Lambda is primary → always saved, but looks "undecayed" |

**The fix changes nothing here.** `setReason()` runs before `recombineParents()`
and zeroes the reason for every daughter. They never enter the particle map, so
`recombineParents()` never sees them. The KEEP_PARENT bug is irrelevant — these
particles are killed at the earlier `setReason` stage.

### Summary of what each fix addresses

| Decay location | v01-35 bug fix | setReason/cylinder fix |
|---|---|---|
| Inside tracker (z < 335 cm) | Restores pi0 in n+pi0 channel | Not needed |
| Outside tracker (z > 335 cm) | Does nothing | Required — would need code change |

**Bottom line:** upgrading DD4hep fixes the n+pi0 channel for ~half of Lambda
decays (those inside the cylinder). The other ~half (outside the cylinder,
including everything near B0 at z=630 cm) remain invisible regardless of DD4hep
version. Fixing that requires either extending the tracking cylinder or modifying
`setReason()` to account for calorimeter hits.

## Configuration options

| Option | Default | Effect |
|---|---|---|
| `SIM.part.keepAllParticles` | False | If True, saves every particle (huge files) |
| `SIM.part.saveProcesses` | ["Decay"] | Which creator processes get the keep tag |
| `SIM.part.minimalKineticEnergy` | 1 MeV | Energy threshold for secondary particles |
| `SIM.part.userParticleHandler` | "Geant4TCUserParticleHandler" | The tracking cylinder filter |

## Detector hits vs MCParticles — what IS always saved

This is a critical distinction. The MCParticle filtering described above does NOT
affect detector hits. Two completely separate things are written to the output:

**SimCalorimeterHits / SimTrackerHits** — ALWAYS saved. Every energy deposit in
every sensitive detector is written, regardless of whether the particle that caused
it survives in MCParticles. A neutron hitting ZDC, a gamma hitting B0 ECal — the
hits exist in the output with correct energy, position, and time.

**MCParticles** — filtered as described above. Only a subset of simulated particles
is kept.

**The link between them:** every hit carries a reference to an MCParticle. When the
particle that actually created the hit is dropped from MCParticles, the link is
**remapped to the nearest surviving ancestor**. For example:

- Lambda (primary) → n + pi0 → gammas hit B0 ECal
- If decay is outside the cylinder: neutron, pi0, gammas all dropped
- The B0 ECal hits exist, but their MCParticle link points to Lambda
- Reconstruction works (uses hit energy/position), but truth-matching is degraded

This is why Lambda reconstruction in ZDC has always worked — it uses the calorimeter
hits, not MCParticles. The issue in epic#1069 is about MC truth validation: you
cannot verify reconstructed Lambdas against their true decay products because those
products are missing from MCParticles.

## Key file locations

| What | Where |
|---|---|
| Tracking cylinder filter | `DD4hep/DDG4/plugins/Geant4UserParticleHandlerHelper.cpp` |
| Cylinder geometry check | `DD4hep/DDG4/plugins/Geant4TCUserParticleHandler.cpp` |
| Main handler (begin/step/end/recombine) | `DD4hep/DDG4/src/Geant4ParticleHandler.cpp` |
| Cylinder boundaries | `epic/compact/definitions.xml` (tracker_region_zmax/zmin/rmax) |
| Configuration defaults | `DD4hep/DDG4/python/DDSim/Helper/ParticleHandler.py` |
| EDM4hep output writer | `DD4hep/DDG4/edm4hep/Geant4Output2EDM4hep.cpp` |
