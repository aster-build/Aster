import json
import pytest
from aster import interactions

# PLIP's own records are namedtuples with per-type fields. These stand in for them
# so the normalisation is tested without the docking environment installed.
class Record:
    def __init__(self,**fields):
        for key,value in fields.items(): setattr(self,key,value)

class Site:
    def __init__(self,**groups):
        for key,value in groups.items(): setattr(self,key,value)

def site():
    return Site(
        hydrophobic_contacts=[Record(restype='PHE',resnr=76,reschain='A',distance=3.84211,type='hydroph_interaction')],
        hbonds_pdon=[Record(restype='SER',resnr=422,reschain='A',distance_ah=2.1004,distance_ad=2.83472,angle=161.4442,protisdon=True,sidechain=True,type='strong')],
        hbonds_ldon=[],
        saltbridge_pneg=[Record(restype='ASP',resnr=79,reschain='A',distance=3.53459,protispos=False)],
        pistacking=[Record(restype='TYR',resnr=156,reschain='A',distance=4.6,angle=12.2,offset=1.3,type='P')],
        metal_complexes=[Record(restype='NA',resnr=705,reschain='A',distance=2.4,target='O',location='ligand',coordination='octahedral',num=6)],
    )

def test_normalise_names_each_interaction_with_its_own_geometry():
    found=interactions.normalise(site())
    kinds=sorted(record['interaction'] for record in found)
    assert kinds==['hydrogen_bond','hydrophobic','metal_complex','pi_stacking','salt_bridge']
    bond=next(r for r in found if r['interaction']=='hydrogen_bond')
    # Geometry is kept as the thresholds that produced it, not as one distance.
    assert bond['donor_acceptor_angstrom']==2.835 and bond['donor_hydrogen_acceptor_angstrom']==2.1
    assert bond['angle_degrees']==161.444 and bond['protein_is_donor'] is True
    assert bond['role']=='protein_donor' and bond['ligand_residue']=='LIG'
    assert all('distance_angstrom' in r or 'donor_acceptor_angstrom' in r for r in found)
    # Every record is JSON-serialisable, because it is stored in result.json.
    json.loads(json.dumps(found))

def test_normalise_ignores_interaction_groups_plip_does_not_report():
    assert interactions.normalise(Site())==[]
    assert interactions.normalise(Site(hbonds_pdon=None))==[]

def test_residues_group_every_kind_touching_one_residue():
    found=interactions.normalise(site())+[{'interaction':'hydrogen_bond','chain':'A','sequence':76,'residue':'PHE'}]
    grouped=interactions.residues(found)
    phe=next(entry for entry in grouped if entry['sequence']==76)
    assert phe['interactions']==['hydrogen_bond','hydrophobic'] and phe['residue']=='PHE'
    assert [entry['sequence'] for entry in grouped]==[76,79,156,422,705]

def test_comparison_separates_proximity_from_named_interaction():
    found=interactions.normalise(site())
    # VAL 120 is within the old cutoff but has no named interaction; NA 705 is named
    # by PLIP as a metal complex although the cutoff list never had it.
    contacts=[{'chain':'A','sequence':76,'distance':3.84},{'chain':'A','sequence':120,'distance':3.9},
              {'chain':'A','sequence':422,'distance':2.83},{'chain':'A','sequence':79,'distance':3.53},
              {'chain':'A','sequence':156,'distance':3.7}]
    report=interactions.compare_to_proximity(found,contacts)
    assert report['proximity_only']==[{'chain':'A','sequence':120}]
    assert report['named_beyond_cutoff']==[{'chain':'A','sequence':705}]
    assert report['residues_within_cutoff']==5 and report['residues_with_named_interaction']==5
    assert len(report['agreed'])==4 and report['named_interaction_count']==len(found)

def test_build_complex_keeps_receptor_and_pose_and_refuses_an_empty_pose():
    receptor='HEADER x\nATOM      1  N   MET A   1      0.000   0.000   0.000  1.00  0.00           N\nTER\nEND\n'
    ligand='HETATM    1  C1  LIG Z 900      1.000   1.000   1.000  1.00  0.00           C\nEND\n'
    built=interactions.build_complex(receptor,ligand)
    assert 'HEADER' not in built and built.count('ATOM')>=1
    assert 'HETATM    1  C1  LIG Z 900' in built and built.rstrip().endswith('END')
    with pytest.raises(ValueError): interactions.build_complex(receptor,'END\n')

def test_tooling_reports_what_is_missing_without_pretending_to_be_available(monkeypatch):
    def refuse(module): raise ImportError('no docking environment here')
    monkeypatch.setattr(interactions,'import_module',refuse)
    state=interactions.tooling()
    assert state['available'] is False and state['method']=='plip-pdbfixer-v1'
    assert len(state['missing'])==2 and set(interactions.PACKAGES)==set(state['versions'])

def test_audit_is_unavailable_rather_than_falling_back_to_a_distance_rule(monkeypatch):
    monkeypatch.setattr(interactions,'tooling',lambda:{'method':interactions.METHOD,'available':False,
                                                       'versions':{'plip':None},'missing':['plip (ImportError)']})
    report=interactions.audit_block('ATOM\n','HETATM\n',receptor_label='receptor.pdb')
    assert report['status']=='unavailable' and report['missing']==['plip (ImportError)']
    assert 'interactions' not in report and report['receptor']=='receptor.pdb'

def test_audit_reports_a_failure_instead_of_silently_returning_nothing(monkeypatch):
    monkeypatch.setattr(interactions,'tooling',lambda:{'method':interactions.METHOD,'available':True,
                                                       'versions':{},'missing':[]})
    monkeypatch.setattr(interactions,'repair_receptor',lambda text,**kw:(_ for _ in ()).throw(RuntimeError('receptor is broken')))
    report=interactions.audit_block('ATOM\n','HETATM x\n')
    assert report['status']=='failed' and 'receptor is broken' in report['reason']

def test_gap_distance_says_whether_an_unbuilt_gap_could_reach_the_pocket():
    def atom(serial,name,residue,chain,sequence,x,y,z):
        return f"ATOM  {serial:>5} {name:<4} {residue:>3} {chain}{sequence:>4}    {x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00"
    lines=[atom(1,'CA','GLY','A',10,0,0,0),atom(2,'CA','GLY','A',30,40,0,0),
           "HETATM    3  C1  LIG Z 900       3.000   0.000   0.000  1.00  0.00           C"]
    gaps=[{'chain':'A','count':2,'residues':['SER','SER'],
           'preceding_residue':{'residue':'GLY','chain':'A','sequence':'10'},
           'following_residue':None},
          {'chain':'A','count':1,'residues':['ALA'],
           'preceding_residue':{'residue':'GLY','chain':'A','sequence':'30'},
           'following_residue':None}]
    near,far=interactions.gap_distances('\n'.join(lines),gaps)
    assert near['nearest_flank_to_ligand_angstrom']==3.0
    assert far['nearest_flank_to_ligand_angstrom']==37.0
    # No ligand records means no distance to report, and the gaps are returned as they were.
    assert interactions.gap_distances('\n'.join(lines[:2]),gaps)==gaps
