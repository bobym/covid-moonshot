#!/bin/bash

# Dock COVID Moonshot compounds in parallel

#BSUB -W 3:00
#BSUB -R "rusage[mem=2]"
#BSUB -n 1
#BSUB -R "span[ptile=1]"
#BSUB -q cpuqueue
#BSUB -o %J.london-aggregate.out
#BSUB -J "london-aggregate"

echo "Job $JOBID/$NJOBS"

echo "LSB_HOSTS: $LSB_HOSTS"

source ~/.bashrc

source activate perses

export PREFIX="pyridine_urea"

# Extract sorted docking results
python ../scripts/03-aggregate-docking-results.py --docked $PREFIX-docked --output $PREFIX-docked-justscore.csv --clean
python ../scripts/03-aggregate-docking-results.py --docked $PREFIX-docked --output $PREFIX-docked.csv
python ../scripts/03-aggregate-docking-results.py --docked $PREFIX-docked --output $PREFIX-docked.sdf
python ../scripts/03-aggregate-docking-results.py --docked $PREFIX-docked --output $PREFIX-docked.pdb

# Coalesce RUNs for FAH
#python ../scripts/04-fah-prep.py --docked $PREFIX-docked --output $PREFIX-fah.csv

# Compute overlap
#python ../scripts/05-score-inspiration-fragment-overlap.py --docked $PREFIX-docked.sdf --output $PREFIX-docked-overlap --clean