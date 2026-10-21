"""Explicit NGSolve task threads, kept separate from nested BLAS thread pools."""
import argparse
import os

_active_threads=None


def positive_threads(value):
    count=int(value)
    if not 1<=count<=128:raise argparse.ArgumentTypeError('solver threads must be in [1,128]')
    return count


def add_thread_option(parser):
    parser.add_argument('--threads',type=positive_threads,default=os.environ.get('PCB_MOTOR_SOLVER_THREADS','1'),
        help='NGSolve task threads; default PCB_MOTOR_SOLVER_THREADS or 1 for reproducibility; BLAS pools remain separate')


def runtime_metadata():
    return {'ngsolve_task_threads':_active_threads,'task_manager_active':_active_threads is not None,
        'blas_environment':{name:os.environ.get(name) for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','MKL_NUM_THREADS']}}


def threaded_main(main):
    global _active_threads
    parser=argparse.ArgumentParser(add_help=False);add_thread_option(parser)
    options,unknown=parser.parse_known_args()
    if '-h' in unknown or '--help' in unknown:return main()
    import ngsolve as ng
    ng.SetNumThreads(options.threads)
    _active_threads=options.threads
    try:
        with ng.TaskManager():return main()
    finally:_active_threads=None
