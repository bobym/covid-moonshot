#!/usr/bin/env python

"""
Generate poses for relative free energy calculations using fragment structures

"""
from openeye import oechem
import numpy as np


def GetFragments(mol, minbonds, maxbonds):
    from openeye import oegraphsim
    frags = []
    fptype = oegraphsim.OEGetFPType("Tree,ver=2.0.0,size=4096,bonds=%d-%d,atype=AtmNum,btype=Order"
                                    % (minbonds, maxbonds))

    for abset in oegraphsim.OEGetFPCoverage(mol, fptype, True):
        fragatompred = oechem.OEIsAtomMember(abset.GetAtoms())

        frag = oechem.OEGraphMol()
        adjustHCount = True
        oechem.OESubsetMol(frag, mol, fragatompred, adjustHCount)
        oechem.OEFindRingAtomsAndBonds(frag)
        frags.append(oechem.OEGraphMol(frag))

    return frags


def GetCommonFragments(mollist, frags,
                       atomexpr=oechem.OEExprOpts_DefaultAtoms,
                       bondexpr=oechem.OEExprOpts_DefaultBonds):

    corefrags = []

    from rich.progress import track
    #for frag in track(frags, description='Finding common fragments'):
    for frag in frags:
        ss = oechem.OESubSearch(frag, atomexpr, bondexpr)
        if not ss.IsValid():
            print('Is not valid')
            continue

        validcore = True
        for mol in mollist:
            oechem.OEPrepareSearch(mol, ss)
            validcore = ss.SingleMatch(mol)
            if not validcore:
                break

        if validcore:
            corefrags.append(frag)

    return corefrags


def GetCoreFragment(refmol, mols,
                    minbonds=3, maxbonds=200,
                    atomexpr=oechem.OEExprOpts_DefaultAtoms,
                    bondexpr=oechem.OEExprOpts_DefaultBonds):

    #print("Number of molecules = %d" % len(mols))

    frags = GetFragments(refmol, minbonds, maxbonds)
    if len(frags) == 0:
        oechem.OEThrow.Error("No fragment is enumerated with bonds %d-%d!" % (minbonds, maxbonds))

    commonfrags = GetCommonFragments(mols, frags, atomexpr, bondexpr)
    if len(commonfrags) == 0:
        oechem.OEThrow.Error("No common fragment is found!")

    #print("Number of common fragments = %d" % len(commonfrags))

    core = None
    for frag in commonfrags:
        if core is None or GetFragmentScore(core) < GetFragmentScore(frag):
            core = frag

    return core

def GetFragmentScore(mol):

    score = 0.0
    score += 2.0 * oechem.OECount(mol, oechem.OEAtomIsInRing())
    score += 1.0 * oechem.OECount(mol, oechem.OENotAtom(oechem.OEAtomIsInRing()))

    return score

def expand_stereochemistry(mols):
    """Expand stereochemistry when uncertain

    Parameters
    ----------
    mols : openeye.oechem.OEGraphMol
        Molecules to be expanded

    Returns
    -------
    expanded_mols : openeye.oechem.OEMol
        Expanded molecules
    """
    expanded_mols = list()

    from openeye import oechem, oeomega
    omegaOpts = oeomega.OEOmegaOptions()
    omega = oeomega.OEOmega(omegaOpts)
    maxcenters = 12
    forceFlip = False
    enumNitrogen = True
    warts = True # add suffix for stereoisomers
    for mol in mols:
        compound_title = mol.GetTitle()
        for enantiomer in oeomega.OEFlipper(mol, maxcenters, forceFlip, enumNitrogen, warts):
            enantiomer = oechem.OEMol(enantiomer)
            oechem.OESetSDData(enantiomer, 'compound', compound_title)
            expanded_mols.append(enantiomer)

    return expanded_mols

class BumpCheck:
    def __init__(self, prot_mol, cutoff=2.0):
        self.near_nbr = oechem.OENearestNbrs(prot_mol, cutoff)
        self.cutoff = cutoff

    def count(self, lig_mol):
        bump_count = 0
        for nb in self.near_nbr.GetNbrs(lig_mol):
            if (not nb.GetBgn().IsHydrogen()) and (not nb.GetEnd().IsHydrogen()):
                bump_count += np.exp(-0.5 * (nb.GetDist() / self.cutoff)**2)
        return bump_count

def mmff_energy(mol):
    """
    Compute MMFF energy

    """
    from openeye import oechem, oeff
    mol = oechem.OEGraphMol(mol)
    mmff = oeff.OEMMFF()
    if not mmff.PrepMol(mol) or not mmff.Setup(mol):
        oechem.OEThrow.Warning("Unable to process molecule: title = '%s'" % mol.GetTitle())
        return None

    vecCoords = oechem.OEDoubleArray(3*mol.GetMaxAtomIdx())
    mol.GetCoords(vecCoords)
    energy = mmff(vecCoords)
    return energy

def generate_restricted_conformers(receptor, refmol, mol, core_smarts=None):
    """
    Generate and select a conformer of the specified molecule using the reference molecule

    Parameters
    ----------
    receptor : openeye.oechem.OEGraphMol
        Receptor (already prepped for docking) for identifying optimal pose
    refmol : openeye.oechem.OEGraphMol
        Reference molecule which shares some part in common with the proposed molecule
    mol : openeye.oechem.OEGraphMol
        Molecule whose conformers are to be enumerated
    core_smarts : str, optional, default=None
        If core_smarts is specified, substructure will be extracted using SMARTS.
    """
    from openeye import oechem, oeomega

    # DEBUG
    #core_smarts = 'C1(CCOc2ccccc12)C(=O)Nc1cncc2ccccc12' # benzopyran-linker-isoquinoline
    #core_smarts = 'C(=O)Nc1cncc2ccccc12' # linker-isoquinoline

    # Get core fragment
    if core_smarts:
        # Truncate refmol to SMARTS if specified
        #print(f'Trunctating using SMARTS {refmol_smarts}')
        ss = oechem.OESubSearch(core_smarts)
        oechem.OEPrepareSearch(refmol, ss)
        for match in ss.Match(refmol):
            core_fragment = oechem.OEGraphMol()
            oechem.OESubsetMol(core_fragment, match)
            break
        #print(f'refmol has {refmol.NumAtoms()} atoms')
    else:
        core_fragment = GetCoreFragment(refmol, [mol])
        oechem.OESuppressHydrogens(core_fragment)
        #print(f'  Core fragment has {core_fragment.NumAtoms()} heavy atoms')
        MIN_CORE_ATOMS = 6
        if core_fragment.NumAtoms() < MIN_CORE_ATOMS:
            return None

    # Create an Omega instance
    #omegaOpts = oeomega.OEOmegaOptions()
    omegaOpts = oeomega.OEOmegaOptions(oeomega.OEOmegaSampling_Dense)

    # Set the fixed reference molecule
    omegaFixOpts = oeomega.OEConfFixOptions()
    omegaFixOpts.SetFixMaxMatch(10) # allow multiple MCSS matches
    omegaFixOpts.SetFixDeleteH(True) # only use heavy atoms
    omegaFixOpts.SetFixMol(core_fragment)
    #omegaFixOpts.SetFixSmarts(smarts)
    omegaFixOpts.SetFixRMS(0.5)

    # This causes a warning:
    #Warning: OESubSearch::Match() is unable to match unset hybridization in the target (EN300-221518_3_1) for patterns with set hybridization, call OEPrepareSearch on the target first
    #atomexpr = oechem.OEExprOpts_Aromaticity | oechem.OEExprOpts_Hybridization

    atomexpr = oechem.OEExprOpts_Aromaticity | oechem.OEExprOpts_AtomicNumber
    bondexpr = oechem.OEExprOpts_BondOrder | oechem.OEExprOpts_Aromaticity
    omegaFixOpts.SetAtomExpr(atomexpr)
    omegaFixOpts.SetBondExpr(bondexpr)
    omegaOpts.SetConfFixOptions(omegaFixOpts)

    molBuilderOpts = oeomega.OEMolBuilderOptions()
    molBuilderOpts.SetStrictAtomTypes(False) # don't give up if MMFF types are not found
    omegaOpts.SetMolBuilderOptions(molBuilderOpts)

    omegaOpts.SetWarts(False) # expand molecule title
    omegaOpts.SetStrictStereo(False) # set strict stereochemistry
    omegaOpts.SetIncludeInput(False) # don't include input
    omegaOpts.SetMaxConfs(1000) # generate lots of conformers
    #omegaOpts.SetEnergyWindow(10.0) # allow high energies
    omega = oeomega.OEOmega(omegaOpts)

    # TODO: Expand protonation states and tautomers
    from openeye import oequacpac
    if not oequacpac.OEGetReasonableProtomer(mol):
        print('No reasonable protomer found')
        return None

    mol = oechem.OEMol(mol) # multi-conformer molecule

    ret_code = omega.Build(mol)
    if (mol.GetDimension() != 3) or (ret_code != oeomega.OEOmegaReturnCode_Success):
        print(f'Omega failure: {mol.GetDimension()} and {oeomega.OEGetOmegaError(ret_code)}')
        return None

    # Extract poses
    class Pose(object):
        def __init__(self, conformer):
            self.conformer = conformer
            self.clash_score = None
            self.docking_score = None
            self.overlap_score = None

    poses = [ Pose(conf) for conf in mol.GetConfs() ]

    # Score clashes
    bump_check = BumpCheck(receptor)
    for pose in poses:
        pose.clash_score = bump_check.count(pose.conformer)

    # Score docking poses
    from openeye import oedocking
    score = oedocking.OEScore(oedocking.OEScoreType_Chemgauss4)
    score.Initialize(receptor)
    for pose in poses:
        pose.docking_score = score.ScoreLigand(pose.conformer)

    # Compute overlap scores
    from openeye import oeshape
    overlap_prep = oeshape.OEOverlapPrep()
    overlap_prep.Prep(refmol)
    shapeFunc = oeshape.OEExactShapeFunc()
    shapeFunc.SetupRef(refmol)
    oeshape_result = oeshape.OEOverlapResults()
    for pose in poses:
        tmpmol = oechem.OEGraphMol(pose.conformer)
        overlap_prep.Prep(tmpmol)
        shapeFunc.Overlap(tmpmol, oeshape_result)
        pose.overlap_score = oeshape_result.GetRefTversky()

    # Filter poses based on top 10% of overlap
    poses = sorted(poses, key= lambda pose : pose.overlap_score)
    poses = poses[int(0.9*len(poses)):]

    # Select the best docking score
    import numpy as np
    poses = sorted(poses, key=lambda pose : pose.docking_score)
    pose = poses[0]
    mol.SetActive(pose.conformer)
    oechem.OESetSDData(mol, 'clash_score', str(pose.clash_score))
    oechem.OESetSDData(mol, 'docking_score', str(pose.docking_score))
    oechem.OESetSDData(mol, 'overlap_score', str(pose.overlap_score))

    # Convert to single-conformer molecule
    mol = oechem.OEGraphMol(mol)

    # Compute MMFF energy
    energy = mmff_energy(mol)
    oechem.OESetSDData(mol, 'MMFF_internal_energy', str(energy))

    return mol

def has_ic50(mol):
    """Return True if this molecule has fluorescence IC50 data"""
    from openeye import oechem
    try:
        pIC50 = oechem.OEGetSDData(mol, 'f_avg_pIC50')
        pIC50 = float(pIC50)
        return True
    except Exception as e:
        return False

# TODO: import this from https://github.com/postera-ai/COVID_moonshot_submissions/blob/master/lib/utils.py
def get_series(mol):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import Descriptors
    series_SMARTS_dict = {
        #"3-aminopyridine": "[R1][C,N;R0;!$(NC(=O)CN)]C(=O)[C,N;R0;!$(NC(=O)CN)][c]1cnccc1",
        "3-aminopyridine-like": "[R1]!@[C,N]C(=O)[C,N]!@[R1]",
        "3-aminopyridine-strict": "c1ccncc1NC(=O)!@[R1]",
        "Ugi": "[c,C:1][C](=[O])[N]([c,C,#1:2])[C]([c,C,#1:3])([c,C,#1:4])[C](=[O])[NH1][c,C:5]",
        "quinolones": "NC(=O)c1cc(=O)[nH]c2ccccc12",
        "piperazine-chloroacetamide": "O=C(CCl)N1CCNCC1",
        #'benzotriazoles': 'c1ccc(NC(=O)[C,N]n2nnc3ccccc32)cc1',
        #'benzotriazoles': 'a1aaa([C,N]C(=O)[C,N]a2aaa3aaaaa32)aa1',
        'benzotriazoles': 'a2aaa3aaaaa32',
    }

    smi = oechem.OECreateSmiString(mol)

    # Filter out covalent
    try:
        if oechem.OEGetSDData(mol,'acrylamide')=='True' or oechem.OEGetSDData(mol,'chloroacetamide')=='True':
            return None
    except Exception as e:
        print(e)

    def check_if_smi_in_series(
        smi, SMARTS, MW_cutoff=550, num_atoms_cutoff=70, num_rings_cutoff=10
    ):
        mol = Chem.MolFromSmiles(smi)
        MW = Chem.Descriptors.MolWt(mol)
        num_heavy_atoms = mol.GetNumHeavyAtoms()
        num_rings = Chem.rdMolDescriptors.CalcNumRings(mol)
        patt = Chem.MolFromSmarts(SMARTS)
        if (
            (
                len(
                    Chem.AddHs(Chem.MolFromSmiles(smi)).GetSubstructMatches(
                        patt
                    )
                )
                > 0
            )
            and (MW <= MW_cutoff)
            and (num_heavy_atoms <= num_atoms_cutoff)
            and (num_rings <= num_rings_cutoff)
        ):
            return True
        else:
            return False

    for series in series_SMARTS_dict:
        series_SMARTS = series_SMARTS_dict[series]
        if series == "3-amonipyridine-like":
            if check_if_smi_in_series(
                smi,
                series_SMARTS,
                MW_cutoff=410,
                num_rings_cutoff=3,
                num_atoms_cutoff=28,
            ):
                return series
        else:
            if check_if_smi_in_series(smi, series_SMARTS):
                return series
    return None

#def generate_restricted_conformers_star(args):
#    return generate_restricted_conformers(*args)

def generate_restricted_conformers_star(args):
    core_smarts_list = [
        'C1(CCOc2ccccc12)C(=O)Nc1cncc2ccccc12', # benzopyran-linker-isoquinoline
        'C(=O)Nc1cncc2ccccc12', # linker-isoquinoline
    ]

    mols = [ generate_restricted_conformers(*args, core_smarts=core_smarts) for core_smarts in core_smarts_list ]

    # Sprint 5 special: Select unproblematic enantiomers by energy
    if mols[1] is None:
        return mols[0]

    try:
        from openeye import oechem
        energies = [ float(oechem.OEGetSDData(mol, 'MMFF_internal_energy')) for mol in mols ]
        if energies[0] > energies[1] + 100:
            return mols[1]
        else:
            return mols[0]
    except Exception as e:
        print(e)
        return None


def generate_poses(receptor, refmol, target_molecules, output_filename):
    """
    Parameters
    ----------
    receptor : openeye.oechem.OEGraphMol
        Receptor (already prepped for docking) for identifying optimal pose
    refmol : openeye.oechem.OEGraphMol
        Reference molecule which shares some part in common with the proposed molecule
    target_molecules : list of OEMol
        List of molecules to build
    output_filename : str
        Output filename for generated conformers
    """
    # Expand uncertain stereochemistry
    print('Expanding uncertain stereochemistry...')
    target_molecules = expand_stereochemistry(target_molecules)
    print(f'  There are {len(target_molecules)} target molecules')

    # TODO: Expand protonation states

    # Identify optimal conformer for each molecule
    with oechem.oemolostream(output_filename) as ofs:
        from rich.progress import track
        from multiprocessing import Pool
        from tqdm import tqdm

        pool = Pool()
        args = [ (receptor, refmol, mol) for mol in target_molecules ]
        for pose in track(pool.imap_unordered(generate_restricted_conformers_star, args), total=len(args), description='Enumerating conformers...'):
        #for pose in map(generate_restricted_conformers_star, args): # DEBUG
            if pose is not None:
                oechem.OEWriteMolecule(ofs, pose)
        pool.close()
        pool.join()

        #for mol in tqdm(target_molecules):
        #    pose = generate_restricted_conformers(receptor, core_fragment, mol)
        #    if pose is not None:
        #        oechem.OEWriteMolecule(ofs, pose)

def annotate_with_assay_data(mols, assay_data_filename):
    """
    Annotate the set of molecules with activity data using SD tags

    Parameters
    ----------
    mols : list of OEMol
        List of molecules to annotate
    assay_data_filename
        Filename of CSV file containing activity data
    """
    # Load assay data
    assayed_molecules = dict()
    with oechem.oemolistream(assay_data_filename) as ifs:
        for mol in ifs.GetOEGraphMols():
            assayed_molecules[mol.GetTitle()] = oechem.OEGraphMol(mol)
    print(f'Loaded data for {len(assayed_molecules)} assayed molecules')

    # Copy all SDData from assayed molecules that match title
    nmols_with_assay_data = 0
    for mol in mols:
        if mol.GetTitle() in assayed_molecules:
            assayed_molecule = assayed_molecules[mol.GetTitle()]
            oechem.OECopySDData(mol, assayed_molecule)
            nmols_with_assay_data += 1

    print(f'Found assay data for {nmols_with_assay_data} / {len(mols)} molecules')

def filter_by_series(mols, filter_series='3-aminopyridine-like'):
    """
    Filter series and include only those that include the required scaffold

    Parameters
    ----------
    mols : list of OEMol
        List of molecules to be filtered

    Returns
    -------
    filtered_mols : list of OEMol
        Filtered list of molecules that match series
    """
    filtered_mols = [ mol for mol in mols if (get_series(mol) == filter_series) ]
    print(f'Filtering by series {filter_series} retains {len(filtered_mols)} / {len(mols)} molecules.')
    return filtered_mols

def filter_by_IC50s(mols):
    """
    Retain only molecules with IC50s
    """
    filtered_mols = [ mol for mol in mols if has_ic50(mol) ]
    print(f'Filtering only molecules with IC50s retains {len(filtered_mols)} / {len(mols)} molecules.')
    return filtered_mols

def load_molecules(filename):
    """
    Read molecules from the specified file

    Parameters
    ----------
    filename : str
        The file name from which to read molecules in a format that OpenEye supports

    Returns
    -------
    target_molecules : list of OEMol
        The list of molecules read (without conformers if none were provided in file)
    """
    from openeye import oechem
    target_molecules = list()
    with oechem.oemolistream(target_molecules_filename) as ifs:
        for mol in ifs.GetOEGraphMols():
            # Store a copy
            target_molecules.append( oechem.OEGraphMol(mol) )

    return target_molecules

def load_fragment(fragid, title=None):
    """
    Load the molecule associated with the given fragment

    Parameters
    ----------
    fragid : str
        The XChem fragment ID to load
    title : str, optional, default=None
        If not None, replace title with specified string.

    Returns
    -------
    refmol : OEMol
        The loaded fragment molecules as an OEMol (with coordinates)

    """
    refmol_filename = f'../../receptors/monomer/Mpro-{fragid}_0A_bound-ligand.mol2'
    refmol = None
    with oechem.oemolistream(refmol_filename) as ifs:
        for mol in ifs.GetOEGraphMols():
            refmol = mol
            break
    if refmol is None:
        raise Exception(f'Could not read {refmol_filename}')
    print(f'Reference molecule has {refmol.NumAtoms()} atoms')

    if title is not None:
        # Replace title
        refmol.SetTitle(title)

    return refmol

def prepend_fragment_molecules(mols, fragments):
    """
    Prepend fragment molecules if they don't already exist in the list of molecules

    Parameters
    ----------
    mols : list of OEMol
        List of molecules to which fragment molecules are to be prepended
    fragments : dict of str : str
        fragments[fragid] is the PostEra CID of the corresponding fragment
    """
    titles = set([mol.GetTitle() for mol in mols])

    # Insert any molecules that are not found, preserving order
    ninserted = 0
    for fragid, cid in fragments.items():
        if cid not in titles:
            # Add the molecule
            fragment = load_fragment(fragid, title=cid)
            mols.insert(ninserted, fragment)
            ninserted += 1

def write_molecules(mols, filename):
    """
    Write molecules to the specified filename

    Parameters
    ----------
    mols : list of OEMol
        Molecules to write
    filename : str
        The filename to be written to
    """
    with oechem.oemolostream(filename) as ofs:
        for mol in mols:
            oechem.OEWriteMolecule(ofs, oechem.OEGraphMol(mol))

def read_receptor(fragid):
    """
    Read the receptor for the given fragment

    Parameters
    ----------
    fragid : str
        The XChem fragment ID

    Returns
    -------
    receptor : OEReceptor
        The receptor

    """
    from openeye import oechem
    receptor = oechem.OEGraphMol()
    receptor_filename = f'../../receptors/monomer/Mpro-{fragment}_0A_bound-receptor.oeb.gz'
    from openeye import oedocking
    oedocking.OEReadReceptorFile(receptor, receptor_filename)
    print(f'  Receptor has {receptor.NumAtoms()} atoms.')
    return receptor

if __name__ == '__main__':
    #fragment = 'x2646' # TRY-UNI-714a760b-6 (the main amino pyridine core)
    #fragment = 'x10789' # TRY-UNI-2eddb1ff-7 (beta-lactam an chloride)

    # TODO: Figure out why this single-threading workaround is needed to prevent issues
    from openeye import oechem
    #oechem.OESetMemPoolMode(oechem.OEMemPoolMode_SingleThreaded |
    #                        oechem.OEMemPoolMode_UnboundedCache)

    # Assay data
    assay_data_filename = 'activity-data/activity-data-2020-11-02.csv'

    # XChem fragment structures to dock to
    # XChem FragID : PostEra CID
    fragments = {
        'x11498' : 'VLA-UCB-1dbca3b4-15', # XChem FragID : PostEra CID
        'x12073' : 'MAT-POS-8a69d52e-7', # XChem FragID : PostEra CID
        }

    # Molecule sets dock
    # This is just the prefix to pull from f"sorted/{prefix}.csv"
    molecule_sets_to_dock = [
        'sprint-5',
    ]

    for prefix in molecule_sets_to_dock:
        # Read molecules to dock
        target_molecules_filename = 'sorted/' + prefix + f'.csv'
        print(f'Reading molecules to be docked from {target_molecules_filename}...')
        target_molecules = load_molecules(target_molecules_filename)

        # Ensure fragment molecules are contained in set
        prepend_fragment_molecules(target_molecules, fragments)

        # Annotate with assay data
        annotate_with_assay_data(target_molecules, assay_data_filename)

        # Generate list of all compounds
        import os
        os.makedirs('docked', exist_ok=True)
        output_filename = f'docked/{prefix}-compounds.sdf'
        print(f'Writing annotated molecules to {output_filename}...')
        write_molecules(target_molecules, output_filename)

        # Generate docked poses from each fragment:receptor pair
        for fragment in fragments:
            # Read receptor
            print('Reading receptor...')
            receptor = read_receptor(fragment)

            # Read reference fragment with coordinates
            refmol = load_fragment(fragment, title=fragments[fragment])

            # Generate poses for all molecules
            output_filename = f'docked/{prefix}-microstates-{fragment}.sdf'
            print(f'Writing poses to {output_filename}...')
            generate_poses(receptor, refmol, target_molecules, output_filename)
