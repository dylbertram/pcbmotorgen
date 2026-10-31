import unittest
import numpy as np
from winding_oracle import layer_z, resistances


class PcbStackupOracleTest(unittest.TestCase):
    def test_explicit_centers_and_copper_override_uniform_weights(self):
        sim = dict(num_layers=4, pcb_thickness_m=.0008, min_trace_m=.0002,
                   pcb_stackup=dict(copper_m=[35e-6,18e-6,70e-6,35e-6],dielectric_m=[.0001,.0004,.000142]))
        for layer, expected in enumerate([-.0000175,-.000144,-.000588,-.0007825]):
            self.assertAlmostEqual(layer_z(sim,{},layer),expected,places=15)
        network=dict(edges=[dict(geometry=dict(kind='trace',layer=i,points_m=[[0,0],[.01,0]])) for i in range(4)])
        drive=dict(winding_temp_c=20,inner_copper_oz=3,outer_copper_oz=3)
        actual=resistances(network,sim,drive,{})
        np.testing.assert_allclose(actual,[1.724e-8*.01/(.0002*t) for t in sim['pcb_stackup']['copper_m']],rtol=1e-14)
        sim['pcb_stackup']['dielectric_m'][0]=0
        with self.assertRaises(ValueError): layer_z(sim,{},0)


if __name__=='__main__': unittest.main()
