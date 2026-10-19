import unittest

from compare_eddy_disk import validate_refinement


class EddyRefinementTest(unittest.TestCase):
    def test_labels_and_inactive_size_changes_are_not_refinement(self):
        a={'conductivity':25e6,'peak_b':0.01,'disk_radius':0.006,'thickness':0.001,
           'slot':0.0005,'mesh':0.0008,'air_radius':0.03}
        b=dict(a,mesh=0.0002)
        validate_refinement(a,b,'fine')
        validate_refinement(b,dict(b,air_radius=0.045),'domain')
        for first,second,tag in [(a,a,'fine'),(a,dict(a,mesh=0.0006),'fine'),
                                 (a,dict(b,air_radius=0.045),'fine'),(b,b,'domain'),
                                 (b,dict(b,air_radius=0.045,slot=0),'domain')]:
            with self.assertRaises(ValueError):validate_refinement(first,second,tag)


if __name__=='__main__':
    unittest.main()
