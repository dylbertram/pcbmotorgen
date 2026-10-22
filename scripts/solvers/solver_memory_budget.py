"""Opt-in native macOS physical-footprint budget for an owned solver group.

This is a sampled safety stop, not a guaranteed kernel allocation limit.
It does not change numerical tolerances, fields or qualification gates.
"""
import ctypes
import errno
import os
import subprocess
import sys
import time


class MemoryBudgetExceeded(RuntimeError):
    pass


class DarwinRusageV2(ctypes.Structure):
    # macOS SDK sys/resource.h rusage_info_v2, RUSAGE_INFO_V2=2.
    _fields_=[('uuid',ctypes.c_uint8*16)]+[(name,ctypes.c_uint64) for name in [
        'user_time','system_time','pkg_idle_wkups','interrupt_wkups','pageins',
        'wired_size','resident_size','phys_footprint','proc_start_abstime','proc_exit_abstime',
        'child_user_time','child_system_time','child_pkg_idle_wkups','child_interrupt_wkups',
        'child_pageins','child_elapsed_abstime','diskio_bytesread','diskio_byteswritten']]


def exited(pid):
    state=subprocess.run(['ps','-o','stat=','-p',str(pid)],capture_output=True,text=True,timeout=5).stdout.strip()
    return not state or state.startswith('Z')


def process_memory(pid):
    if sys.platform!='darwin':raise ValueError('Native physical-footprint guard requires macOS; no silent RSS substitution')
    info=DarwinRusageV2();lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    query=lib.proc_pid_rusage;query.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p];query.restype=ctypes.c_int
    if query(pid,2,ctypes.byref(info)):
        error=ctypes.get_errno()
        if error in [errno.ESRCH,errno.ENOENT]:return None
        # An exited-but-unreaped child holds no memory, and macOS refuses its
        # rusage with EPERM. Only a confirmed zombie or vanished PID is skipped.
        if error==errno.EPERM and exited(pid):return None
        raise OSError(error,'Cannot observe native solver memory')
    return dict(pid=pid,resident_bytes=info.resident_size,physical_footprint_bytes=info.phys_footprint)


def group_memory(group):
    if type(group) is not int or group<=1:raise ValueError('Safe owned process group required')
    rows=subprocess.check_output(['ps','-axo','pid=,pgid='],text=True,timeout=5).splitlines()
    pids=[int(row.split()[0]) for row in rows if len(row.split())==2 and int(row.split()[1])==group]
    values=[value for pid in pids if (value:=process_memory(pid)) is not None]
    return dict(physical_footprint_bytes=sum(value['physical_footprint_bytes'] for value in values),
        resident_bytes=sum(value['resident_bytes'] for value in values),processes=values,
        scope='Sum of native proc_pid_rusage physical footprint in owned POSIX group; sampled, not a hard allocation limit')


def wait_guarded(process,timeout,limit,on_sample,interval=1.,observe=group_memory):
    if type(limit) is not int or limit<=0:raise ValueError('Positive integer native memory budget required')
    started=time.monotonic();peak=0
    while True:
        remaining=timeout-(time.monotonic()-started)
        if remaining<=0:raise subprocess.TimeoutExpired(process.args,timeout)
        value=observe(process.pid);peak=max(peak,value['physical_footprint_bytes'])
        on_sample(dict(value,peak_physical_footprint_bytes=peak,limit_bytes=limit,elapsed_seconds=time.monotonic()-started))
        if value['physical_footprint_bytes']>limit:
            raise MemoryBudgetExceeded(f'Owned solver physical footprint {value["physical_footprint_bytes"]} exceeds declared {limit} byte budget')
        try:return process.wait(timeout=min(interval,remaining))
        except subprocess.TimeoutExpired:pass
