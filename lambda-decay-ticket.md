# `setReason()` unconditionally zeros `reason`, overriding `keepAllParticles` for particles born outside tracker cylinder

## Summary

Setting `keepAllParticles=True` is supposed to guarantee that every simulated particle ends up in the MC truth output. It does not. If a particle is born outside the tracking cylinder and is not a primary, it gets silently discarded — even with `keepAllParticles=True`.

The reason is a small mismatch between two pieces of DD4hep that don't talk to each other:

- **`Geant4ParticleHandler`** marks every particle with a "keep me" flag (`KEEP_ALWAYS`) when `keepAllParticles=True`. At the end of each track it checks the flag and, if set, stores the particle.
- **`Geant4TCUserParticleHandler`** (the tracking-cylinder filter, installed by default in DDSim) runs *just before* that check. For any non-primary particle born outside the cylinder, it overwrites the entire flags field with zero (`p.reason = 0`) — wiping `KEEP_ALWAYS` along with everything else.

By the time the storage check runs, the "keep me" flag is gone and the particle is dropped. The user gets no warning. The only flag the cylinder filter respects is `PRIMARY`; `KEEP_ALWAYS` was never added to its allow-list.

The practical consequence: any secondary produced outside the tracker region (decay products, backscatter, far-forward physics) is missing from MC truth, regardless of `keepAllParticles`. For most detectors this is invisible because the relevant physics happens inside the cylinder. For experiments with significant acceptance outside it — notably EIC's far-forward region — it is a routine source of missing decay chains.

## Observed symptom (EIC)

Upstream report: [eic/epic#1069](https://github.com/eic/epic/issues/1069). In EIC simulations, roughly 50% of `GEN_STABLE` Λ (PDG 3122) appear in `MCParticles` with "No decay" — no daughters recorded — even with `SIM.part.keepAllParticles=True`. The split corresponds precisely to whether Λ decays inside or outside the tracking cylinder (`z_max ≈ 335 cm`, `z_min ≈ -175 cm`, `r_max ≈ 82 cm`). The EIC far-forward region (B0 at `z ≈ 630 cm`, Roman Pots, ZDC) is entirely outside. Kinematics and branching ratios for the retained half are correct — it is purely an MC-truth bookkeeping issue.

Hit collections are **not** affected: hits are produced during G4 stepping (before particle-handler filtering) and `saveCollection` writes them unconditionally. The MCParticle link is remapped to the surviving ancestor (Λ or primary), and `producedBySecondary=true` correctly flags the remap.

## Root cause — step by step

1. `SIM.part.keepAllParticles=True` is set by the user.
2. `Geant4ParticleHandler::begin()` sets `G4PARTICLE_KEEP_ALWAYS` (bit 10) on every new track.
3. A Λ decays at `z = 500 cm` (far-forward, outside the tracker cylinder). Its daughters (`p`, `π⁻`) start there, inheriting `reason` with `KEEP_ALWAYS` set.
4. When a daughter's track ends, `Geant4ParticleHandler::end(track)` runs:
   - Line 336: `PropertyMask mask(m_currTrack.reason);` — `PropertyMask` is `ReferenceBitMask<int>` which holds `T& mask;` (a reference), so this binds to the live `m_currTrack.reason` field.
   - Line 386: `handler->end(track, m_currTrack);` — dispatches to `Geant4TCUserParticleHandler::end()`.
5. `Geant4TCUserParticleHandler::end()` computes `starts_in_trk_vol=false`, then calls `setReason(p, false, ends_in_trk_vol)`.
6. `setReason()` in `Geant4UserParticleHandlerHelper.cpp`:
   - Not `PRIMARY` → skip the only early-return.
   - `KEEP_ALWAYS` is **never checked**.
   - Falls into `if(!starts_in_trk_vol)` and executes `p.reason = 0;` — direct assignment, wiping all bits including `KEEP_ALWAYS`.
7. Control returns to `Geant4ParticleHandler::end()`. Because `mask` is a reference to the now-zeroed field, `mask.isNull()` returns `true` at the storage gate (line ~400).
8. Storage gate fails (no `SIM_BACKSCATTER` restoration either — that would require `STARTED_IN_CALORIMETER` plus a tracker hit; neither applies to Λ daughters born in beam-pipe vacuum).
9. Particle is dropped: `m_equivalentTracks[g4_id] = pid` remaps the daughter to its parent.
10. EDM4hep output: Λ appears with `endpoint` set but **no daughters** → "No decay" classification.

## Relevant code

**`DDG4/plugins/Geant4UserParticleHandlerHelper.cpp`** — the bug:

```cpp
void setReason(Geant4Particle& p, bool starts_in_trk_vol, bool ends_in_trk_vol) {
  dd4hep::detail::ReferenceBitMask<int> reason(p.reason);

  if( reason.isSet(G4PARTICLE_PRIMARY) ) {
    return;                              // <-- only PRIMARY is protected
  } else if( starts_in_trk_vol && ! reason.isSet(G4PARTICLE_ABOVE_ENERGY_THRESHOLD) )  {
    p.reason = 0;
    return;
  }
  if(reason.isSet(G4PARTICLE_CREATED_TRACKER_HIT) && reason.isSet(G4PARTICLE_ABOVE_ENERGY_THRESHOLD))  {
    return;
  }
  if( !starts_in_trk_vol ) {
    if( !ends_in_trk_vol ){
      p.reason = 0;                      // <-- wipes KEEP_ALWAYS
    }
    else if( ! reason.isSet(G4PARTICLE_CREATED_TRACKER_HIT) ) {
      p.reason = 0;                      // <-- wipes KEEP_ALWAYS
    }
  }
}
```

**`DDG4/src/Geant4ParticleHandler.cpp`** — the surrounding flow (`end()`):

```cpp
void Geant4ParticleHandler::end(const G4Track* track) {
  // ...
  int32_t track_reason = m_currTrack.reason;     // local COPY (snapshot)
  PropertyMask mask(m_currTrack.reason);         // REFERENCE to live field
  // ...
  PropertyMask reason_mask(track_reason);        // reference to the COPY
  // ...
  for (auto* handler : this->m_userHandlers)
    handler->end(track, m_currTrack);            // <-- setReason zeros m_currTrack.reason here
  // ...
  if (!mask.isNull() || track_info || reason_mask.isSet(G4PARTICLE_SIM_BACKSCATTER)) {
    // store
  } else {
    // drop -> m_equivalentTracks[g4_id] = pid
  }
}
```

`PropertyMask` is `ReferenceBitMask<int>` (see `DDCore/include/Parsers/Primitives.h`), which stores `T& mask;` — a reference, not a copy. So `mask.isNull()` observes the zero that `setReason()` wrote.

## Proposed fix

Add a single early-return for `KEEP_ALWAYS` parallel to the existing `PRIMARY` check:

```cpp
void setReason(Geant4Particle& p, bool starts_in_trk_vol, bool ends_in_trk_vol) {
  dd4hep::detail::ReferenceBitMask<int> reason(p.reason);

  if( reason.isSet(G4PARTICLE_PRIMARY) ) {
    return;
  }
  if( reason.isSet(G4PARTICLE_KEEP_ALWAYS) ) {  // NEW
    return;                                     // NEW — honor keepAllParticles
  }
  // ... rest unchanged
}
```

Rationale: `KEEP_ALWAYS` is an explicit user request to preserve the particle. The existing logic short-circuits for `PRIMARY` for the same reason; `KEEP_ALWAYS` deserves symmetric treatment. The change is minimal, local, and preserves default behavior (the bit is only set when the user opts in via `keepAllParticles=True`).

## Workaround (no rebuild)

Disable the tracking-cylinder user handler in the steering file:

```python
SIM.part.userParticleHandler = ""
```

This bypasses `Geant4TCUserParticleHandler` entirely, so `setReason()` is never called and `KEEP_ALWAYS` is honored. Side effect: no tracker/calorimeter origin classification in the `simulatorStatus` bits.

## Why this was not caught earlier

- `Geant4TCUserParticleHandler` was designed for compact detectors where the tracker cylinder covered the full acceptance.
- `keepAllParticles` was added later; the TC handler's `setReason()` was never updated to respect the new bit.
- The bug is silent: no warning, no error — the particles simply disappear from MC truth.
- For most users the symptom is invisible because decays happen inside the cylinder. EIC's far-forward region exposes it consistently.

## Test

A regression test would generate a long-lived neutral (e.g. Λ with forced `GEN_STABLE`) with a decay vertex at `z > TrackingVolume_Zmax`, run with `keepAllParticles=True`, and assert that the daughters appear in `MCParticles` with the Λ as parent. Current behavior: daughters missing. Expected with fix: daughters present.

## References

- Upstream symptom: [eic/epic#1069](https://github.com/eic/epic/issues/1069)
- Bug location: `DDG4/plugins/Geant4UserParticleHandlerHelper.cpp` — `setReason()`
- Flag definition: `DDG4/include/DDG4/Geant4Particle.h` — `G4PARTICLE_KEEP_ALWAYS = 1<<10`
- Flag set site: `DDG4/src/Geant4ParticleHandler.cpp` — `Geant4ParticleHandler::begin()`
- Storage gate: `DDG4/src/Geant4ParticleHandler.cpp` — `Geant4ParticleHandler::end()` storage condition
- `ReferenceBitMask` definition: `DDCore/include/Parsers/Primitives.h`
