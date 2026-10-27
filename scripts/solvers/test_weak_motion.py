import unittest
import tempfile
from pathlib import Path

import magpylib as magpy
import numpy as np

from weak_motion import solve
from check_weak_motion_elmer import input_file, integrals


class WeakMotionTest(unittest.TestCase):
    def test_nonfinite_material_or_dimensions_cannot_pass(self):
        field=lambda points:np.tile([0,0,0.1],(len(points),1))
        for dimensions,sigma in [([0.012,float('nan'),0.001],25e6),([0.012,0.012,0.001],float('nan'))]:
            with self.assertRaises(ValueError):solve([8,8,4],dimensions,[0.01,0,0],sigma,field)

    def test_slot_volume_and_uniform_field_cancellation_survive_refinement(self):
        field=lambda points:np.tile([0,0,0.1],(len(points),1))
        for n in [8,12]:
            result=solve([n,n,4],[0.012,0.012,0.001],[0.01,0,0],25e6,field,slot=0.0005)
            self.assertAlmostEqual(result['conductor_volume_m3'],1.41e-7,places=18)
            self.assertEqual(result['components'],1)
            self.assertLess(result['joule_power_w']/result['uninhibited_power_w'],1e-16)

    def test_elmer_uses_charge_potential_and_relative_conductor_velocity(self):
        text=input_file([0.01,0,0],25e6)
        self.assertIn('Static Conductivity = True',text)
        self.assertIn('Lorentz Velocity 1 = 0.01',text)
        self.assertIn('Electric Conductivity = 25000000',text)
        self.assertIn('Linear System Abort Not Converged = True',text)

    def test_dc_current_force_and_loss_integrals_have_no_half_factor(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fields.vtu'
            path.write_text('''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0 0 0 1</DataArray></Points>
<PointData><DataArray type="Float64" Name="current density e" NumberOfComponents="3">0 1 0 0 1 0 0 1 0 0 1 0</DataArray>
<DataArray type="Float64" Name="magnetic flux density e" NumberOfComponents="3">0 0 2 0 0 2 0 0 2 0 0 2</DataArray></PointData>
<Cells><DataArray type="Int32" Name="connectivity">0 1 2 3</DataArray>
<DataArray type="Int32" Name="offsets">4</DataArray><DataArray type="UInt8" Name="types">10</DataArray></Cells>
<CellData><DataArray type="Int32" Name="GeometryIds">3</DataArray></CellData>
</Piece></UnstructuredGrid></VTKFile>''')
            power,force=integrals(path,1)
            self.assertAlmostEqual(power,1/6)
            np.testing.assert_allclose(force,[1/3,0,0],atol=1e-14)

    def test_uniform_field_charge_cancels_motional_current(self):
        field=lambda points:np.tile([0.02,0.03,0.1],(len(points),1))
        result=solve([8,8,4],[0.012,0.012,0.001],[0.01,0,0],25e6,field)
        self.assertLess(result['joule_power_w']/result['uninhibited_power_w'],1e-16)
        np.testing.assert_allclose(result['force_on_conductor_n'],0,atol=1e-14)

    def test_prescribed_pm_drag_is_passive_reversible_and_zero_at_rest(self):
        magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
        results=[solve([10,10,4],[0.012,0.012,0.001],[v,0,0],25e6,magnet.getB) for v in [0.01,-0.01,0]]
        forward,reverse,zero=results
        self.assertGreater(forward['joule_power_w'],0)
        self.assertLess(forward['force_on_conductor_n'][0],0)
        self.assertAlmostEqual(forward['joule_power_w'],reverse['joule_power_w'],places=15)
        np.testing.assert_allclose(forward['force_on_conductor_n'],-np.array(reverse['force_on_conductor_n']),atol=1e-14)
        self.assertEqual(zero['joule_power_w'],0)
        np.testing.assert_array_equal(zero['force_on_conductor_n'],0)


if __name__=='__main__':
    unittest.main()
