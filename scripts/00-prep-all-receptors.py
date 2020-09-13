"""
Prepare all SARS-CoV-2 Mpro structures for docking and simulation in monomer and dimer forms

This should be run from the covid-moonshot/scripts directory

"""
import rich
import openeye

structures_path = '../structures'
output_basepath = '../receptors'

def download_url(url, save_path, chunk_size=128):
    """
    Download file from the specified URL to the specified file path, creating base dirs if needed.
    """
    # Create directory
    import os
    base_path, filename = os.path.split(save_path)
    os.makedirs(base_path, exist_ok=True)
    # Download
    from rich.progress import track
    import requests
    r = requests.get(url, stream=True)
    with open(save_path, 'wb') as fd:
        nchunks = int(r.headers['Content-Length'])/chunk_size
        for chunk in track(r.iter_content(chunk_size=chunk_size), 'Downloading ZIP archive of Mpro structures...', total=nchunks):
            fd.write(chunk)

def read_pdb_file(pdb_file):
    #print(f'Reading receptor from {pdb_file}...')

    from openeye import oechem
    ifs = oechem.oemolistream()
    ifs.SetFlavor(oechem.OEFormat_PDB, oechem.OEIFlavor_PDB_Default | oechem.OEIFlavor_PDB_DATA | oechem.OEIFlavor_PDB_ALTLOC)  # noqa

    if not ifs.open(pdb_file):
        oechem.OEThrow.Fatal("Unable to open %s for reading." % pdb_file)

    mol = oechem.OEGraphMol()
    if not oechem.OEReadMolecule(ifs, mol):
        oechem.OEThrow.Fatal("Unable to read molecule from %s." % pdb_file)
    ifs.close()

    return (mol)

def prepare_receptor(complex_pdb_filename, output_basepath, dimer=False, retain_water=False):
    """
    Parameters
    ----------
    complex_pdb_filename : str
        The complex PDB file to read in
    output_basepath : str
        Base path for output
    dimer : bool, optional, default=False
        If True, generate the dimer as the biological unit
    retain_water : bool, optional, default=False
        If True, will retain waters
    """
    # Check whether this is a diamond SARS-CoV-2 Mpro structure or not
    import re
    is_diamond_structure = (re.search('-x\d+_', complex_pdb_filename) is not None)

    import os
    basepath, filename = os.path.split(complex_pdb_filename)
    prefix, extension = os.path.splitext(filename)
    prefix = os.path.join(output_basepath, prefix)

    # Check if receptor already exists
    receptor_filename = f'{prefix}-receptor.oeb.gz'
    thiolate_receptor_filename = f'{prefix}-receptor-thiolate.oeb.gz'
    if os.path.exists(receptor_filename) and os.path.exists(thiolate_receptor_filename):
        return

    # Read in PDB file
    pdbfile_lines = [ line for line in open(complex_pdb_filename, 'r') if 'UNK' not in line ]

    # If monomer is specified, drop crystal symmetry lines
    if not dimer:
        pdbfile_lines = [ line for line in pdbfile_lines if 'REMARK 350' not in line ]

    # Filter out waters
    if not retain_water:
        pdbfile_lines = [ line for line in pdbfile_lines if 'HOH' not in line ]

    # Filter out LINK records to covalent inhibitors so we can model non-covalent complex
    pdbfile_lines = [ line for line in pdbfile_lines if 'LINK' not in line ]

    # Reconstruct PDBFile contents
    pdbfile_contents = ''.join(pdbfile_lines)

    # Append SEQRES to fragment structures if this is a Diamond SARS-CoV-2 Mpro structure
    seqres = """\
SEQRES   1 A  306  SER GLY PHE ARG LYS MET ALA PHE PRO SER GLY LYS VAL
SEQRES   2 A  306  GLU GLY CYS MET VAL GLN VAL THR CYS GLY THR THR THR
SEQRES   3 A  306  LEU ASN GLY LEU TRP LEU ASP ASP VAL VAL TYR CYS PRO
SEQRES   4 A  306  ARG HIS VAL ILE CYS THR SER GLU ASP MET LEU ASN PRO
SEQRES   5 A  306  ASN TYR GLU ASP LEU LEU ILE ARG LYS SER ASN HIS ASN
SEQRES   6 A  306  PHE LEU VAL GLN ALA GLY ASN VAL GLN LEU ARG VAL ILE
SEQRES   7 A  306  GLY HIS SER MET GLN ASN CYS VAL LEU LYS LEU LYS VAL
SEQRES   8 A  306  ASP THR ALA ASN PRO LYS THR PRO LYS TYR LYS PHE VAL
SEQRES   9 A  306  ARG ILE GLN PRO GLY GLN THR PHE SER VAL LEU ALA CYS
SEQRES  10 A  306  TYR ASN GLY SER PRO SER GLY VAL TYR GLN CYS ALA MET
SEQRES  11 A  306  ARG PRO ASN PHE THR ILE LYS GLY SER PHE LEU ASN GLY
SEQRES  12 A  306  SER CYS GLY SER VAL GLY PHE ASN ILE ASP TYR ASP CYS
SEQRES  13 A  306  VAL SER PHE CYS TYR MET HIS HIS MET GLU LEU PRO THR
SEQRES  14 A  306  GLY VAL HIS ALA GLY THR ASP LEU GLU GLY ASN PHE TYR
SEQRES  15 A  306  GLY PRO PHE VAL ASP ARG GLN THR ALA GLN ALA ALA GLY
SEQRES  16 A  306  THR ASP THR THR ILE THR VAL ASN VAL LEU ALA TRP LEU
SEQRES  17 A  306  TYR ALA ALA VAL ILE ASN GLY ASP ARG TRP PHE LEU ASN
SEQRES  18 A  306  ARG PHE THR THR THR LEU ASN ASP PHE ASN LEU VAL ALA
SEQRES  19 A  306  MET LYS TYR ASN TYR GLU PRO LEU THR GLN ASP HIS VAL
SEQRES  20 A  306  ASP ILE LEU GLY PRO LEU SER ALA GLN THR GLY ILE ALA
SEQRES  21 A  306  VAL LEU ASP MET CYS ALA SER LEU LYS GLU LEU LEU GLN
SEQRES  22 A  306  ASN GLY MET ASN GLY ARG THR ILE LEU GLY SER ALA LEU
SEQRES  23 A  306  LEU GLU ASP GLU PHE THR PRO PHE ASP VAL VAL ARG GLN
SEQRES  24 A  306  CYS SER GLY VAL THR PHE GLN
"""
    if is_diamond_structure:
        #print('Prepending SEQRES')
        pdbfile_contents = seqres + pdbfile_contents

    # Read the receptor and identify design units
    from openeye import oespruce, oechem
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(delete=False, mode='wt', suffix='.pdb') as pdbfile:
        pdbfile.write(pdbfile_contents)
        pdbfile.close()
        complex = read_pdb_file(pdbfile.name)
        # TODO: Clean up

    #het = oespruce.OEHeterogenMetadata()
    #het.SetTitle("LIG")  # real ligand 3 letter code
    #het.SetID("CovMoonShot1234")  # in case you have corporate IDs
    #het.SetType(oespruce.OEHeterogenType_Ligand)
    #   mdata.AddHeterogenMetadata(het)

    #print('Identifying design units...')
    # Produce zero design units if we fail to protonate

    # Log warnings
    errfs = oechem.oeosstream() # create a stream that writes internally to a stream
    oechem.OEThrow.SetOutputStream(errfs)
    oechem.OEThrow.Clear()
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Verbose) # capture verbose error output

    opts = oespruce.OEMakeDesignUnitOptions()
    #print(f'ligand atoms: min {opts.GetSplitOptions().GetMinLigAtoms()}, max {opts.GetSplitOptions().GetMaxLigAtoms()}')

    mdata = oespruce.OEStructureMetadata();
    opts.GetPrepOptions().SetStrictProtonationMode(True);
    if is_diamond_structure:
        # Only cap C-terminus, since N-terminus is biological
        opts.GetPrepOptions().GetBuildOptions().SetCapNTermini(False);
        opts.GetPrepOptions().GetBuildOptions().SetCapCTermini(True);
    design_units = list(oespruce.OEMakeDesignUnits(complex, mdata, opts))

    # Restore error stream
    oechem.OEThrow.SetOutputStream(oechem.oeerr)

    # Capture the warnings to a string
    warnings = errfs.str().decode("utf-8")

    if len(design_units) >= 1:
        design_unit = design_units[0]
        print('')
        print('')
        print(f'{complex_pdb_filename} : SUCCESS')
        print(warnings)
    elif len(design_units) == 0:
        print('')
        print('')
        print(f'{complex_pdb_filename} : FAILURE')
        print(warnings)
        msg = f'No design units found for {complex_pdb_filename}\n'
        msg += warnings
        msg += '\n'
        raise Exception(msg)

    # Prepare the receptor
    #print('Preparing receptor...')
    from openeye import oedocking
    protein = oechem.OEGraphMol()
    design_unit.GetProtein(protein)
    ligand = oechem.OEGraphMol()
    design_unit.GetLigand(ligand)

    receptor = oechem.OEGraphMol()
    oedocking.OEMakeReceptor(receptor, protein, ligand)
    oedocking.OEWriteReceptorFile(receptor, receptor_filename)

    with oechem.oemolostream(f'{prefix}-protein.pdb') as ofs:
        oechem.OEWriteMolecule(ofs, protein)
    with oechem.oemolostream(f'{prefix}-ligand.mol2') as ofs:
        oechem.OEWriteMolecule(ofs, ligand)
    with oechem.oemolostream(f'{prefix}-ligand.pdb') as ofs:
        oechem.OEWriteMolecule(ofs, ligand)
    with oechem.oemolostream(f'{prefix}-ligand.sdf') as ofs:
        oechem.OEWriteMolecule(ofs, ligand)

    # Filter out UNK from PDB files (which have covalent adducts)
    pdbfile_lines = [ line for line in open(f'{prefix}-protein.pdb', 'r') if 'UNK' not in line ]
    with open(f'{prefix}-protein.pdb', 'wt') as outfile:
        outfile.write(''.join(pdbfile_lines))

    # Adjust protonation state of CYS145 to generate thiolate form
    #print('Deprotonating CYS145...')
    pred = oechem.OEAtomMatchResidue(["CYS:145: :A"])
    for atom in protein.GetAtoms(pred):
        if oechem.OEGetPDBAtomIndex(atom) == oechem.OEPDBAtomName_SG:
            oechem.OESuppressHydrogens(atom)
            atom.SetFormalCharge(-1)
            atom.SetImplicitHCount(0)
    # Adjust protonation states
    #print('Re-optimizing hydrogen positions...')
    place_hydrogens_opts = oechem.OEPlaceHydrogensOptions()
    place_hydrogens_opts.SetBypassPredicate(pred)
    protonate_opts = oespruce.OEProtonateDesignUnitOptions(place_hydrogens_opts)
    success = oespruce.OEProtonateDesignUnit(design_unit, protonate_opts)
    design_unit.GetProtein(protein)

    # Old hacky way to adjust protonation states
    #opts = oechem.OEPlaceHydrogensOptions()
    #opts.SetBypassPredicate(pred)
    #describe = oechem.OEPlaceHydrogensDetails()
    #success = oechem.OEPlaceHydrogens(protein, describe, opts)
    #if success:
    #    oechem.OEUpdateDesignUnit(design_unit, protein, oechem.OEDesignUnitComponents_Protein)

    # Write thiolate form of receptor
    receptor = oechem.OEGraphMol()
    oedocking.OEMakeReceptor(receptor, protein, ligand)
    oedocking.OEWriteReceptorFile(receptor, thiolate_receptor_filename)

    with oechem.oemolostream(f'{prefix}-protein-thiolate.pdb') as ofs:
        oechem.OEWriteMolecule(ofs, protein)

    # Filter out UNK from PDB files (which have covalent adducts)
    pdbfile_lines = [ line for line in open(f'{prefix}-protein-thiolate.pdb', 'r') if 'UNK' not in line ]
    with open(f'{prefix}-protein-thiolate.pdb', 'wt') as outfile:
        outfile.write(''.join(pdbfile_lines))


if __name__ == '__main__':
    # Prep all receptors
    import glob, os

    # Be quiet
    from openeye import oechem
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Quiet)
    #oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Error)

    if not os.path.exists(structures_path):
        # Download ZIP file
        url = 'https://fragalysis.diamond.ac.uk/media/targets/Mpro.zip'
        zip_path = os.path.join(structures_path, 'Mpro.zip')
        download_url(url, zip_path)
        # Unpack ZIP file
        from zipfile import ZipFile
        with ZipFile(zip_path, 'r') as zip_obj:
           zip_obj.extractall(structures_path)

    # Get list of all PDB files to prep
    source_pdb_files = glob.glob(os.path.join(structures_path, "aligned/Mpro-*_0/Mpro-*_0_bound.pdb"))

    # Create output directory
    os.makedirs(output_basepath, exist_ok=True)

    for dimer in [True, False]:
        if dimer:
            output_basepath = '../receptors/dimer'
        else:
            output_basepath = '../receptors/monomer'

        os.makedirs(output_basepath, exist_ok=True)

        def prepare_receptor_wrapper(complex_pdb_file):
            try:
                prepare_receptor(complex_pdb_file, output_basepath, dimer=dimer)
            except Exception as e:
                #print(e)
                pass

        # DEBUG:
        #for source_pdb_file in source_pdb_files:
        #    print(source_pdb_file)
        #    prepare_receptor_wrapper(source_pdb_file)
        #    print('')
        #stop

        # Process all receptors in parallel
        from multiprocessing import Pool
        from rich.progress import Progress
        with Pool() as pool:
            with Progress() as progress:
                task = progress.add_task('[green]Sprucing structures...', total=len(source_pdb_files))
                for i, _ in enumerate(pool.imap_unordered(prepare_receptor_wrapper, source_pdb_files)):
                    progress.update(task, advance=1)
