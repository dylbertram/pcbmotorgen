import tempfile
import unittest
from pathlib import Path

import numpy as np

from read_vtu import sample_vector


VTU = '''<VTKFile><UnstructuredGrid><Piece>
<Points><DataArray type="Float64" format="ascii">0 0 0 1 0 0 0 1 0 0 0 1</DataArray></Points>
<PointData><DataArray type="Float64" Name="magnetic flux density" NumberOfComponents="3" format="ascii">0 0 1 1 0 1 2 0 1 0 3 1</DataArray></PointData>
<Cells>
<DataArray type="Int32" Name="connectivity" format="ascii">0 1 2 3</DataArray>
<DataArray type="Int32" Name="offsets" format="ascii">4</DataArray>
<DataArray type="UInt8" Name="types" format="ascii">10</DataArray>
</Cells></Piece></UnstructuredGrid></VTKFile>'''


class VtuTest(unittest.TestCase):
    def test_element_field_is_not_replaced_by_nodal_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'element.vtu'
            path.write_text(VTU.replace('<Cells>','<CellData><DataArray type="Float64" Name="magnetic flux density e" NumberOfComponents="3">7 8 9</DataArray></CellData><Cells>'))
            np.testing.assert_allclose(sample_vector(path,[[0.1,0.2,0.3]],name='magnetic flux density e'),[[7,8,9]])
            np.testing.assert_allclose(sample_vector(path,[[0.1,0.2,0.3]]),[[0.5,0.9,1]])

    def test_raw_getdp_air_tetrahedron(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'air.pos'
            path.write_text('View "b" {VS(0,0,0,1,0,0,0,1,0,0,0,1){0,0,1,1,0,1,2,0,1,0,3,1};};')
            np.testing.assert_allclose(sample_vector(path,[[0.1,0.2,0.3],[0,0,0]]),[[0.5,0.9,1],[0,0,1]],atol=1e-14)
            with self.assertRaisesRegex(ValueError,'outside'):
                sample_vector(path,[[1,1,1]])
            path.write_text('View "b" {VS(0,0,0,1,0,0,0,1,0,0,0,1){0,0,2,2,0,2,4,0,2,0,6,2};};')
            np.testing.assert_allclose(sample_vector(path,[[0.1,0.2,0.3]]),[[1,1.8,2]],atol=1e-14)

    def test_linear_vector_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field.vtu"
            path.write_text(VTU)
            actual = sample_vector(path, [[0.1, 0.2, 0.3], [0, 0, 0]])
            np.testing.assert_allclose(actual, [[0.5, 0.9, 1], [0, 0, 1]], atol=1e-14)
            with self.assertRaisesRegex(ValueError, "outside"):
                sample_vector(path, [[1, 1, 1]])
            with self.assertRaisesRegex(ValueError, "Missing"):
                sample_vector(path, [[0, 0, 0]], "unknown")

    def test_unsupported_binary_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field.vtu"
            path.write_text(VTU.replace('format="ascii"', 'format="binary"'))
            with self.assertRaisesRegex(ValueError, "ASCII"):
                sample_vector(path, [[0, 0, 0]])


if __name__ == "__main__":
    unittest.main()
