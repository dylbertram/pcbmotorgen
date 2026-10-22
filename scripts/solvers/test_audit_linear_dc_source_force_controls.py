from copy import deepcopy
import unittest

import numpy as np

from audit_linear_dc_source_force_controls import PASSED,same_layout,validate_plan,validate_source_force_summary


class SourceForceAuditGateTest(unittest.TestCase):
    def summary(self):
        pair={'0.0-total':dict(passed=True,difference_n=0.,limit_n=1e-8)}
        pair.update({str(i)+suffix:dict(passed=True,difference_n=0.,limit_n=1e-8) for i in [.1,-.1,.5,-.5] for suffix in ['-total','-increment']})
        controls={k:dict(resistance=dict(passed=True),local_sections=[dict(passed=True)],
            forces={pose:deepcopy(pair) for pose in ['nominal','plus100um','minus100um']}) for k in ['mesh','port','curvature']}
        return dict(status=PASSED,failures=[],actual_model={'actual':'model'},baseline_source_sha256='current-hash',
            source_axes=['mesh','port','curvature'],magnetic_source_control_jobs=9,saved_current_states=45,comparison_pairs=9,
            relative_refinement_gate=.02,force_vector_floor_n=1e-8,controls=controls,
            source_auxiliary_checks={k:dict(passed=True) for k in ['passive','return','independent_h1','near_field','mesh_field','port_field','curvature_field']})

    def test_new_admission_requires_bound_complete_total_and_incremental_source_forces(self):
        report=self.summary();validate_source_force_summary(report,{'actual':'model'},'current-hash')
        for kind in ['pose','increment','auxiliary','gate','binding','force']:
            changed=deepcopy(report)
            if kind=='pose':del changed['controls']['mesh']['forces']['minus100um']
            elif kind=='increment':del changed['controls']['port']['forces']['nominal']['0.1-increment']
            elif kind=='auxiliary':changed['source_auxiliary_checks']['passive']['passed']=False
            elif kind=='gate':changed['relative_refinement_gate']=.05
            elif kind=='binding':changed['baseline_source_sha256']='old-current'
            else:changed['controls']['curvature']['forces']['nominal']['0.1-increment']['difference_n']=1.
            with self.subTest(kind=kind),self.assertRaises(ValueError):validate_source_force_summary(changed,{'actual':'model'},'current-hash')

    def test_complete_source_axes_and_all_poses_are_mandatory(self):
        poses=dict(nominal='actual0',plus100um='actual+',minus100um='actual-')
        plan=dict(schema='linear-dc-source-force-audit-plan-v1',baseline=dict(jobs=poses),
            variants={kind:dict(jobs=deepcopy(poses)) for kind in ['mesh','port','curvature']})
        validate_plan(plan)
        missing=deepcopy(plan);del missing['variants']['curvature']
        with self.assertRaises(ValueError):validate_plan(missing)
        missing=deepcopy(plan);del missing['variants']['mesh']['jobs']['minus100um']
        with self.assertRaises(ValueError):validate_plan(missing)

    def test_equal_counts_are_not_equal_physical_quadrature(self):
        a=dict(points_m=np.array([[0.,0.,0.],[1.,0.,0.]]),element_numbers=np.array([1,2]))
        b=deepcopy(a);same_layout(a,b)
        b['points_m'][1,0]+=1e-12
        with self.assertRaises(ValueError):same_layout(a,b)
        b=deepcopy(a);b['element_numbers'][0]=2
        with self.assertRaises(ValueError):same_layout(a,b)
