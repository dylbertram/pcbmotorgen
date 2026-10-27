import importlib.util
import unittest

import numpy as np

from finite_copper_current import solve


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class FiniteCopperCurrentTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('pyamg'),'optional pinned PyAMG target required')
    def test_symmetric_amg_preserves_saved_resistivity_mixed_solution(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry,Box,Glue
        inner=.001;outer=.002;height=.0005;rho=2.0966426e-8
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        half=ring*Box(Pnt(-.003,-.003,-.001),Pnt(.003,0.,.001));other=ring-half
        half.mat('drive');other.mat('copper')
        mesh=ng.Mesh(OCCGeometry(Glue([half,other])).GenerateMesh(maxh=.0002));mesh.Curve(1)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        direct,reference=solve(ng,mesh,electric,rho)
        amg,metadata=solve(ng,mesh,electric,rho,iterative=True,pressure_solver='amg')
        np.testing.assert_allclose(amg.vec.FV().NumPy(),direct.vec.FV().NumPy(),rtol=1e-7,atol=1e-7)
        self.assertLess(abs(metadata['source_power_w']/reference['source_power_w']-1),1e-9)
        self.assertLess(metadata['relative_equation_residual'],1e-9)
        self.assertIsNone(metadata['linear_solver']['pressure_factor_nonzeros'])

    def test_native_face_adjacency_matches_independent_tetra_face_counts(self):
        from collections import Counter
        from itertools import combinations
        import ngsolve as ng
        from netgen.occ import Box,Pnt,Glue,OCCGeometry
        from finite_copper_current import exterior_flux_dofs
        left=Box(Pnt(0,0,0),Pnt(.5,1,1));right=Box(Pnt(.5,0,0),Pnt(1,1,1))
        left.mat('copper');right.mat('drive')
        mesh=ng.Mesh(OCCGeometry(Glue([left,right])).GenerateMesh(maxh=.3));space=ng.HDiv(mesh,order=0)
        counts=Counter(tuple(sorted(v)) for element in mesh.Elements() for v in combinations([v.nr for v in element.vertices],3))
        expected=set();interface=set()
        for face in mesh.faces:
            dofs=set(space.GetDofNrs(ng.NodeId(ng.FACE,face.nr)))
            if counts[tuple(sorted(v.nr for v in face.vertices))]==1:expected.update(dofs)
            if len(face.elements)==2 and len({mesh[e].mat for e in face.elements})==2:interface.update(dofs)
        actual=set(exterior_flux_dofs(ng,mesh,space))
        self.assertEqual(actual,expected);self.assertTrue(interface);self.assertFalse(actual&interface)

    def test_linear_geometry_closed_flux_keeps_original_current_moment_gate(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        inner=.001;outer=.002;height=.0005;rho=2.0966426e-8
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        ring.mat('copper');mesh=ng.Mesh(OCCGeometry(ring).GenerateMesh(maxh=.0002));mesh.Curve(1)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        _,metadata=solve(ng,mesh,electric,rho,iterative=True)
        analytic=height*np.log(outer/inner)/(2*np.pi*rho)
        self.assertLess(abs(metadata['source_power_w']/analytic-1),.02)
        self.assertLess(metadata['net_current_relative_error'],1e-9)

    def test_block_solver_retains_accuracy_at_saved_copper_resistivity_scale(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        inner=.001;outer=.002;height=.0005;rho=1.724e-8*(1+.00393*(75.-20.))
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        ring.mat('copper');mesh=ng.Mesh(OCCGeometry(ring).GenerateMesh(maxh=.00025));mesh.Curve(2)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        _,metadata=solve(ng,mesh,electric,rho,iterative=True)
        analytic=height*np.log(outer/inner)/(2*np.pi*rho)
        self.assertLess(abs(metadata['source_power_w']/analytic-1),.02)
        self.assertLess(metadata['relative_equation_residual'],1e-9)

    def test_internal_material_interface_does_not_become_an_insulating_cut(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry,Box,Glue
        inner=.001;outer=.002;height=.0005
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        half=ring*Box(Pnt(-.003,-.003,-.001),Pnt(.003,0.,.001));other=ring-half
        half.mat('drive');other.mat('copper')
        mesh=ng.Mesh(OCCGeometry(Glue([half,other])).GenerateMesh(maxh=.00025));mesh.Curve(2)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        _,metadata=solve(ng,mesh,electric,1.)
        analytic=height*np.log(outer/inner)/(2*np.pi)
        self.assertLess(abs(metadata['source_power_w']/analytic-1),.02)

    def test_annular_closed_current_matches_analytic_resistance_and_is_divergence_free(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        inner=.001;outer=.002;height=.0005
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        ring.mat('copper');ring.faces.name='outer'
        mesh=ng.Mesh(OCCGeometry(ring).GenerateMesh(maxh=.00025));mesh.Curve(2)
        radius2=ng.x**2+ng.y**2;electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*radius2)
        solution,metadata=solve(ng,mesh,electric,1.)
        iterative,block=solve(ng,mesh,electric,1.,iterative=True)
        np.testing.assert_allclose(iterative.vec.FV().NumPy(),solution.vec.FV().NumPy(),rtol=1e-7,atol=1e-9)
        self.assertLess(block['linear_solver']['relative_mixed_residual'],1e-9)
        analytic=height*np.log(outer/inner)/(2*np.pi)
        self.assertLess(abs(metadata['source_power_w']/analytic-1),.02)
        self.assertLess(metadata['net_current_relative_error'],1e-9)
        self.assertLess(metadata['integrated_divergence_squared'],1e-16)
