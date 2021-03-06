from openeye import oechem
from rich.progress import track

"""
Prepare list of annotated compounds for docking

* Aggregate all compound designs
* Annotate by intermediate
* Sort compounds by size
* Interleave compounds by intermediate

"""

# Latest submissions downloaded from PostEra site
# TODO: Auto-download and timestamp
submissions_csv_filename = 'submissions/submissions-2020-11-14.csv'

# Aggregate all compound designs
source_filenames = [
    # Filtered synthetic designs
    'filtered/filtered_alkyl_halide_bb_ether_synthesis_for_FEP.smi',
    'filtered/filtered_amine_bb_amide_couplings_for_FEP.smi',
    'filtered/filtered_cooh_bb_amide_couplings_for_FEP.smi',
]
mols = list()
for source_filename in source_filenames:
    with open(source_filename, 'rt') as infile:
        for line in track(infile.readlines(), description=f'Reading {source_filename}'):
            smiles, title, _, demerits, reason_for_demerits = line.split()
            mol = oechem.OEGraphMol()
            oechem.OESmilesToMol(mol, smiles)
            mol.SetTitle(title)
            oechem.OESetSDData(mol, 'demerits', demerits)
            oechem.OESetSDData(mol, 'reason_for_demerits', reason_for_demerits)
            mols.append(mol)
print(f'{len(mols)} molecules read')

# Read all submitted designs: Compounds with the key substructure will be retained
print('Reading submitted designs...')
# Drop columns that cause trouble for OpenEye
import pandas as pd
drop_columns = ['Submission Rationale', 'Submission Notes']
df = pd.read_csv(submissions_csv_filename)
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

# Annotate molecules with SMARTS labels
print('Annotating SMARTS labels...')
import csv
labels_filename = 'intermediates/benzopyran_sprint_5_intermediates.csv' # list of labels for various SMARTS patterns
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

# Sort molecules by size
#print('Sorting molecules by number of atoms...')
#mols.sort(key=lambda mol : mol.NumAtoms())
print('Sorting molecules by molecular weight...')
mols.sort(key=lambda mol : oechem.OECalculateMolecularWeight(mol))

# Interleave molecules by intermediate category
print('Interleaving molecules by intermediate...')
mols_by_label = { label : list() for label in smarts_labels.values() }
for mol in mols:
    label = oechem.OEGetSDData(mol, 'intermediate')
    mols_by_label[label].append(mol)
nmols_to_assign = len(mols)
mols = list()
while (nmols_to_assign > 0):
    for label in mols_by_label.keys():
        if len(mols_by_label[label]) > 0:
            mols.append(mols_by_label[label].pop(0))
            nmols_to_assign -= 1

# Move important molecules to the beginning
print('Moving important molecules to the beginning...')
important_molecules_titles = [
    # Lead compounds
    'ALP-POS-477dc5b7-3',
    'EDJ-MED-e4b030d8-13'
    'MAT-POS-b3e365b9-1',
    'EDJ-MED-e4b030d8-11',
    'EDJ-MED-e4b030d8-2',
    'MAT-POS-0c8fa4a7-1',
    'EDJ-MED-e4b030d8-13',
    'ALP-POS-477dc5b7-1',
    'VLA-UCB-1dbca3b4-15',
    'MAT-POS-8a69d52e-2',
    'MAT-POS-11b63608-1',
    'MAT-POS-8a69d52e-7',
    'EDJ-MED-e4b030d8-8',
    'ALP-POS-477dc5b7-2',
    'ALP-POS-3b848b35-2',
    'ALP-POS-477dc5b7-3',
    ]

important_molecules = [ mol for mol in mols if mol.GetTitle() in important_molecules_titles ]
less_important_molecules = [ mol for mol in mols if mol.GetTitle() not in important_molecules_titles ]
mols = important_molecules + less_important_molecules

# Write molecules
output_filename = 'sorted/sprint-5.csv'
with oechem.oemolostream(output_filename) as ofs:
    for mol in track(mols, description='Writing molecules...'):
        oechem.OEWriteMolecule(ofs, mol)
