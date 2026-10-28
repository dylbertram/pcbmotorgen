import importlib.util
import unittest

from ngsolve_eddy_av import disk_mesh,solve,weak_disk_loss
from eddy_sphere_reference import dipole_loss


class DiskReferenceTest(unittest.TestCase):
    def test_peak_field_frequency_and_geometry_scaling(self):
        baseline=weak_disk_loss(.006,.001,25e6,1.,.01)
        self.assertAlmostEqual(baseline,2.5115084111042857e-8,delta=1e-18)
        self.assertAlmostEqual(weak_disk_loss(.012,.002,25e6,2.,.02)/baseline,512.)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class CoupledAVEddyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        cls.ng=ng;cls.mesh=disk_mesh(ng,.001,.0002,0.,.0005,.004,.002,'sphere')

    def test_zero_impressed_source_has_no_current_or_reaction_energy(self):
        _,proof=solve(self.ng,self.mesh,1000.,1e6,0.,4)
        self.assertEqual(proof['joule_power_w'],0.)
        self.assertEqual(proof['reaction_magnetic_energy_time_average_j'],0.)
        self.assertEqual(proof['relative_equation_residual'],0.)

    def test_coupled_source_is_passive_and_frequency_reversal_conjugates(self):
        _,forward=solve(self.ng,self.mesh,1000.,1e6,.01,4)
        _,reverse=solve(self.ng,self.mesh,-1000.,1e6,.01,4)
        self.assertLess(forward['relative_equation_residual'],1e-9)
        self.assertLess(forward['net_volume_current_relative_error'],1e-9)
        self.assertLess(forward['relative_source_work_joule_balance'],.02)
        self.assertAlmostEqual(forward['joule_power_w']/reverse['joule_power_w'],1.,places=10)
        exact=dipole_loss(.001,1e6,1000.,.01)
        self.assertLess(abs(forward['joule_power_w']/exact-1),.05)

    def test_tree_and_coulomb_gauges_preserve_physical_current_and_energy(self):
        for order in [0,2]:
            _,reference=solve(self.ng,self.mesh,1000.,1e6,.01,4,order=order)
            _,tree=solve(self.ng,self.mesh,1000.,1e6,.01,4,order=order,gauge='tree')
            self.assertGreater(tree['tree_fixed_edges'],0)
            self.assertLess(tree['relative_equation_residual'],1e-9)
            self.assertLess(tree['net_volume_current_relative_error'],1e-9)
            for key in ['joule_power_w','source_work_w','reaction_magnetic_energy_time_average_j']:
                self.assertLess(abs(tree[key]/reference[key]-1),1e-8)
