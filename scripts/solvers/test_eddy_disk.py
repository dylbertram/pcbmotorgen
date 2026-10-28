import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from check_eddy_disk import mean_power, poynting_input, source_input_work, sif, weak_loss
from eddy_disk_network import shape_integral


class EddyDiskTest(unittest.TestCase):
    def test_projection_ringing_keeps_signed_energy_and_rejects_material_negative_power(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'projection.vtu'
            def write(negative):
                path.write_text(f'''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0 0 0 1 2 0 0 3 0 0 2 1 0 2 0 1</DataArray></Points>
<Cells><DataArray type="Int32" Name="connectivity">0 1 2 3 4 5 6 7</DataArray>
<DataArray type="Int32" Name="offsets">4 8</DataArray><DataArray type="UInt8" Name="types">10 10</DataArray></Cells>
<CellData><DataArray type="Float64" Name="joule heating e">6 {negative}</DataArray></CellData>
</Piece></UnstructuredGrid></VTKFile>''')
            write(-1e-8)
            power,metadata=mean_power(path)
            self.assertAlmostEqual(power,1-1e-8/6,places=14)
            self.assertLess(metadata['_projection_audit']['negative_power_w'],0)
            self.assertTrue(metadata['_projection_audit']['signed_integral_retained'])
            write(-0.01)
            with self.assertRaisesRegex(ValueError,'one part per million'):
                mean_power(path)

    def test_source_work_integrates_linear_current_times_linear_impressed_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'field.vtu'
            path.write_text('''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0 0 0 1</DataArray></Points>
<PointData><DataArray type="Float64" Name="current density im e" NumberOfComponents="3">0 0 0 0 -1 0 1 0 0 0 0 0</DataArray></PointData>
<Cells><DataArray type="Int32" Name="connectivity">0 1 2 3</DataArray>
<DataArray type="Int32" Name="offsets">4</DataArray><DataArray type="UInt8" Name="types">10</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>''')
            # omega*B/2=1, so J_im=Eprimary_im=(y,-x,0).
            # integral(x^2+y^2) over the unit tetra is 1/30; peak-to-mean is 1/2.
            self.assertAlmostEqual(source_input_work(path,1/(2*math.pi),2),1/60)

    def test_independent_stream_oracle_recovers_circle_and_slot_effect(self):
        plain=shape_integral(48,0.006)
        self.assertLess(plain['max_point_error_normalized'],1e-11)
        self.assertLess(abs(plain['integral_relative_error']),0.001)
        slot=shape_integral(48,0.006,0.001)
        fine=shape_integral(96,0.006,0.001)
        self.assertLess(slot['integral_u_m4'],plain['integral_u_m4'])
        self.assertLess(abs(slot['integral_u_m4']/fine['integral_u_m4']-1),0.02)
        with self.assertRaises(ValueError):shape_integral(16,0.006,0.0005)

    def test_closed_surface_flux_of_uniform_complex_fields_is_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'field.vtu'
            p=np.array([[1,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]])/math.sqrt(3)
            arrays=''
            for name,vector in [('electric field re e',[1,0,0]),('electric field im e',[0,1,0]),
                                ('magnetic field strength re e',[0,1,0]),('magnetic field strength im e',[0,0,1])]:
                values=' '.join(str(x) for x in np.tile(vector,(4,1)).ravel())
                arrays+=f'<DataArray type="Float64" Name="{name}" NumberOfComponents="3">{values}</DataArray>'
            points=' '.join(f'{x:.17g}' for x in p.ravel())
            path.write_text(f'''<VTKFile><UnstructuredGrid><Piece><Points><DataArray type="Float64">{points}</DataArray></Points>
<PointData>{arrays}</PointData><Cells><DataArray type="Int32" Name="connectivity">0 1 2 3</DataArray>
<DataArray type="Int32" Name="offsets">4</DataArray><DataArray type="UInt8" Name="types">10</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>''')
            flux,count=poynting_input(path,1)
            self.assertEqual(count,4)
            self.assertAlmostEqual(flux,0,places=14)

    def test_mean_loss_matches_direct_current_density_integral(self):
        frequency,b,sigma,a,t=1.0,0.01,25e6,0.006,0.001
        n=128
        r=(np.arange(n)+0.5)*a/n
        j=sigma*2*math.pi*frequency*b*r/2
        integral=float(np.sum(j*j/(2*sigma)*2*math.pi*r*a/n*t))
        expected=weak_loss(frequency,b,sigma,a,t)
        self.assertLess(abs(integral/expected-1),1e-4)
        self.assertAlmostEqual(weak_loss(2*frequency,b,sigma,a,t)/expected,4)
        self.assertAlmostEqual(weak_loss(frequency,2*b,sigma,a,t)/expected,4)

    def test_peak_excitation_uses_time_average_power(self):
        text=sif(1,0.01,25e6)
        self.assertIn('Calculate Harmonic Peak Power = False',text)
        self.assertIn('WhitneyAVHarmonicSolver',text)
        self.assertIn('AV Re {e} 1 = Variable Coordinate 2',text)
        self.assertIn('Real MATC "-0.0050000000000000001*tx"',text)
        self.assertIn('Linear System Abort Not Converged = True',text)

    def test_elemental_joule_density_is_volume_integrated(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'field.vtu'
            path.write_text('''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0 0 0 1</DataArray></Points>
<Cells><DataArray type="Int32" Name="connectivity">0 1 2 3</DataArray>
<DataArray type="Int32" Name="offsets">4</DataArray>
<DataArray type="UInt8" Name="types">10</DataArray></Cells>
<CellData><DataArray type="Float64" Name="joule heating e">6</DataArray></CellData>
</Piece></UnstructuredGrid></VTKFile>''')
            self.assertAlmostEqual(mean_power(path)[0],1)
            path.write_text(path.read_text().replace('<CellData>','<PointData>').replace('</CellData>','</PointData>').replace('>6</DataArray>','>6 6 6 6</DataArray>'))
            self.assertAlmostEqual(mean_power(path)[0],1)


if __name__=='__main__':
    unittest.main()
