import itertools
import unittest
import tempfile
from pathlib import Path

import numpy as np

from getdp_initial_guess import coefficients, transfer_formulation, layout


class InitialGuessTest(unittest.TestCase):
    def test_preprocessor_element_indices_are_not_gmsh_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);mesh=root/'mesh.msh';pre=root/'project.pre'
            mesh.write_text('$Nodes\n4\n1 0 0 0\n2 1 0 0\n3 0 1 0\n4 0 0 1\n$EndNodes\n$Elements\n5\n'
                '10 2 2 1 1 1 2 3\n20 2 2 1 1 1 2 4\n30 2 2 1 1 1 3 4\n40 2 2 1 1 2 3 4\n50 4 2 1 1 1 2 3 4\n$EndElements\n')
            records=[f'1 {i} 0 1 {i} 0' for i in range(1,5)]+[f'2 {i} 0 1 {i+4} 0' for i in range(1,7)]
            pre.write_text('$DofData\n0 0\n1 0\n1 0\n1 0\n10 10\n'+'\n'.join(records)+'\n$EndDofData\n$ElementsXEdges\n0 5\n'
                '0 3 1 2 4\n1 3 1 3 5\n2 3 2 3 6\n3 3 4 5 6\n4 6 1 2 3 4 5 6\n$EndElementsXEdges\n')
            nodes,edges,parsed,count=layout(mesh,pre)
            self.assertEqual(edges[6],(3,4));self.assertEqual(count,10);self.assertEqual(len(parsed),10)

    def test_hierarchical_edge_coefficients_reconstruct_a_quadratic_polynomial(self):
        nodes={1:np.array([0.,0.,0.]),2:np.array([1.,0.,0.]),3:np.array([0.,1.,0.]),4:np.array([0.,0.,1.])}
        edges=dict(enumerate(itertools.combinations(nodes,2),1))
        records=[(1,i,i-1) for i in nodes]+[(2,i,i+3) for i in edges]
        f=lambda p:p[:,0]**2+2*p[:,1]*p[:,2]+3*p[:,2]
        values=coefficients(nodes,edges,records,10,f)
        bary=np.array([.1,.2,.3,.4]);point=np.array([bary[1:]])
        reconstructed=np.dot(values[:4],bary)+sum(values[i+3]*bary[a-1]*bary[b-1] for i,(a,b) in edges.items())
        self.assertAlmostEqual(reconstructed,f(point)[0],places=14)

    def test_transfer_resolution_does_not_solve_a_physics_problem(self):
        changed=transfer_formulation('Resolution {old}\nPostProcessing {old}\n')
        section=changed.split('Resolution {')[1].split('PostProcessing {')[0]
        self.assertNotIn('GenerateJac',section);self.assertNotIn('SolveJac',section)
        self.assertIn('CopySolution[InitialValues(),S]',section)
