import argparse
import os
import unittest
import types
import sys
from unittest.mock import patch

from solver_threads import add_thread_option,positive_threads,runtime_metadata,threaded_main


class SolverThreadsTest(unittest.TestCase):
    def test_cli_can_override_the_environment_without_touching_blas(self):
        with patch.dict(os.environ,{'PCB_MOTOR_SOLVER_THREADS':'4','OPENBLAS_NUM_THREADS':'1'}):
            parser=argparse.ArgumentParser();add_thread_option(parser)
            self.assertEqual(parser.parse_args([]).threads,4)
            self.assertEqual(parser.parse_args(['--threads','8']).threads,8)
            self.assertEqual(os.environ['OPENBLAS_NUM_THREADS'],'1')
            self.assertFalse(runtime_metadata()['task_manager_active'])

    def test_invalid_worker_counts_are_rejected(self):
        for value in ['0','-1','129']:
            with self.assertRaises(argparse.ArgumentTypeError):positive_threads(value)

    def test_ngsolve_threads_are_activated_inside_a_task_manager(self):
        events=[]
        class Manager:
            def __enter__(self):events.append('enter')
            def __exit__(self,*args):events.append('exit')
        fake=types.SimpleNamespace(SetNumThreads=lambda count:events.append(count),TaskManager=Manager)
        with patch.dict(sys.modules,{'ngsolve':fake}),patch.object(sys,'argv',['solver.py','--threads','8','--work','case']):
            result=threaded_main(lambda:runtime_metadata())
        self.assertEqual(events,[8,'enter','exit'])
        self.assertEqual(result['ngsolve_task_threads'],8)
        self.assertTrue(result['task_manager_active'])
        self.assertFalse(runtime_metadata()['task_manager_active'])
