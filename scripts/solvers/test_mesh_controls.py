import unittest

from mesh_controls import with_far_mesh
from project_static import geometry
from test_mesh_stretch import model


class FarMeshControlTest(unittest.TestCase):
    def test_only_far_air_controls_change(self):
        original=geometry(model(),0.0008,0.0001,0.06)
        changed=with_far_mesh(original,0.005)
        for before,after in zip(original.splitlines(),changed.splitlines()):
            if before.startswith('Mesh.MeshSizeMax=') or '.VOut=' in before:
                self.assertTrue(after.endswith('=0.0050000000000000001;'))
            elif before.startswith('Mesh.MeshSizeFromCurvature='):
                self.assertEqual(after,'Mesh.MeshSizeFromCurvature=0;')
            else:self.assertEqual(before,after)
        self.assertIn('Mesh.MeshSizeFromCurvature=0;',with_far_mesh(original,0.06/6))
        self.assertIn('Mesh.MeshSizeFromCurvature=16;',original) # legacy geometry remains unchanged

    def test_radius_refinement_can_hold_far_air_absolute_size_fixed(self):
        original=with_far_mesh(geometry(model(),0.0008,0.0001,0.06),0.01)
        larger=with_far_mesh(geometry(model(),0.0008,0.0001,0.09),0.01)
        self.assertNotEqual(original.splitlines()[1],larger.splitlines()[1])
        controls=lambda text:[line for line in text.splitlines() if line.startswith('Mesh.') or '.VOut=' in line]
        self.assertEqual(controls(original),controls(larger))

    def test_invalid_or_missing_controls_are_not_silently_ignored(self):
        for value in [0,-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):with_far_mesh('anything',value)
        with self.assertRaises(ValueError):with_far_mesh('Mesh.MeshSizeMax=0.01;\n',0.005)


if __name__=='__main__':unittest.main()
