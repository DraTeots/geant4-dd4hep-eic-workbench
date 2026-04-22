# geant4-dd4hep-eic-workbench

npsim commands: 

```bash
time -v npsim --compactFile=$DETECTOR_PATH/epic_craterlake_10x100.xml --runType run --inputFiles {input_file} --outputFile {output_file} --numberOfEvents 5000 2>&1

# keep all
time -v npsim -compactFile=$DETECTOR_PATH/epic_craterlake_10x100.xml --part.keepAllParticles=true --runType run --inputFiles {input_file} --outputFile {output_file} --numberOfEvents 5000 2>&1
time -v npsim \
     --compactFile=$DETECTOR_PATH/epic_craterlake_10x100.xml \
     --part.keepAllParticles=true \
     --runType run \
     --inputFiles /data/afterburner/10x100-priority/k_lambda_10x100_5000evt_0001.afterburner.hepmc \
     --outputFile /data/k_lambda_10x100_5000evt_0001.edm4hep.root \
     --numberOfEvents 5000 2>&1
```