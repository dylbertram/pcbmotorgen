import unittest

from relabel_dxf_phases import swap


class RelabelDxfTest(unittest.TestCase):
    def test_swap_is_exact_and_preserves_numeric_groups_and_endings(self):
        original=b'  2\r\nL6_B\r\n  8\r\nVia_L6_L5_C\r\n 10\r\n6.333333\r\n  1\r\nC\r\n'
        corrected,counts=swap(original)
        self.assertEqual(corrected,b'  2\r\nL6_C\r\n  8\r\nVia_L6_L5_B\r\n 10\r\n6.333333\r\n  1\r\nB\r\n')
        self.assertEqual(sum(counts.values()),3)
        self.assertEqual(swap(corrected)[0],original)

    def test_does_not_swap_substrings_or_other_phases(self):
        original=b'8\nL5_A\n8\nBOARD\n8\nL5_B_extra\n40\nB\n'
        self.assertEqual(swap(original),(original,{}))

    def test_rejects_partial_group_pairs(self):
        with self.assertRaises(ValueError):
            swap(b'0\nLINE\n8\n')


if __name__ == '__main__':
    unittest.main()
