import copy
import unittest

from prepare_linear_dc_designs import derive


class DeclaredLinearDesignTest(unittest.TestCase):
    def test_only_selected_new_design_changes_original_and_materials_preserved(self):
        state=dict(cad_geometry=None,mover_position_mm=.5,config=dict(topology='linear',desired_travel_mm=1.,num_layers=2,drive=dict(inner_copper_oz=1.),backplane=dict(layers=['saved'])))
        source=dict(versions=[dict(state=copy.deepcopy(state)),dict(state=copy.deepcopy(state))]);before=copy.deepcopy(source)
        case=dict(id='new-linear',config_overrides=dict(num_layers=4),drive_overrides=dict(inner_copper_oz=2.))
        result=derive(source,1,case)
        self.assertEqual(source,before);self.assertEqual(result['versions'][0],source['versions'][0])
        config=result['versions'][1]['state']['config'];self.assertEqual(config['num_layers'],4)
        self.assertEqual(config['backplane'],state['config']['backplane']);self.assertEqual(config['drive']['inner_copper_oz'],2.)
        for key,value in [('topology','rotary'),('backplane',{}),('unknown',3)]:
            bad=copy.deepcopy(case);bad['config_overrides']={key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):derive(source,1,bad)
        with self.assertRaises(ValueError):derive(source,True,case)
        bad=copy.deepcopy(case);bad['config_overrides']['desired_travel_mm']=.1
        with self.assertRaisesRegex(ValueError,'no automatic clamp'):derive(source,1,bad)
        bad['state_overrides']={'mover_position_mm':.05}
        self.assertEqual(derive(source,1,bad)['versions'][1]['state']['mover_position_mm'],.05)
