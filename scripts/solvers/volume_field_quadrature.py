"""Physical-volume quadrature of an archived FE vector field in affine cells."""
import numpy as np


def sample(ng,mesh,field,region,degree):
    rule=ng.IntegrationRule(ng.ET.TET,degree)
    local=np.array([point.point[:3] for point in rule]);weights=np.array([point.weight for point in rule])
    corners=ng.IntegrationRule(points=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)],weights=[1.,1.,1.,1.])
    xyz=ng.CoefficientFunction((ng.x,ng.y,ng.z));points=[];values=[];physical_weights=[]
    for element in mesh.Elements(ng.VOL):
        if element.mat!=region:continue
        if element.type!=ng.ET.TET:raise ValueError('Only tetrahedral volume quadrature is supported')
        transform=mesh.GetTrafo(element);vertices=np.asarray(xyz(transform(corners))).reshape(4,3)
        matrix=vertices[1:]-vertices[0];det=abs(float(np.linalg.det(matrix)));mapped=transform(rule)
        physical=np.asarray(xyz(mapped)).reshape(-1,3)
        if det<=0 or np.max(abs(physical-(vertices[0]+local@matrix)))>1e-12:
            raise ValueError('Curved cells need physical Jacobian weights, not affine ones')
        vector=np.asarray(field(mapped),dtype=float).reshape(-1,3)
        if vector.shape!=physical.shape or not np.isfinite(vector).all():raise ValueError('Invalid material field')
        points.append(physical);values.append(vector);physical_weights.append(weights*det)
    if not points:raise ValueError('Missing requested material volume')
    return np.concatenate(points),np.concatenate(values),np.concatenate(physical_weights)
