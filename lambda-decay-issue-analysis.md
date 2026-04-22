# Lambda Decay Issue Analysis (epic#1069)

## Problem Statement

Two issues with Lambda (PDG 3122) MC truth in EIC simulations:

1. **Lambda decays appear only before B0 detector** (~6.3m from IP), while physics says
   they should decay everywhere along their flight path.
2. **Missing pi0 in Lambda -> n + pi0 decay mode** -- only the neutron is saved in
   MCParticles, the pi0 is absent.

---

## Observed Data (from plots)

| Metric | Value | Notes |
|---|---|---|
| Total Lambda | 5004 | 100% |
| Decayed (has daughters) | 2448 | 48.9% -- other 51.1% appear undecayed |
| p + pi- | 1560 | 31.2% of total, **63.7% of decayed** (PDG: 63.9%) |
| n + pi0 | **0** | **0.0%** -- completely missing |
| Other Decays | 888 | 17.7% of total, **36.3% of decayed** (PDG for n+pi0: 35.8%) |
| Decay z mean | 1483 mm | |
| Decay z cutoff | ~3500 mm | Matches tracker_region_zmax = 3350 mm |

**Key observations:**
- The 888 "Other" events match the n+pi0 branching ratio perfectly (36.3% vs 35.8%)
  -> Geant4 IS producing n+pi0 correctly, but pi0 is always dropped
- The z distribution hard cutoff at ~3350 mm matches tracker_region_zmax exactly
  -> Decays beyond this boundary are invisible in MC truth
- 51.1% of Lambdas appear undecayed -> their decays happened outside the tracker cylinder

---

## Key Geometry Numbers

| Quantity | Value | Source |
|---|---|---|
| tracker_region_zmax | **+335 cm** (EcalEndcapP_zmin) | `epic/compact/definitions.xml:734` |
| tracker_region_zmin | **-175 cm** (EcalEndcapN_zmin) | `epic/compact/definitions.xml:735` |
| tracker_region_rmax | **~82 cm** (EcalBarrel_rmin) | `epic/compact/definitions.xml:733` |
| B0 Tracker center z | **630 cm** | `epic/compact/far_forward/B0_tracker.xml:17` |
| B0 ECal center z | **702 cm** | `epic/compact/far_forward/B0_ECal.xml` |
| World volume | **+/-15 m** | `epic/compact/definitions.xml:12` |

**The B0 is at z=630 cm, nearly twice the tracker_region_zmax of 335 cm.**

Calculation chain for tracker_region_zmax:
```
CentralTrackingRegionP_zmax = 1800 mm = 180 cm
ForwardPIDRegion_length = 135 cm
ForwardTrackingRegion_length = 0 cm
ForwardInnerEndcapRegion_length = 135 + 0 = 135 cm
ForwardInnerEndcapRegionExtraSpace_length = 4.6 cm
ForwardServiceGap_zmin = 180 + 135 + 4.6 = 319.6 cm
ForwardServiceGap_length = 15.4 cm
ForwardServiceGap_zmax = 335.0 cm
EcalEndcapP_zmin = ForwardServiceGap_zmax = 335.0 cm
tracker_region_zmax = EcalEndcapP_zmin = 335.0 cm
```

---

## Exact Particle Lifecycle: How Geant4 Sets Flags and DD4hep Writes Particles

There are two separate data structures on each particle:
- `reason` field (type `int`, bitmask) -- used for FILTERING decisions
- `status` field (type `int`, bitmask) -- used for SIMULATION STATUS in EDM4hep output

### All Flag Definitions

**Reason flags** (`Geant4Particle.h:56-68`) -- govern keep/drop decisions:
```
Bit  Flag                              Hex     Meaning
1    G4PARTICLE_CREATED_HIT            0x002   Particle created any hit in a sensitive detector
2    G4PARTICLE_PRIMARY                0x004   Primary particle from generator
3    G4PARTICLE_HAS_SECONDARIES        0x008   Produced secondary particles
4    G4PARTICLE_ABOVE_ENERGY_THRESHOLD 0x010   KE > minimalKineticEnergy (default 1 MeV)
5    G4PARTICLE_KEEP_PROCESS           0x020   Created by a "saved" process (default: "Decay")
6    G4PARTICLE_KEEP_PARENT            0x040   Parent of a kept particle
7    G4PARTICLE_CREATED_CALORIMETER_HIT 0x080  Hit in a calorimeter sensitive detector
8    G4PARTICLE_CREATED_TRACKER_HIT    0x100   Hit in a tracker sensitive detector
9    G4PARTICLE_KEEP_USER              0x200   User forced keep
10   G4PARTICLE_KEEP_ALWAYS            0x400   Always keep (backscatter, keepAll)
11   G4PARTICLE_FORCE_KILL             0x800   Force remove
12   G4PARTICLE_STARTED_IN_CALORIMETER 0x1000  Track started in calorimeter volume
```

**Status flags** (`Geant4Particle.h:86-93`) -- written to EDM4hep MCParticle:
```
Bit  Flag                           Meaning
10   G4PARTICLE_SIM_CREATED          Created by simulation (not generator)
11   G4PARTICLE_SIM_BACKSCATTER      Backscattered from calo to tracker
12   G4PARTICLE_SIM_DECAY_CALO       Decayed/interacted in calorimeter region
13   G4PARTICLE_SIM_DECAY_TRACKER    Decayed/interacted in tracking region
14   G4PARTICLE_SIM_STOPPED          Kinetic energy reached zero
15   G4PARTICLE_SIM_LEFT_DETECTOR    Left world volume undecayed
16   G4PARTICLE_SIM_PARENT_RADIATED  Vertex not at parent's endpoint
```

### Phase 1: Pre-Track (`Geant4ParticleHandler::begin`)

File: `DD4hep/DDG4/src/Geant4ParticleHandler.cpp:211-327`

Called when Geant4 starts tracking a new particle. Sets initial reason flags.

```
For each new G4Track:

1. Check if PRIMARY (from generator):
   YES -> reason |= G4PARTICLE_PRIMARY | G4PARTICLE_ABOVE_ENERGY_THRESHOLD
          Store in particleMap immediately
   NO  -> reason = (KE > 1 MeV) ? G4PARTICLE_ABOVE_ENERGY_THRESHOLD : 0
          status = G4PARTICLE_SIM_CREATED

2. Check creator process name against saveProcesses list (default: ["Decay"]):
   Match -> reason |= G4PARTICLE_KEEP_PROCESS

3. If keepAllParticles == true:
   reason |= G4PARTICLE_KEEP_ALWAYS

4. Check if track starts in a calorimeter sensitive detector:
   YES -> reason |= G4PARTICLE_STARTED_IN_CALORIMETER

5. Record: production vertex (vsx,vsy,vsz), momentum (psx,psy,psz),
   g4Parent track ID, creator process pointer, global time
```

**Example -- neutron from Lambda -> n + pi0 decay:**
```
reason = G4PARTICLE_ABOVE_ENERGY_THRESHOLD | G4PARTICLE_KEEP_PROCESS
       = 0x010 | 0x020 = 0x030
status = G4PARTICLE_SIM_CREATED = 0x400
```

**Example -- pi0 from Lambda -> n + pi0 decay:**
```
reason = G4PARTICLE_ABOVE_ENERGY_THRESHOLD | G4PARTICLE_KEEP_PROCESS
       = 0x010 | 0x020 = 0x030  (identical to neutron)
status = G4PARTICLE_SIM_CREATED = 0x400
```

### Phase 2: Stepping (`Geant4ParticleHandler::step`)

File: `DD4hep/DDG4/src/Geant4ParticleHandler.cpp:191-208`

Called for every Geant4 step. Updates flags based on what happens during tracking.

```
For each step:
  steps++
  IF reason has ABOVE_ENERGY_THRESHOLD:
    IF step produced secondaries:
      reason |= G4PARTICLE_HAS_SECONDARIES
```

The `mark()` function (called by sensitive detectors when a hit is created):
```
File: Geant4ParticleHandler.cpp:148-174

  reason |= G4PARTICLE_CREATED_HIT
  Check sensitive detector type:
    "calorimeter" -> reason |= G4PARTICLE_CREATED_CALORIMETER_HIT
    "tracker"     -> reason |= G4PARTICLE_CREATED_TRACKER_HIT
    other         -> reason |= G4PARTICLE_CREATED_TRACKER_HIT  (default to tracker)
```

**Example -- neutron after tracking:**
```
reason = 0x030                                     (from begin)
       | G4PARTICLE_HAS_SECONDARIES                (if it interacted)
       | G4PARTICLE_CREATED_HIT                    (if it hit a sensitive detector)
       | G4PARTICLE_CREATED_CALORIMETER_HIT        (if it hit forward calorimeter)
```

**Example -- pi0 after tracking (1 step, decays immediately to gamma+gamma):**
```
reason = 0x030                                     (from begin)
       | G4PARTICLE_HAS_SECONDARIES                (pi0 -> gamma gamma)
       = 0x038
No hits created (pi0 has zero track length, never reaches a sensitive detector)
```

### Phase 3: Post-Track (`Geant4ParticleHandler::end`)

File: `DD4hep/DDG4/src/Geant4ParticleHandler.cpp:330-451`

Called when a track finishes. This is the CRITICAL decision point.

```
1. SNAPSHOT the current reason: track_reason = m_currTrack.reason
   (This preserves the pre-handler flags for later use)

2. Create REFERENCE mask to m_currTrack.reason:
   PropertyMask mask(m_currTrack.reason)
   (Any modification to m_currTrack.reason is visible through mask)

3. Record endpoint: vex, vey, vez from track position
   Record endpoint momentum: pex, pey, pez

4. Set simulation status bits:
   - If track ended at world boundary -> status |= G4PARTICLE_SIM_LEFT_DETECTOR
   - If kinetic energy <= 0           -> status |= G4PARTICLE_SIM_STOPPED

5. Backscatter check (only if STARTED_IN_CALORIMETER):
   If ended in tracker or has tracker hits -> flag as backscatter

6. *** CALL USER HANDLER: handler->end(track, m_currTrack) ***
   This calls Geant4TCUserParticleHandler::end() which calls:
   - setReason(p, starts_in_trk_vol, ends_in_trk_vol)  [MODIFIES m_currTrack.reason!]
   - setSimulatorStatus(p, starts_in_trk_vol, ends_in_trk_vol)

7. STORAGE DECISION (the gate):
   IF mask is non-null OR has trackInfo OR has backscatter flag:
     -> STORE particle in particleMap
   ELSE:
     -> DO NOT STORE. Set equivalentTrack to parent.
        OR the SNAPSHOT track_reason into parent's reason
        (preserves flags for hit association even though particle is dropped)
```

**The critical subtlety**: `mask` is a REFERENCE to `m_currTrack.reason`. If `setReason`
sets `p.reason = 0`, then `mask.isNull()` returns TRUE, and the particle is NOT stored,
REGARDLESS of what the original flags were. The SNAPSHOT `track_reason` preserves the
original flags but is only used for backscatter check and parent inheritance.

### Phase 3a: setReason -- The Primary Filter

File: `DD4hep/DDG4/plugins/Geant4UserParticleHandlerHelper.cpp:23-54`

```cpp
void setReason(Geant4Particle& p, bool starts_in_trk_vol, bool ends_in_trk_vol) {
  ReferenceBitMask<int> reason(p.reason);

  // [1] Primary particles: ALWAYS keep
  if( reason.isSet(G4PARTICLE_PRIMARY) ) {
    return;
  }
  // [2] Created in tracker but below energy threshold: DROP
  else if( starts_in_trk_vol && !reason.isSet(G4PARTICLE_ABOVE_ENERGY_THRESHOLD) ) {
    p.reason = 0;       // <-- ZEROES ALL FLAGS including KEEP_PROCESS
    return;
  }
  // [3] Has tracker hit AND above threshold: KEEP
  if( reason.isSet(G4PARTICLE_CREATED_TRACKER_HIT)
      && reason.isSet(G4PARTICLE_ABOVE_ENERGY_THRESHOLD) ) {
    return;
  }
  // [4] Created OUTSIDE tracker:
  if( !starts_in_trk_vol ) {
    if( !ends_in_trk_vol ) {
      p.reason = 0;     // <-- ZEROES ALL FLAGS -- THIS IS THE MAIN PROBLEM
    }
    else if( !reason.isSet(G4PARTICLE_CREATED_TRACKER_HIT) ) {
      p.reason = 0;     // <-- Ends in tracker but no tracker hit: DROP
    }
  }
  // [5] Implicit: created in tracker AND above threshold AND no tracker hit
  //     -> falls through, reason PRESERVED (kept)
}
```

**Tracking cylinder is configured from epic's constants:**
```python
# DD4hep/DDG4/python/DDSim/Helper/ParticleHandler.py:129-146
user.TrackingVolume_Zmax = DDG4.tracker_region_zmax   # = +335 cm
user.TrackingVolume_Zmin = DDG4.tracker_region_zmin   # = -175 cm
user.TrackingVolume_Rmax = DDG4.tracker_region_rmax   # = ~82 cm
```

**Geometry test in Geant4TCUserParticleHandler::end():**
```cpp
// DD4hep/DDG4/plugins/Geant4TCUserParticleHandler.cpp:101-119
double r_prod = sqrt(p.vsx*p.vsx + p.vsy*p.vsy);
double z_prod = p.vsz;
bool starts_in_trk_vol = (r_prod <= m_rTracker
  && z_prod >= m_zTrackerMin && z_prod <= m_zTrackerMax);

double r_end = sqrt(p.vex*p.vex + p.vey*p.vey);
double z_end = p.vez;
bool ends_in_trk_vol = (r_end <= m_rTracker
  && z_end >= m_zTrackerMin && z_end <= m_zTrackerMax);
```

### Phase 3b: setSimulatorStatus

File: `DD4hep/DDG4/plugins/Geant4UserParticleHandlerHelper.cpp:56-72`

```cpp
void setSimulatorStatus(Geant4Particle& p, bool starts_in_trk_vol, bool ends_in_trk_vol) {
  ReferenceBitMask<int> simStatus(p.status);

  if( ends_in_trk_vol )
    simStatus.set(G4PARTICLE_SIM_DECAY_TRACKER);

  if( !ends_in_trk_vol && !simStatus.isSet(G4PARTICLE_SIM_LEFT_DETECTOR) )
    simStatus.set(G4PARTICLE_SIM_DECAY_CALO);

  if( !starts_in_trk_vol && ends_in_trk_vol )
    simStatus.set(G4PARTICLE_SIM_BACKSCATTER);
}
```

### Phase 4: End of Event -- rebaseSimulatedTracks

File: `DD4hep/DDG4/src/Geant4ParticleHandler.cpp:488-628`

Establishes parent-daughter relationships using Geant4 track IDs:
```
For each particle in particleMap:
  Find its g4Parent in the map (following equivalentTracks chain if needed)
  Add this particle to parent's daughters list
  Add parent to this particle's parents list
```

### Phase 5: End of Event -- recombineParents

File: `DD4hep/DDG4/src/Geant4ParticleHandler.cpp:664-742`

Iterates particles in REVERSE order (latest first). Decides final keep/drop.

```
For each particle (reverse iteration):

  1. Call dropParticle(p) via user handlers (or defaultDropParticle if no handlers):
     dropParticle delegates to defaultDropParticle which checks:
       - backscatter? -> DON'T DROP
       - reason is null? -> DROP
       - has secondaries AND low energy AND no hits? -> DROP
       - no hits AND low energy? -> DROP
       - no tracker hit AND has calo hit AND low energy? -> DROP
       - else -> DON'T DROP

  2. Force-remove checks:
     - reason is null OR FORCE_KILL set? -> remove_me = true

  3. Force-keep checks (each causes `continue`, skipping removal):
     - G4PARTICLE_KEEP_USER    -> skip (kept)
     - G4PARTICLE_PRIMARY      -> skip (kept)
     - G4PARTICLE_KEEP_ALWAYS  -> skip (kept)
     - G4PARTICLE_KEEP_PARENT  -> (continue is COMMENTED OUT, does NOT skip!)
     - G4PARTICLE_KEEP_PROCESS -> check if parent has ABOVE_ENERGY_THRESHOLD:
         YES -> set KEEP_PARENT on parent, skip (kept)
         NO  -> fall through

  4. If remove_me == true:
     - Add to remove set
     - Set equivalentTrack to parent
     - OR this particle's reason into parent's reason
     - Increment parent's steps and secondaries
     - Call user handler combine() for any custom merging

  5. After iteration: delete all particles in remove set from particleMap
```

### Phase 6: Write to EDM4hep -- saveParticles

File: `DD4hep/DDG4/edm4hep/Geant4Output2EDM4hep.cpp:419-521`

Only particles surviving in the final `particleMap` are written.

```
Pass 1 -- Create EDM4hep MCParticle objects:
  For each particle in particleMap:
    Set PDG, momentum (start + endpoint), vertex (start + endpoint)
    Set time, mass, charge
    Set generator status from genStatus or status flags:
      GEN_STABLE -> 1, GEN_DECAYED -> 2, GEN_DOCUMENTATION -> 3,
      GEN_BEAM -> 4, GEN_OTHER -> 9
    Set simulation status bits from status field:
      createdInSimulation, backscatter, vertexIsNotEndpointOfParent,
      decayedInTracker, decayedInCalorimeter, hasLeftDetector, stopped
    If createdInSimulation: force generatorStatus = 0

Pass 2 -- Establish parent-daughter relations:
  For each particle:
    For each daughter ID in particle->daughters:
      Look up daughter in the EDM4hep collection by ID mapping
      IF NOT FOUND: print FATAL error, skip   <--- pi0 missing here!
      Add daughter to MCParticle
    For each parent ID in particle->parents:
      Look up parent, add to MCParticle
```

---

## Root Cause Analysis: Why n+pi0 = 0

### Issue 1: Decay z cutoff (tracker cylinder boundary)

The decay z distribution hard-cutoff at ~3350 mm proves this. 51.1% of Lambdas appear
"undecayed" because their decay happened at z > 335 cm and ALL daughters were dropped
by `setReason` step [4]: `!starts_in_trk_vol && !ends_in_trk_vol -> reason = 0`.

### Issue 2: pi0 systematically absent (n+pi0 = 0 means something is 100% broken)

The data shows 888 "Other" decays = 36.3% of decayed Lambdas, matching the n+pi0
branching ratio (35.8%). Geant4 IS producing n+pi0 at the correct rate, but no event
is classified as "n + pi0".

**Known bug in v01-35 (the Docker image version):**

The Docker image builds DD4hep v01-35. This version has a bug in `recombineParents`:
```cpp
bool remove_me = defaultKeepParticle(*p);
if ( !this->m_userHandlers.empty() )  {
    remove_me = true;          // BUG: unconditionally overwrites to true
    for( auto* h : this->m_userHandlers )
        remove_me |= h->keepParticle(*p);  // true | anything = always true
}
```
This bug was fixed in commit `1dc80f87` (2026-02-23), AFTER v01-35 was released.
However, particles with KEEP_PROCESS whose parent has ABOVE_ENERGY_THRESHOLD still
survive via the `continue` statement in the KEEP_PROCESS branch of recombineParents.
So this bug alone should NOT drop pi0 from inside-tracker decays.

**What needs experimental verification:**

For Lambda decays INSIDE the tracker (z < 335 cm), BOTH neutron and pi0 should survive:
- Both get KEEP_PROCESS from "Decay" in begin()
- Both are above energy threshold
- setReason preserves reason (starts_in_trk_vol=true, above threshold)
- recombineParents: KEEP_PROCESS + parent (Lambda) has ABOVE_ENERGY_THRESHOLD → kept

Gammas from pi0→γγ WILL hit electromagnetic calorimeters and SHOULD also be saved
(CREATED_CALORIMETER_HIT flag). So the 888 "Other" events should have daughters
visible in the MCParticles output.

**Two hypotheses for the 888 "Other" events:**

**Hypothesis A: Pi0 IS tracked, but gammas replace it in the record**

If Geant4 tracks pi0 as a separate G4Track (standard behavior), then:
- Lambda daughters = [neutron, pi0]
- Pi0 daughters = [gamma1, gamma2]
- Analysis looking for (n, pi0) should find it → should be classified as "n + pi0"
- The fact that n+pi0 = 0 means either pi0 is not in the output OR the analysis has a bug

BUT: if pi0 is somehow removed by recombineParents (e.g., due to the v01-35
`remove_me = true` bug interacting with some edge case), then:
- Pi0 is removed from particleMap
- equivalentTracks maps pi0 → Lambda
- Gammas' parent is reassigned to Lambda via equivalentTracks
- Lambda daughters become = [neutron, gamma1, gamma2]
- Analysis looking for (n, pi0) finds (n, γ, γ) → "Other"

This would explain the 888 "Other" events AND why gammas survive (they hit calorimeters).

**Hypothesis B: Pi0 is NOT tracked as a separate G4Track**

Pi0 lifetime = 8.4e-17 s. Some Geant4 configurations or physics lists may pre-decay
pi0 at the production vertex without creating a separate track. In that case:
- Lambda daughters would be [neutron, gamma1, gamma2] directly
- Analysis finds no pi0 → classified as "Other"

**Hypothesis A is more likely** because:
1. Standard Geant4 DOES create G4Tracks for pi0 (not shortlived, has decay table)
2. The user previously saw n+pi0 working, meaning pi0 WAS a tracked particle
3. The gammas should hit calorimeters and be saved, explaining the "Other" classification

### Critical check: What are the actual daughters in the 888 "Other" events?

The user checked one event (evt_id=1513) and found daughters=1 (only neutron). This
specific event may be from a decay OUTSIDE the tracker boundary where gammas were
also dropped, or from a hadronic interaction rather than a decay.

**The 888 "Other" events likely contain a MIX of:**
- Events with (neutron, gamma, gamma) -- decay inside tracker, gammas survived
- Events with (neutron) only -- decay near tracker boundary, gammas dropped
- Events with (neutron, other particles) -- hadronic interactions, not true decays

### Why p+pi- works but n+pi0 doesn't

For Lambda -> p + pi-:
- Proton: long-lived, charged, creates tracker hits -> always kept
- Pi-: long-lived, charged, creates tracker hits -> always kept
- No intermediate short-lived particle -> clean 2-body final state in MCParticles

For Lambda -> n + pi0 (if pi0 is tracked but removed):
- Neutron: long-lived, above threshold, has KEEP_PROCESS -> kept
- Pi0: above threshold, has KEEP_PROCESS -> should be kept BUT may be removed by
  the v01-35 `remove_me = true` bug or by recombineParents edge case
- Gammas: hit calorimeters, above threshold -> kept, but parent reassigned to Lambda
- Result: Lambda daughters = (neutron, gamma, gamma) -> classified as "Other"

---

## Recent DD4hep Code Changes (potential regression sources)

### Bug: "removing all particles except primaries" (introduced Jan 2026, fixed Feb 2026)

**Introduced**: `e1d47ac4` (2026-01-19) - "Allow user actions within ParticleHandler"
Changed from single `m_userHandler` to multiple `m_userHandlers`. In `recombineParents`,
set `remove_me = true` unconditionally before calling user handlers.

**Fixed**: `1dc80f87` (2026-02-23) - "fix keepParticle logic"
Commit message: "true or anything is always true, so we were removing all particles,
except primaries." Changed to `remove_me = false` as default.

**Current version (1829429c) includes the fix.**

### Other relevant recent changes:
- `cd5590b7` (2026-02-27): Renamed `keepParticle` -> `dropParticle` (semantic clarity)
- `da2e946e` (2026-02-*): Added backscatter handling for calo->tracker particles
- `fa7fe958` (2026-03-13): Simplified primary check in setReason (added explicit return)
- `2fafcc24` (2026-03-13): Added tracker-hit + above-threshold shortcut in setReason

---

## Issue 3: SimCalorimeterHits missing in 2026.03 (not present in 2025.10)

### Version differences between images

| Component | 2025.10 image | 2026.03 image |
|---|---|---|
| DD4hep | v01-31 | v01-35 |
| Geant4 | v11.3.0 | v11.3.2 |
| PODIO | v01-03 | v01-06 |
| EDM4hep | v00-99-02 | v00-99-04 |
| Epic geometry | 25.02.0 | main (at build time) |

### What we verified is NOT the cause

1. **Epic far-forward geometry** — `far_forward/default.xml` includes B0_ECal, ZDC_SiPMonTile,
   ZDC_Crystal_LYSO. These haven't changed between Oct 2025 and Mar 2026. All properly
   call `sens.setType("calorimeter")`.

2. **Missing `type_flags`** — Commit `a3ea84612` (Apr 6, 2026) added `type_flags` and
   `setDetectorTypeFlag()` to far-forward calorimeters. These are metadata for reconstruction
   (DetType classification), NOT for Geant4 hit generation. Absence of type_flags doesn't
   prevent SimCalorimeterHits from being created.

3. **`setReason()` logic** — Identical since 2014. This only affects MCParticles, not
   calorimeter hits. Hits are generated during Geant4 stepping regardless of particle
   filtering.

### What DID change (DD4hep v01-31 → v01-35)

**A. recombineParents `remove_me = true` bug**

The critical behavioral difference:

v01-31 (`recombineParents`, line 634):
```cpp
bool remove_me = m_userHandler ? m_userHandler->keepParticle(*p) : defaultKeepParticle(*p);
```
`defaultKeepParticle` returns false for above-threshold particles → `remove_me = false`.
Most secondary particles SURVIVE unless they hit a specific removal condition.

v01-35 (`recombineParents`, line 630-634):
```cpp
bool remove_me = defaultKeepParticle(*p);
if ( !this->m_userHandlers.empty() )  {
    remove_me = true;          // BUG: unconditionally true when handlers present
    for( auto* h : this->m_userHandlers )
        remove_me |= h->keepParticle(*p);  // true | anything = always true
}
```
ALL non-primary particles with `remove_me = true` unless they hit a `continue` escape.

Concrete impact on Lambda decay products (inside tracker):
- v01-31: neutron survives (KEEP_PROCESS), pi0 survives (remove_me=false), gammas survive
- v01-35: neutron survives (KEEP_PROCESS continue), pi0 REMOVED (KEEP_PARENT masks
  KEEP_PROCESS, remove_me=true), gammas survive but reparented to Lambda

**B. Sensitive detector action changes (`Geant4SensDetAction.cpp`, `Geant4SDActions.cpp`)**

- New `UseVolumeManager` property (default: `true`) — guards volume manager lookups
- `cellID()` function added optical photon special handling (G4OpticalParameters)
- Calorimeter hit position calculation now handles `!segmentation.isValid()` case

These changes should be behavioral no-ops for standard EIC calorimeters (default settings,
valid segmentation).

**C. Output writer (`Geant4Output2EDM4hep.cpp`)**

No filtering logic changes. Added run parameter storage, helicity support, multithreading
support. `saveCollection` and its MCParticle linking logic are identical in both versions.

### DISPROVED: saveCollection exception cascade

Initial hypothesis was that aggressive removal could break MCParticle links in hits,
causing `m_particles.at(trackID)` to throw and skip all remaining collections.

**This is proven impossible.** Full code path trace:

1. **Every G4Track gets an `m_equivalentTracks` entry** in `end()` (line 401 or 426).
   Every track that deposits energy in a sensitive detector was tracked → has entry.

2. **`recombineParents` maintains the chain.** When removing a particle (line 723):
   `m_equivalentTracks[g4_id] = p->g4Parent` overwrites self-mapping with parent mapping.
   The parent's own entry still exists.

3. **`rebaseSimulatedTracks` resolves every chain** (lines 536-561). The chain walk
   follows parent pointers: `child → parent → grandparent → ... → primary`. Every
   parent was a G4Track → has m_equivalentTracks entry → chain continues. Primary
   particles are ALWAYS in m_particleMap (never removed by recombineParents, protected
   by `G4PARTICLE_PRIMARY` continue). So the chain always terminates.

4. **Rebased IDs are contiguous** (code comment at line 514: "assumed ZERO based without
   holes"). Primary IDs: 0..N-1, secondary IDs: N, N+1, ... So rebased ID = MCParticle
   collection index.

5. **`particleID()` never returns -1.** It looks up `equivalentTracks[g4_id]`. Every
   g4_id from a hit creator has an entry (link 1). Every entry resolves to a surviving
   particle (link 3). So it always returns a valid rebased ID ≥ 0.

6. **`m_particles.at(rebased_id)` never throws.** The rebased ID equals the collection
   index (link 4). The collection has that many entries.

**Conclusion:** The v01-35 `remove_me=true` bug changes WHICH MCParticle each hit
points to (more hits point to ancestor primaries), but every hit IS always written.
SimCalorimeterHits cannot be lost through this mechanism.

### What to verify

1. **Check if SimCalorimeterHit collections exist in the output**:
   ```python
   import podio
   reader = podio.root_io.Reader("output.edm4hep.root")
   for name in reader.get_podio_version().available_collections:
       print(name)
   # Or: check with ROOT TBrowser for collection names
   ```

2. **Check ddsim log for ERROR messages**: Look for:
   - `"No Equivalent particle for track"` — from `particleID()` failure
   - `"Exception while saving event"` — from the outer catch
   - `"FATAL: No real particle parent present"` — from `end()` storage gate

3. **Run with `--part.keepAllParticles=True`**: If all particles are kept, no
   `equivalentTracks` failures should occur. If SimCalorimeterHits appear with
   `keepAllParticles=True` but not without, it confirms the removal cascade hypothesis.

4. **Compare raw collection sizes**: Run the same events with 2025.10 and 2026.03
   images. Compare the number of entries in each hit collection.

---

## Proposed Fixes

### Fix 1: Extend tracker region to cover far-forward (quick, partial fix)

In `epic/compact/definitions.xml`, extend `tracker_region_zmax` to cover B0:
```xml
<constant name="tracker_region_zmax" value="750*cm"/>  <!-- past B0 ECal at 702 cm -->
```
**Fixes**: Issue 1 (decay z cutoff). **Does NOT fix**: Issue 2 (pi0 never tracked).
**Cons**: Increases MC truth file size; conceptually wrong (this isn't really the
"tracker region").

### Fix 2: Save all decay products regardless of position (correct fix for Issue 1)

Modify `Geant4UserParticleHandlerHelper.cpp:setReason()` to preserve particles from
saved processes even outside the tracker region:

```cpp
void setReason(Geant4Particle& p, bool starts_in_trk_vol, bool ends_in_trk_vol) {
  dd4hep::detail::ReferenceBitMask<int> reason(p.reason);

  if( reason.isSet(G4PARTICLE_PRIMARY) ) {
    return;
  }
  // NEW: Keep decay products (from saved processes like "Decay")
  // regardless of position -- these are physics-critical for MC truth
  if( reason.isSet(G4PARTICLE_KEEP_PROCESS) ) {
    return;
  }
  // ... rest of existing logic unchanged ...
}
```

**Fixes**: Issue 1 fully. **Partially fixes Issue 2**: neutron from n+pi0 would be
saved at all z positions, but pi0 still won't appear (Geant4 doesn't track it).

### Fix 3: Upgrade DD4hep past v01-35 (fixes recombineParents bug)

The Docker image uses DD4hep v01-35 which has the `remove_me = true` bug. Upgrading
to a version that includes `1dc80f87` (2026-02-23) fixes this. This may resolve the
pi0 issue if the bug is what causes pi0 to be dropped in recombineParents.

In `eic-base/Dockerfile`, change:
```
ARG VERSION_DD4HEP=v01-36
```
(v01-36 should include the fix. Verify with `git log v01-36 --oneline | grep keepParticle`)

### Fix 4: Custom EIC particle handler (most flexible)

Create a `Geant4EICUserParticleHandler` that extends `Geant4TCUserParticleHandler`:
- Keep all daughters of primary particles regardless of position
- Keep all particles within sensitive detector volumes (not just tracker cylinder)
- Reconstruct intermediate pi0 from gamma pairs
- Optionally keep particles in specific z-ranges (far-forward)

### Fix 5: keepAllParticles = True (debugging only)

```python
SIM.part.keepAllParticles = True
```
Sets `G4PARTICLE_KEEP_ALWAYS` on all particles. Preserves everything including shower
debris. Useful for verifying the diagnosis but NOT for production (huge file size).

---

## Key Files Reference

| File | Role |
|---|---|
| `DD4hep/DDG4/plugins/Geant4UserParticleHandlerHelper.cpp` | `setReason()` -- **primary filter** |
| `DD4hep/DDG4/plugins/Geant4TCUserParticleHandler.cpp` | Tracking cylinder geometry check |
| `DD4hep/DDG4/src/Geant4ParticleHandler.cpp` | begin/end track, mark, recombineParents |
| `DD4hep/DDG4/src/Geant4UserParticleHandler.cpp` | dropParticle -> defaultDropParticle |
| `DD4hep/DDG4/include/DDG4/Geant4Particle.h` | All flag definitions (reason + status) |
| `DD4hep/DDG4/python/DDSim/Helper/ParticleHandler.py` | Python config (saveProcesses, keepAll) |
| `DD4hep/DDG4/edm4hep/Geant4Output2EDM4hep.cpp` | EDM4hep MCParticle writer |
| `epic/compact/definitions.xml:733-735` | tracker_region constants |
| `epic/compact/far_forward/B0_tracker.xml` | B0 geometry |
| `geant4/source/particles/hadrons/barions/src/G4Lambda.cc` | Lambda definition |
| `geant4/source/processes/decay/src/G4Decay.cc` | Decay process |

---

## Verification Steps (using Docker eicdev/eic-full)

**MOST IMPORTANT -- Step 0: Check what "Other" events actually contain**

For the 888 "Other" events, dump ALL daughters of Lambda (all PDG codes, not just
looking for n+pi0 or p+pi-). Key question: do you see (neutron, gamma, gamma) as
daughters? If yes, the gammas ARE being saved, pi0 is just not appearing as an
intermediate particle in the MCParticles record. The gammas got their parent
reassigned to Lambda when pi0 was removed from the record.

1. **keepAllParticles test**: Run with `--part.keepAllParticles=True`. If pi0 (PDG 111)
   appears as a Lambda daughter, the issue is in the filtering chain (likely the v01-35
   `remove_me = true` bug in recombineParents). If pi0 still doesn't appear, Geant4
   is not tracking it as a separate particle.

2. **Confirm pi0 tracking**: Run with Geant4 verbose tracking (`/tracking/verbose 2`)
   for a Lambda -> n + pi0 event. Check if pi0 appears as a separate G4Track.

3. **Check DD4hep version in Docker**: `python -c "import dd4hep; print(dd4hep.version())"` 
   or check `/opt/*/dd4hep/share/DD4hep/DD4hepConfig-version.cmake`. Confirm it's v01-35.

4. **Test with DD4hep v01-36**: Rebuild Docker image with `VERSION_DD4HEP=v01-36`
   (includes the recombineParents bug fix). If n+pi0 starts appearing, the bug was
   the root cause.

5. **Check neutron creator process**: For neutrons in "Other" events, verify the
   creator process is "Decay" (not "LambdaInelastic" or other hadronic process).

6. **Test Fix 2**: Apply the KEEP_PROCESS bypass in setReason and verify decay products
   appear at all z positions (fixes Issue 1 -- the z cutoff).
