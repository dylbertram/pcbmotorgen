import json
from pathlib import Path
import tempfile
import unittest

from run_dc_saved_host_acceptance import cargo_command,completed_host_result,host_environment


class ActualSavedHostAcceptanceTest(unittest.TestCase):
    def test_cargo_symlink_must_keep_its_dispatch_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'rustup';target.write_text('not executed')
            cargo=root/'cargo';cargo.symlink_to(target)
            command=cargo_command(cargo,root)
            self.assertEqual(command[3],str(cargo.absolute()))
            self.assertNotEqual(command[3],str(cargo.resolve()))

    def test_python_symlink_must_keep_its_virtualenv_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=root/'base-python';base.write_text('not executed');venv=root/'venv/bin'
            venv.mkdir(parents=True);python=venv/'python';python.symlink_to(base)
            result=host_environment({},root/'project',root/'study',python,root,root,root/'cargo')
            self.assertEqual(result['PCB_MOTOR_DC_PYTHON'],str(python.absolute()))
            self.assertNotEqual(result['PCB_MOTOR_DC_PYTHON'],str(python.resolve()))

    def test_clean_host_paths_do_not_reuse_developer_pythonpath(self):
        original=dict(PYTHONPATH='developer-only',PCB_MOTOR_DC_QUALIFY_CIRCULAR='1',OTHER='preserved')
        result=host_environment(original,*map(Path,['/actual/project','/actual/study','/pinned/python','/solver','/archive','/cargo/bin/cargo']))
        self.assertNotIn('PYTHONPATH',result);self.assertNotIn('PCB_MOTOR_DC_QUALIFY_CIRCULAR',result)
        self.assertEqual(result['PCB_MOTOR_DC_STUDY_REQUEST_PATH'],'/actual/study')
        self.assertEqual(original['PYTHONPATH'],'developer-only');self.assertEqual(result['OTHER'],'preserved')

    def test_only_the_selected_cases_real_completed_result_is_accepted(self):
        value=dict(state='completed',result=dict(qualified_case=dict(case_id='actual')))
        text='running test\n'+json.dumps(value)+'\n'
        self.assertEqual(completed_host_result(text,'actual'),value)
        for bad in [text+json.dumps(value),text.replace('actual','fixture'),'no result']:
            with self.assertRaises(ValueError):completed_host_result(bad,'actual')
