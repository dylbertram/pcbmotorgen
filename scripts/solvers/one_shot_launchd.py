"""Explicit one-shot native job, never installed in a login/startup directory.

Do not use launchctl submit: its OnDemand=false job may restart after exit.
An explicit KeepAlive=false/RunAtLoad=true plist runs once per bootstrap.
"""
import os
from pathlib import Path
import plistlib
import subprocess


def job_spec(label,arguments,work,environment=None):
    work=Path(work).resolve()
    if not label.startswith('com.pcbmotorgen.dc.') or '/' in label:raise ValueError('Explicit owned PCB motor job label required')
    if not arguments or any(not isinstance(value,str) or not value for value in arguments):raise ValueError('Explicit program argv required')
    if not Path(arguments[0]).is_absolute() or not work.is_dir():raise ValueError('Absolute program and existing evidence directory required')
    return dict(Label=label,ProgramArguments=arguments,WorkingDirectory=str(work),KeepAlive=False,RunAtLoad=True,
        StandardOutPath=str(work/(label+'.stdout.log')),StandardErrorPath=str(work/(label+'.stderr.log')),
        EnvironmentVariables=environment or {},AbandonProcessGroup=False)


def bootstrap(label,arguments,work,environment=None):
    spec=job_spec(label,arguments,work,environment);domain='gui/'+str(os.getuid());path=Path(work)/(label+'.plist')
    # Refuse any occupied label or evidence file, never replace an earlier job.
    if subprocess.run(['launchctl','print',domain+'/'+label],capture_output=True).returncode==0:
        raise ValueError('Owned launchd label already exists; inspect before reusing')
    with path.open('xb') as stream:plistlib.dump(spec,stream)
    subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
    return dict(label=label,domain=domain,plist=str(path.resolve()),keep_alive=False,run_at_load=True)
