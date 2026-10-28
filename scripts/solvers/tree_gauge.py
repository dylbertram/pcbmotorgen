"""Exact lowest-edge tree gauge for a simply connected HCurl mesh.

Dirichlet-boundary vertices form one root. Fixing one edge per interior vertex
removes the remaining lowest-order gradient kernel. Higher-order gradients
must already be removed by HCurl(nograds=True). No penalty term is added.
This helper does not support multiply connected global field domains.
"""


def tree_edges(vertices,edges,boundary_vertices):
    vertices=set(vertices);boundary=set(boundary_vertices)
    if not boundary or not boundary<=vertices:raise ValueError('Need an explicit nonempty exterior root')
    root=object();parent={value:value for value in vertices};parent[root]=root
    def find(value):
        while parent[value]!=value:
            parent[value]=parent[parent[value]];value=parent[value]
        return value
    for vertex in boundary:parent[vertex]=root
    selected=[]
    for edge,a,b in edges:
        if a not in vertices or b not in vertices:raise ValueError('Edge endpoint outside mesh graph')
        x,y=find(a),find(b)
        if x!=y:parent[x]=y;selected.append(edge)
    if any(find(vertex)!=find(root) for vertex in vertices):raise ValueError('Disconnected field mesh')
    if len(selected)!=len(vertices)-len(boundary):raise ValueError('Invalid rooted spanning-tree dimension')
    return selected


def free_dofs(ng,mesh,compound_space,a_space):
    edges=[];boundary=set();dofs={};a_free=a_space.FreeDofs()
    for edge in mesh.edges:
        a,b=[vertex.nr for vertex in edge.vertices]
        values=a_space.GetDofNrs(ng.NodeId(ng.EDGE,edge.nr))
        active=[value for value in values if value>=0]
        if len(active)!=1:raise ValueError('Remove higher gradient modes before applying the lowest-edge tree gauge')
        dof=active[0];dofs[edge.nr]=dof;edges.append((edge.nr,a,b))
        if not a_free[dof]:boundary.update([a,b])
    chosen=tree_edges([vertex.nr for vertex in mesh.vertices],edges,boundary)
    result=ng.BitArray(compound_space.ndof)
    for index,flag in enumerate(compound_space.FreeDofs()):result[index]=flag
    for edge in chosen:
        if not result[dofs[edge]]:raise ValueError('Tree selected an already-fixed boundary edge')
        result[dofs[edge]]=False
    return result,len(chosen)
