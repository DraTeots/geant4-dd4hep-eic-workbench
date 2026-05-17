import ROOT
ROOT.gSystem.Load("libDDCore")
ROOT.gSystem.Load("libDDG4")

description = ROOT.dd4hep.Detector.getInstance()
description.fromXML("/app/epic/share/epic/epic.xml")

# Get the TGeo manager and export full geometry (incl. parallel worlds)
mgr = description.manager()
mgr.Export("tracking_pw.root")
print("Exported to tracking_pw_wrong.root")

# List all volumes to find the parallel world tracking volume
print("\nSearching for tracking_volume...")
vols = mgr.GetListOfVolumes()
for i in range(vols.GetEntries()):
    v = vols.At(i)
    if "tracking" in v.GetName().lower():
        print(f"  Found: {v.GetName()}")
