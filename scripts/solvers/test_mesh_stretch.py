import copy
import re
import tempfile
import unittest
from pathlib import Path

from mesh_stretch import physical_mesh,stretched_geometry
from project_symmetry import quarter_model,quarter_geometry


def model():
    return {'magnets':[{'tag':2,'name':'magnet','origin_m':[-0.0025,-0.0025,0.0013],
                        'size_m':[0.005,0.005,0.003],'polarization_t':[0,0,1.34]}],
            'stack':[{'tag':3,'name':'plate','origin_m':[-0.006,-0.006,-0.005],
                      'size_m':[0.012,0.012,0.005],'material':'flex_ferrite','mu_r':130,'bsat_t':0.25}]}


class MeshStretchTest(unittest.TestCase):
    def test_only_meshing_coordinates_change_not_the_source_or_material(self):
        original=quarter_model(model());before=copy.deepcopy(original)
        text=stretched_geometry(original,0.0008,0.0001,0.03,4,quarter=True)
        self.assertEqual(original,before)
        self.assertIn('Dilate {{0,0,0},{1,1,4}} {Volume{1};}',text)
        box=list(map(float,re.search(r'Box\(2\)=\{([^}]+)\}',text).group(1).split(',')))
        self.assertAlmostEqual(box[2],0.0052)
        self.assertAlmostEqual(box[5],0.012)
        self.assertIn('0.12',text)
        with self.assertRaises(ValueError):stretched_geometry(original,0.0004,0.0002,0.03,4,quarter=True)
        self.assertEqual(stretched_geometry(original,0.0008,0.0001,0.03,1,quarter=True),quarter_geometry(original,0.0008,0.0001,0.03))

    def test_shared_source_dimensions_are_stretched_once_per_object(self):
        original=model();other=copy.deepcopy(original['magnets'][0]);other['tag']=4;other['name']='second'
        other['origin_m']=[0.004,-0.0025,0.0013];other['size_m']=original['magnets'][0]['size_m'];original['magnets'].append(other)
        text=stretched_geometry(original,0.0008,0.0001,0.03,4)
        for tag in [2,4]:
            data=list(map(float,re.search(rf'Box\({tag}\)=\{{([^}}]+)\}}',text).group(1).split(',')))
            self.assertAlmostEqual(data[5],0.012)
        self.assertEqual(original['magnets'][0]['size_m'][2],0.003)

    def test_mesh_returns_to_physical_z_before_any_pde_with_tags_untouched(self):
        text='$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n2\n1 0.003 0.004 0.02\n2 0 0 -0.04\n$EndNodes\n$Elements\n1\n1 1 2 1001 1 1 2\n$EndElements\n'
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'scaled.msh';destination=Path(directory)/'physical.msh';source.write_text(text)
            physical_mesh(source,destination,4)
            data=destination.read_text().splitlines();nodes=data[data.index('$Nodes')+2:data.index('$EndNodes')]
            self.assertAlmostEqual(float(nodes[0].split()[3]),0.005)
            self.assertAlmostEqual(float(nodes[1].split()[3]),-0.01)
            self.assertEqual(data[data.index('$Elements'):],text.splitlines()[text.splitlines().index('$Elements'):])
            self.assertEqual(source.read_text(),text)
            with self.assertRaises(ValueError):physical_mesh(source,destination,4)

    def test_sphere_reprojection_cannot_hide_an_interface_or_missing_exterior(self):
        template='$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n3\n1 0.03 0 0\n2 0 0.03 0\n3 0 0 0.12000004\n$EndNodes\n$Elements\n1\n1 2 2 1001 1 1 2 3\n$EndElements\n'
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'scaled.msh';destination=Path(directory)/'physical.msh';source.write_text(template)
            physical_mesh(source,destination,4,0.03)
            nodes=destination.read_text().splitlines();start=nodes.index('$Nodes')
            self.assertAlmostEqual(float(nodes[start+4].split()[3]),0.03,places=15)
            source.write_text(template.replace('0.12000004','0.004'))
            with self.assertRaises(ValueError):physical_mesh(source,Path(directory)/'bad.msh',4,0.03)
            source.write_text(template.replace('1001','1002'))
            with self.assertRaises(ValueError):physical_mesh(source,Path(directory)/'missing.msh',4,0.03)


if __name__=='__main__':unittest.main()
