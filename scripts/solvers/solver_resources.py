"""Read solver-reported resource measurements; do not invent process peaks."""
import math
import re


def getdp_resources(log):
    dofs=re.findall(r'System\s+\d+/\d+:\s+(\d+)\s+Dofs',log)
    stops=re.findall(r'^\s*Info\s*:\s*Stopped .*?Wall\s*=\s*([^s,]+)s,\s*CPU\s*=\s*([^s,]+)s,\s*Mem\s*=\s*([^M,)]+)Mb',log,re.M)
    result={}
    if dofs:
        value=max(map(int,dofs))
        if value<=0:raise ValueError('Invalid solver DOF measurement')
        result['max_reported_dofs']=value
    if stops:
        wall,cpu,memory=map(float,stops[-1])
        if not all(math.isfinite(value) and value>=0 for value in [wall,cpu,memory]):raise ValueError('Invalid solver resource measurement')
        result.update(solver_reported_wall_seconds=wall,solver_reported_cpu_seconds=cpu,
                      solver_reported_final_memory_mb=memory,
                      memory_scope='GetDP Stopped log measurement, not an independently sampled peak RSS')
    return result
