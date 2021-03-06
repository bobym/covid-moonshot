from openeye import oechem
from rich.progress import track

"""
Prepare list of annotated compounds for docking

* Aggregate all compound designs
* Annotate by intermediate
* Sort compounds by size
* Interleave compounds by intermediate

"""

mols = list()

# Latest submissions downloaded from PostEra site
# TODO: Auto-download and timestamp
submissions_csv_filename = 'submissions/submissions-2021-01-21.csv'

# Read all submitted designs: Compounds with the key substructure will be retained
print('Reading submitted designs...')
# Drop columns that cause trouble for OpenEye
import pandas as pd
drop_columns = ['Submission Rationale', 'Submission Notes']
df = pd.read_csv(submissions_csv_filename, dtype=str)
df.drop(columns=drop_columns, inplace=True)
import tempfile
with tempfile.NamedTemporaryFile(suffix='.csv') as csv_file:
    df.to_csv(csv_file.name, header=True, index=False)
    # Read file
    with oechem.oemolistream(csv_file.name) as ifs:
        mol = oechem.OEGraphMol()
        while oechem.OEReadMolecule(ifs, mol):
            # Clear SD tags
            oechem.OEClearSDData(mol)
            # Store the molecule
            mols.append(mol.CreateCopy())
print(f'{len(mols)} molecules read')

# Aggregate all compound designs
source_filenames = [
    # Filtered synthetic designs
    'filtered/transformations-final-ligands.csv',
]
for source_filename in source_filenames:
    with oechem.oemolistream(source_filename) as ifs:
        mol = oechem.OEGraphMol()
        while oechem.OEReadMolecule(ifs, mol):
            # Clear SD tags
            oechem.OEClearSDData(mol)
            # Store the molecule
            mols.append(mol.CreateCopy())
print(f'{len(mols)} molecules read')

# Annotate molecules with SMARTS labels
print('Annotating SMARTS labels...')
import csv
labels_filename = 'annotations/benzopyran_annotations.csv' # list of labels for various SMARTS patterns
smarts_labels = dict()
with open(labels_filename, 'r') as csvfile:
    csvreader = csv.reader(csvfile, delimiter=',')
    for row in csvreader:
        smarts = row[0]
        label = row[1]
        smarts_labels[smarts] = label
# Label the molecules
for smarts, label in smarts_labels.items():
    ss = oechem.OESubSearch(smarts)
    for mol in track(mols, description=label):
        oechem.OEPrepareSearch(mol, ss)
        if ss.SingleMatch(mol):
            oechem.OESetSDData(mol, 'intermediate', label)
# Discard molecules without labels
mols = [ mol for mol in mols if oechem.OEHasSDData(mol, 'intermediate') ]
print(f'{len(mols)} molecules remain after discarding unlabeled molecules')

# Write molecules
output_filename = 'sorted/sprint-5-dimer.csv'
with oechem.oemolostream(output_filename) as ofs:
    for mol in track(mols, description='Writing molecules...'):
        oechem.OEWriteMolecule(ofs, mol)
