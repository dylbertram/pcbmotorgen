import copy
import unittest

import numpy as np

from audit_material_motion_controls import control_axis,changes,trace_checks


def record(steps=4):
    rows=[]
    for i in range(steps):
        rows.append({'time_mid_s':(i+.5)/steps,'joule_power_w':1.,'housing_source_force_n':[.1,0.,0.],
            'material_source_force_n':[0.,0.,1.],'reduced_magnetic_energy_end_j':-.1+.001*(i+1)/steps})
    return {'model':{},'source_summary_sha256':'a','version':'1','mesh_sha256':'same','request':{'steps':steps,'mesh':.002,'fer_mesh':.002,'far':.04,'bonus_order':4},
        'profile':{'start_offset_m':0.,'end_offset_m':.01,'duration_s':1.,'dt_s':1/steps},
        'steps':rows,'joule_energy_j':1.,'mechanical_source_energy_j':1.001,'initial_reduced_energy_j':-.1,'final_reduced_energy_j':-.099}


class MaterialMotionControlsTest(unittest.TestCase):
    def test_only_declared_axis_changes_and_time_mesh_is_identical(self):
        a=record();b=record(8);control_axis(a,b,'time')
        b['mesh_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'changed the mesh'):control_axis(a,b,'time')
        b=record(8);b['request']['far']=.06
        with self.assertRaisesRegex(ValueError,'multiple parameter'):control_axis(a,b,'time')

    def test_assembly_comparison_keeps_identical_physics_and_mesh(self):
        a=record();b=copy.deepcopy(a);control_axis(a,b,'assembly')
        b['request']['steps']=8
        with self.assertRaisesRegex(ValueError,'multiple parameter'):control_axis(a,b,'assembly')
        b=copy.deepcopy(a);b['mesh_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'changed the mesh'):control_axis(a,b,'assembly')

    def test_static_attraction_cannot_hide_failed_drag_or_energy_change(self):
        a=record();b=record(8)
        self.assertTrue(changes(a,b)['passed'])
        for row in a['steps']:row['housing_source_force_n'][0]*=1.1
        self.assertFalse(changes(a,b)['checks']['housing_source_force_n']['passed'])
        a=record();a['initial_reduced_energy_j']+=.01;a['final_reduced_energy_j']+=.0101
        result=changes(a,b)
        self.assertFalse(result['checks']['energy_change_j']['passed'])

    def test_trace_recomputes_material_work_and_energy_limits(self):
        trial=record();trial['status']='completed-nonlinear-ferrite-housing-motion-unqualified';trial['failures']=[]
        trial['request']['speed']=1.;trial['profile']['end_offset_m']=1.
        old=trial['initial_reduced_energy_j'];dt=trial['profile']['dt_s']
        for i,row in enumerate(trial['steps']):
            row.update(step=i,source_offset_m=(i+.5)*dt,current_source_work_w=1.001,mechanical_source_work_w=1.001,
                housing_source_force_n=[1.001,0.,0.],relative_equation_residual=0.,net_current_relative_error=0.)
            new=row['reduced_magnetic_energy_end_j'];row['energy_defect_j']=abs((1.001-1.)*dt-(new-old))
            row['energy_limit_j']=.02*1.001*dt;old=new
        trial['integrated_energy_defect_j']=abs(1.001-1.-(trial['final_reduced_energy_j']-trial['initial_reduced_energy_j']));trial['integrated_energy_limit_j']=.02*1.001
        trace_checks(trial)
        missing_work=copy.deepcopy(trial);missing_work['steps'][0]['material_source_force_n'][0]=.1
        with self.assertRaisesRegex(ValueError,'Conservative material work'):trace_checks(missing_work)
        inflated_gate=copy.deepcopy(trial);inflated_gate['steps'][0]['energy_limit_j']*=10
        with self.assertRaisesRegex(ValueError,'inconsistent'):trace_checks(inflated_gate)
        nonfinite=copy.deepcopy(trial);nonfinite['steps'][0]['relative_equation_residual']=float('nan')
        with self.assertRaisesRegex(ValueError,'Nonfinite'):trace_checks(nonfinite)
