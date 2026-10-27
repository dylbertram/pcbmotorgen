"""Evaluate the same midpoint equation with subtraction before mass scaling.

Do not subtract separately assembled large bias-mass vectors to recover a small
ripple residual. The constitutive gradient is still fully nonlinear and the
Newton tangent still includes the same2*M/dt. No numerical gate is relaxed.
"""


def evaluate(static,mass,midpoint,previous,forcing,drive,dt,result):
    if dt<=0:raise ValueError('Positive midpoint interval required')
    difference=midpoint.CreateVector()
    difference.FV().NumPy()[:]=midpoint.FV().NumPy()-previous.FV().NumPy()
    static.Apply(midpoint,result)
    result.data+=(2/dt)*(mass*difference)-drive*forcing
