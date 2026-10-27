import tempfile
import unittest
from pathlib import Path

import numpy as np

from check_plate2d import raw_field, line_stress, MU0


class PotentialCurlTest(unittest.TestCase):
    def test_getdp_raw_potential_curl_and_stress(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'potential.pos'
            path.write_text('''View "potential" {
ST(0,0,0,1,0,0,0,1,0){0,1,2};
ST(1,0,0,1,1,0,0,1,0){1,3,2};
};''')
            np.testing.assert_allclose(raw_field(path,[[0.1,0.2],[0.9,0.9]]),[[2,-1],[2,-1]],atol=1e-14)
            self.assertAlmostEqual(line_stress(path,0.4,0,1)/(-3/(2*MU0)),1,places=12)
            path.write_text('View "wrong" { VT(0,0,0){1,2,3}; };')
            with self.assertRaisesRegex(ValueError,'Expected scalar triangles'):
                raw_field(path,[[0,0]])

    def test_curl_and_triangle_coordinates(self):
        # A_z=x+2y has B=(2,-1). Reverse node orientation too.
        for order in ["0 1 2", "0 2 1"]:
            with self.subTest(order=order), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "field.vtu"
                path.write_text(f'''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0</DataArray></Points>
<PointData><DataArray type="Float64" Name="A">0 1 2</DataArray></PointData>
<Cells><DataArray type="Int32" Name="connectivity">{order}</DataArray>
<DataArray type="Int32" Name="offsets">3</DataArray>
<DataArray type="UInt8" Name="types">5</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>''')
                actual = raw_field(path, [[0.1, 0.2], [0, 0]])
                np.testing.assert_allclose(actual, [[2, -1], [2, -1]], atol=1e-14)
                with self.assertRaises(AssertionError):
                    raw_field(path, [[0.8, 0.8]])

    def test_exact_stress_integration_across_triangles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field.vtu"
            # Square split along its diagonal, A=x+2y, B=(2,-1).
            path.write_text('''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64">0 0 0 1 0 0 0 1 0 1 1 0</DataArray></Points>
<PointData><DataArray type="Float64" Name="A">0 1 2 3</DataArray></PointData>
<Cells><DataArray type="Int32" Name="connectivity">0 1 2 1 3 2</DataArray>
<DataArray type="Int32" Name="offsets">3 6</DataArray>
<DataArray type="UInt8" Name="types">5 5</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>''')
            for y in [0.01, 0.5, 0.99]:
                self.assertAlmostEqual(line_stress(path, y, 0, 1)/(-3/(2*MU0)), 1, places=12)
                self.assertAlmostEqual(line_stress(path, y, 0.2, 0.7)/(-1.5/(2*MU0)), 1, places=12)
            with self.assertRaisesRegex(AssertionError, "not fully covered"):
                line_stress(path, 0.5, -1, 1)
            # Replacing an output cannot reuse the earlier potential cache.
            path.write_text(path.read_text().replace('>0 1 2 3</DataArray>', '>0 2 4 6</DataArray>'))
            np.testing.assert_allclose(raw_field(path, [[0.1,0.2], [0.9,0.9]]), [[4,-2], [4,-2]])


if __name__ == "__main__":
    unittest.main()
