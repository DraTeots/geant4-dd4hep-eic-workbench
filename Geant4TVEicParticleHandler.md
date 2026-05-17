# Geant4TVEicParticleHandler — context & design notes

Date: 2026-05-17

## Background: tracking volume in npsim/ddsim

- **npsim default handler:** On branch `pr/use_volume_tracking_region`,
  `npsim/src/dd4pod/python/npsim.py:48` hard-codes
  `RUNNER.part.userParticleHandler = "Geant4TVUserParticleHandler"`
  (commit `a965152`, "feat: use Geant4TVUserParticleHandler by default").
- That commit is **only on the PR branch**, not on `origin/main`. The
  official EIC image builds from `main`, where the default is still
  `Geant4TCUserParticleHandler`. So on the stock image you **must** pass
  `--part.userParticleHandler=Geant4TVUserParticleHandler` explicitly.
- **epic side:** `epic/compact/tracking_region.xml:33` defines a
  `parallelworld_volume name="tracking_volume"` (included via
  `epic/prefix/share/epic/epic.xml:57`). DD4hep's Compact2Objects parser
  calls `description.setTrackingVolume(vol)`; the handler retrieves it via
  `kernel().detectorDescription().trackingVolume()`. Defining
  `tracking_volume` in epic is sufficient — no extra wiring needed once the
  handler is selected.
- `part.keepAllParticles=True` overrides the handler; `part.saveProcesses`
  is orthogonal (which secondaries survive, not volume filtering).

## Energy threshold clarification

- The TV handler does **not** contain any energy cut. It only reads the
  pre-computed reason bit `G4PARTICLE_ABOVE_ENERGY_THRESHOLD`.
- That bit is set by the base `Geant4ParticleHandler`
  (`DD4hep/DDG4/plugins/Geant4ParticleHandler.cpp`) using its
  `MinimalKineticEnergy` property — exposed as `part.minimalKineticEnergy`,
  **DD4hep default 1 MeV** (`DD4hep/DDG4/python/DDSim/Helper/ParticleHandler.py:15`),
  not 5 MeV. npsim does not override it; any 5 MeV value would come from a
  command line / steering file.
- The base cut is global and position-agnostic — no Z/position-aware rule
  exists upstream. That is the motivation for the EIC handler.

## New plugin: Geant4TVEicParticleHandler

- **Location:** `npsim/src/plugins/src/Geant4TVEicParticleHandler.cpp`,
  added to the existing `NPDetPlugins` target in
  `npsim/src/plugins/CMakeLists.txt`.
- **Initial implementation:** verbatim clone of DD4hep's
  `Geant4TVUserParticleHandler` (inherits `Geant4UserParticleHandler`,
  same base as upstream). Registered as a distinct plugin via
  `DECLARE_GEANT4ACTION(Geant4TVEicParticleHandler)`.
- The helpers `setReason` / `setSimulatorStatus` are **inlined** (copied
  from `DD4hep/DDG4/plugins/Geant4UserParticleHandlerHelper.{h,cpp}`)
  because that header is internal to DD4hep's plugins folder and not part
  of the installed public API.
- `npsim.py` default left **unchanged** (still points at the stock
  handler) for now.

### EIC-specific cut (in `end()`)

Drops particles that end far forward with low momentum:

- if `p.vez > ForwardZMax` **and** `|p| < ForwardMomentumMin` → `p.reason = 0`
- `|p|` from `p.psx/psy/psz` (MeV); `p.vez` in mm.
- Applied **after** the standard `setReason` / `setSimulatorStatus`.
- Uses **end-vertex Z** (`p.vez`). No primary-particle guard yet.

### Configurable plugin properties

| Property             | Member   | Default | Units |
|----------------------|----------|---------|-------|
| `ForwardZMax`        | `m_zMax` | 5000.0  | mm    |
| `ForwardMomentumMin` | `m_pMin` | 100.0   | MeV   |

Declared via `declareProperty(...)` in the constructor, so they can be set
from ddsim/npsim steering like any other Geant4Action property.

## Follow-ups / open items

- Optionally protect primaries with a `G4PARTICLE_PRIMARY` guard.
- Decide start-vertex (`vsz`) vs end-vertex (`vez`) semantics.
- Flip `npsim.py` default to `Geant4TVEicParticleHandler` when ready.
- Build/compile verification still pending.
- Related: `memory/project_lambda_issue.md` — `setReason()` zeroing
  `p.reason` overrides `keepAllParticles` (downstream truth-linking bug,
  independent of volume filtering).
