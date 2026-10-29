import copy
import unittest

import numpy as np

from winding_oracle import conductor_samples,resistances,unit_currents


class WindingOracleTest(unittest.TestCase):
    def fixture(self):
        sim={'num_layers':4,'pcb_thickness_m':0.0012,'min_trace_m':0.0002,'min_via_drill_m':0.0003}
        drive={'winding_temp_c':20.,'outer_copper_oz':1.,'inner_copper_oz':1.,'via_plating_m':25e-6}
        net={'node_count':3,'terminal':[0],'star':[2],'edges':[
            {'a':0,'b':1,'geometry':{'kind':'trace','layer':0,'points_m':[[0,0],[0,0.01]]}},
            {'a':1,'b':2,'geometry':{'kind':'via','layers':[0,1],'position_m':[0,0.01]}}]}
        return sim,drive,net

    def test_physical_barrel_interval_and_vertical_current_are_independent(self):
        sim,drive,net=self.fixture();r=resistances(net,sim,drive,{})
        expected_via=1.724e-8*0.0004/(np.pi*25e-6*(0.0003+25e-6))
        self.assertAlmostEqual(r[1],expected_via,places=14)
        shares,equivalent=unit_currents(net,r)
        np.testing.assert_allclose(shares,[1,1],atol=1e-12);self.assertAlmostEqual(equivalent,float(r.sum()),places=12)
        positions,dl=conductor_samples(net,shares,sim,{},8)
        self.assertEqual(positions.shape,(16,3));self.assertAlmostEqual(float(dl[:,2].sum()),-0.0004,places=14)
        self.assertAlmostEqual(float((-2*dl[:,2]).sum()),0.0008,places=14)

    def test_drawing_direction_does_not_set_electrical_current_polarity(self):
        sim,drive,net=self.fixture();reversed=copy.deepcopy(net)
        reversed['edges'][0]['a']=1;reversed['edges'][0]['b']=0
        reversed['edges'][0]['geometry']['points_m'].reverse()
        sums=[]
        for network in [net,reversed]:
            shares,_=unit_currents(network,resistances(network,sim,drive,{}))
            _,dl=conductor_samples(network,shares,sim,{},8);sums.append(dl.sum(axis=0))
        np.testing.assert_allclose(sums[0],sums[1],atol=1e-14)

    def test_performance_goals_do_not_change_independent_winding_reference(self):
        sim,drive,net=self.fixture()
        def solve(sim,drive):
            r=resistances(net,sim,drive,{})
            shares,equivalent=unit_currents(net,r)
            positions,dl=conductor_samples(net,shares,sim,{},8)
            return r,shares,equivalent,positions,dl
        baseline=solve(sim,drive)
        sim.update(target_force_n=100.,peak_force_n=.001,max_accel_m_s2=0.,max_temperature_rise_c=0.)
        drive.update(voltage_headroom=.001,ripple_limit_fraction=.0001,allowed_rise_c=.1)
        changed=solve(sim,drive)
        for a,b in zip(baseline,changed):np.testing.assert_array_equal(a,b)

    def test_imported_depth_replaces_equal_spacing_and_invalid_data_fail(self):
        sim,drive,net=self.fixture();hints={'layer_z_m':[0.0002,-0.003]}
        shares,_=unit_currents(net,resistances(net,sim,drive,hints))
        _,dl=conductor_samples(net,shares,sim,hints,8)
        self.assertAlmostEqual(float(dl[:,2].sum()),-0.0032,places=14)
        with self.assertRaises(ValueError):conductor_samples(net,shares,sim,hints,0)
        with self.assertRaises(ValueError):resistances(net,sim,drive,{'layer_z_m':[float('nan')]})


if __name__=='__main__':unittest.main()
