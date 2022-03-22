import taichi as ti
import numpy as np
from scipy.sparse import csr_matrix

class TetrahedronMeshDataStructure():
    localFace = ti.Matrix([(1, 2, 3),  (0, 3, 2), (0, 1, 3), (0, 2, 1)])
    localEdge = ti.Matrix([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
    localFace2edge = ti.Matrix([(5, 4, 3), (5, 1, 2), (4, 2, 0), (3, 0, 1)])

def construct(NN, cell):
    NC = cell.shape[0]

    localFace = np.array([(1, 2, 3),  (0, 3, 2), (0, 1, 3), (0, 2, 1)])
    localEdge = np.array([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
    #构建 face
    totalFace = cell[:, localFace].reshape(NC*4, 3)

    _, i0, j = np.unique(
            np.sort(totalFace, axis=1),
            return_index=True,
            return_inverse=True,
            axis=0)
    face = totalFace[i0]

    # 构建 face2cell
    NF = i0.shape[0]
    face2cell = np.zeros((NF, 4), dtype=np.int_)

    i1 = np.zeros(NF, dtype=np.int_)
    i1[j] = np.arange(NC*4)

    face2cell[:, 0] = i0 // 4
    face2cell[:, 1] = i1 // 4
    face2cell[:, 2] = i0 % 4
    face2cell[:, 3] = i1 % 4
    cell2face = np.reshape(j, (NC, 4))

    totalEdge = cell[:, localEdge].reshape(-1, 2)
    edge, i2, j = np.unique(
            np.sort(totalEdge, axis=1),
            return_index=True,
            return_inverse=True,
            axis=0)
    cell2edge = np.reshape(j, (NC, 6))
    return face, edge, cell2edge, cell2face, face2cell

@ti.data_oriented
class TetrahedronMesh():
    def __init__(self, node, cell):

        assert cell.shape[-1] == 4
        assert node.shape[-1] == 3

        NN = node.shape[0]
        GD = node.shape[1]
        self.node = ti.field(ti.f64, (NN, 3))
        self.node.from_numpy(node)

        NC = cell.shape[0]
        self.cell = ti.field(ti.u32, shape=(NC, 4))
        self.cell.from_numpy(cell)
        self.ds = TetrahedronMeshDataStructure()


    def construct_data_structure(self):
        """! 构造四面体网格的辅助数据结构
        """

        NN = self.number_of_nodes()
        cell = self.cell.to_numpy()
        face, edge, cell2edge, cell2face, face2cell = construct(NN, cell)
        NE = edge.shape[0]
        NF = face.shape[0]

        self.edge = ti.field(ti.u32, shape=(NE, 2))
        self.edge.from_numpy(edge)

        self.face = ti.field(ti.u32, shape=(NF, 3))
        self.face.from_numpy(face)

        self.face2cell = ti.field(ti.u32, shape=(NF, 4))
        self.face2cell.from_numpy(face2cell)

        self.cell2edge = ti.field(ti.u32, shape=(NC, 6))
        self.cell2edge.from_numpy(cell2edge)

        self.cell2face = ti.field(ti.u32, shape=(NC, 4))
        self.cell2face.from_numpy(cell2face)

    def geo_dimension(self):
        return 3
    def number_of_nodes(self):
        return self.node.shape[0]

    def number_of_cells(self):
        return self.cell.shape[0]

    def entity(self, etype=2):
        if etype in {'cell', 3}:
            return self.cell
        elif etype in {'face', 2}:
            return self.face
        elif etype in {'edge', 1}:
            return self.edge
        elif etype in {'node', 0}:
            return self.node
        else:
            raise ValueError("`etype` is wrong!")

    def vtk_cell_type(self):
        VTK_TETRA = 10
        return VTK_TETRA

    def to_vtk(self, fname, nodedata=None, celldata=None):
        """

        Parameters
        ----------
        points: vtkPoints object
        cells:  vtkCells object
        pdata:  
        cdata:

        Notes
        -----
        把网格转化为 VTK 的格式
        """
        from fealpy.mesh.vtk_extent import vtk_cell_index, write_to_vtu

        node = self.node.to_numpy()
        GD = self.geo_dimension()

        cell = self.cell.to_numpy(dtype=np.int_)
        cellType = self.vtk_cell_type()
        NV = cell.shape[-1]

        NC = self.number_of_cells()
        cell = np.r_['1', np.zeros((NC, 1), dtype=cell.dtype), cell]
        cell[:, 0] = NV

        print("Writting to vtk...")
        write_to_vtu(fname, node, NC, cellType, cell.flatten(),
                nodedata=nodedata,
                celldata=celldata)

    @ti.func
    def cell_measure(self, c: ti.u32) -> ti.f64:
        """
        计算第i 个单元的体积测度
        """
        V = ti.Matrix.zero(ti.f64, 3, 3)
        for i in ti.static(range(3)):
            for j in ti.static(range(3)):
                V[i, j] = self.node[self.cell[c, i+1], j] - self.node[self.cell[c, 0], j]
        vol = V.determinant()/6.0
        return vol 

    @ti.func
    def grad_lambda(self, c: ti.u32) -> (ti.types.matrix(4, 3, ti.f64), ti.f64):
        """
        计算第 c 个单元上重心坐标函数的梯度，以及单元的面积
        """
        vol = self.cell_measure(c)*6
        glambda = ti.Matrix.zero(ti.f64, 4, 3)
        v = ti.Matrix.zero(ti.f64, 2, 3)
        for i in ti.static(range(4)):
            j = self.ds.localFace[i, 0]
            k = self.ds.localFace[i, 1]
            m = self.ds.localFace[i, 2]
            for l in ti.static(range(3)):
                v[0, l] = self.node[self.cell[c, k], l] - self.node[self.cell[c, j], l]
                v[1, l] = self.node[self.cell[c, m], l] - self.node[self.cell[c, j], l]
            glambda[i, 0] = (v[0, 2]*v[1, 1] - v[0, 1]*v[1, 2])/vol
            glambda[i, 1] = (v[0, 0]*v[1, 2] - v[0, 2]*v[1, 0])/vol 
            glambda[i, 2] = (v[0, 1]*v[1, 0] - v[0, 0]*v[1, 1])/vol 
        return glambda, vol/6

    @ti.kernel
    def cell_stiff_matrices(self, S: ti.template()):
        """
        计算网格上的所有单元刚度矩阵
        """
        for c in range(self.cell.shape[0]):
            gphi, vol = self.grad_lambda(c) 

            S[c, 0, 0] = vol*(gphi[0, 0]*gphi[0, 0] + gphi[0, 1]*gphi[0, 1]+ gphi[0, 2]*gphi[0, 2])
            S[c, 0, 1] = vol*(gphi[0, 0]*gphi[1, 0] + gphi[0, 1]*gphi[1, 1]+ gphi[0, 2]*gphi[1, 2])
            S[c, 0, 2] = vol*(gphi[0, 0]*gphi[2, 0] + gphi[0, 1]*gphi[2, 1]+ gphi[0, 2]*gphi[2, 2])
            S[c, 0, 3] = vol*(gphi[0, 0]*gphi[3, 0] + gphi[0, 1]*gphi[3, 1]+ gphi[0, 2]*gphi[3, 2])

            S[c, 1, 0] = S[c, 0, 1]
            S[c, 1, 1] = vol*(gphi[1, 0]*gphi[1, 0] + gphi[1, 1]*gphi[1, 1]+ gphi[1, 2]*gphi[1, 2])
            S[c, 1, 2] = vol*(gphi[1, 0]*gphi[2, 0] + gphi[1, 1]*gphi[2, 1]+ gphi[1, 2]*gphi[2, 2])
            S[c, 1, 3] = vol*(gphi[1, 0]*gphi[3, 0] + gphi[1, 1]*gphi[3, 1]+ gphi[1, 2]*gphi[3, 2])

            S[c, 2, 0] = S[c, 0, 2]
            S[c, 2, 1] = S[c, 1, 2]
            S[c, 2, 2] = vol*(gphi[2, 0]*gphi[2, 0] + gphi[2, 1]*gphi[2, 1]+ gphi[2, 2]*gphi[2, 2])
            S[c, 2, 3] = vol*(gphi[2, 0]*gphi[3, 0] + gphi[2, 1]*gphi[3, 1]+ gphi[2, 2]*gphi[3, 2])

            S[c, 3, 0] = S[c, 0, 3]
            S[c, 3, 1] = S[c, 1, 3]
            S[c, 3, 2] = S[c, 2, 3]
            S[c, 3, 3] = l*(gphi[3, 0]*gphi[3, 0] + gphi[3, 1]*gphi[3, 1]+ gphi[3, 2]*gphi[3, 2])

    @ti.kernel
    def cell_mass_matrices(self, S: ti.template()):
        """
        计算网格上的所有单元质量矩阵
        """
        for c in range(self.cell.shape[0]):

            vol = self.cell_measure(c)
            c0 = vol/10.0
            c1 = vol/20.0

            S[c, 0, 0] = c0 
            S[c, 0, 1] = c1
            S[c, 0, 2] = c1
            S[c, 0, 3] = c1

            S[c, 1, 0] = c1 
            S[c, 1, 1] = c0  
            S[c, 1, 2] = c1
            S[c, 1, 3] = c1

            S[c, 2, 0] = c1 
            S[c, 2, 1] = c1 
            S[c, 2, 2] = c0 
            S[c, 2, 3] = c1 

            S[c, 3, 0] = c1 
            S[c, 3, 1] = c1 
            S[c, 3, 2] = c1 
            S[c, 3, 3] = c0 

    @ti.kernel
    def cell_convection_matrices(self, u: ti.template(), S:ti.template()):
        """! 计算网格上所有单元的对流矩阵

        The continuous weak foumulation

        \f[ (\\boldsymbol\cdot \\nabla\phi, v) \f]

        where \f$\\boldsymbol\f$ is the velocity field, \f$\phi\f$ is trial
        function, and \f$ v \f$ is test function.

        @param[in] u  Taichi field with shape (NN, 3)
        @param[in, out] S  Taichi field with shape (NN, 4, 4)

        See Also
        -------
        """
        for c in range(self.cell.shape[0]):
            gphi, vol = self.grad_lambda(c) 

            c0 = vol/10.0
            c1 = vol/20.0

            U = ti.Matrix.zero(ti.f64, 4, 3)

            for i in ti.static(range(3)):
                U[0, i] += u[self.cell[c, 0], i]*c0 
                U[0, i] += u[self.cell[c, 1], i]*c1 
                U[0, i] += u[self.cell[c, 2], i]*c1 
                U[0, i] += u[self.cell[c, 3], i]*c1

            for i in ti.static(range(3)):
                U[1, i] += u[self.cell[c, 0], i]*c1 
                U[1, i] += u[self.cell[c, 1], i]*c0 
                U[1, i] += u[self.cell[c, 2], i]*c1 
                U[1, i] += u[self.cell[c, 3], i]*c1

            for i in ti.static(range(3)):
                U[2, i] += u[self.cell[c, 0], i]*c1 
                U[2, i] += u[self.cell[c, 1], i]*c1 
                U[2, i] += u[self.cell[c, 2], i]*c0 
                U[2, i] += u[self.cell[c, 3], i]*c1

            for i in ti.static(range(3)):
                U[3, i] += u[self.cell[c, 0], i]*c1 
                U[3, i] += u[self.cell[c, 1], i]*c1 
                U[3, i] += u[self.cell[c, 2], i]*c1 
                U[3, i] += u[self.cell[c, 3], i]*c0

            for i in ti.static(range(4)):
                for j in ti.static(range(4)):
                    S[c, i, j] = U[i, 0]*gphi[j, 0] + U[i, 1]*gphi[j, 1] + U[i, 2]*gphi[j, 2]

    @ti.kernel
    def cell_source_vectors(self, f:ti.template(), bc:ti.template(), ws:ti.template(), F:ti.template()):
        """
        计算所有单元载荷
        """
        for c in range(self.cell.shape[0]):
            x0 = self.node[self.cell[c, 0], 0]
            y0 = self.node[self.cell[c, 0], 1]
            z0 = self.node[self.cell[c, 0], 2]

            x1 = self.node[self.cell[c, 1], 0]
            y1 = self.node[self.cell[c, 1], 1]
            z1 = self.node[self.cell[c, 1], 2]

            x2 = self.node[self.cell[c, 2], 0]
            y2 = self.node[self.cell[c, 2], 1]
            z2 = self.node[self.cell[c, 2], 2]

            x3 = self.node[self.cell[c, 3], 0]
            y3 = self.node[self.cell[c, 3], 1]
            z3 = self.node[self.cell[c, 3], 2]

            l1 = (x1 - x0)*((y2 - y0)*(z3 - z0) - (z2 - z0)*(y3 - y0))
            l2 = (y1 - y0)*((x3 - x0)*(z2 - z0) - (z3 - z0)*(x2 - x0))
            l3 = (z1 - x0)*((x2 - x0)*(y3 - y0) - (x3 - x0)*(y2 - y0))

            l = (l1 + l2 + l3)/6
            for q in ti.static(range(bc.n)):
                x = x0*bc[q, 0] + x1*bc[q, 1] + x2*bc[q, 2] + x3*bc[q, 3]
                y = y0*bc[q, 0] + y1*bc[q, 1] + y2*bc[q, 2] + y3*bc[q, 3]
                z = z0*bc[q, 0] + z1*bc[q, 1] + z2*bc[q, 2] + z3*bc[q, 3]
                r = f(x, y, z)
                for i in ti.static(range(4)):
                    F[c, i] += ws[q]*bc[q, i]*r

            for i in range(4):
                F[c, i] *= l

    def stiff_matrix(self, c=None):
        """
        组装总体刚度矩阵
        """
        NC = self.number_of_cells()

        K = ti.field(ti.f64, (NC, 4, 4))
        self.cell_stiff_matrices(K)

        M = K.to_numpy()
        if c is not None:
            M *= c # 目前假设 c 为一常数

        cell = self.cell.to_numpy()
        I = np.broadcast_to(cell[:, :, None], shape=M.shape)
        J = np.broadcast_to(cell[:, None, :], shape=M.shape)

        NN = self.number_of_nodes()
        M = csr_matrix((K.to_numpy().flat, (I.flat, J.flat)), shape=(NN, NN))
        return M

    def mass_matrix(self, c=None):
        """
        组装总体质量矩阵
        """
        NC = self.number_of_cells()

        K = ti.field(ti.f64, (NC, 4, 4))
        self.cell_mass_matrices(K)

        M = K.to_numpy()
        if c is not None:
            M *= c

        cell = self.cell.to_numpy()
        I = np.broadcast_to(cell[:, :, None], shape=M.shape)
        J = np.broadcast_to(cell[:, None, :], shape=M.shape)

        NN = self.number_of_nodes() 
        M = csr_matrix((M.flat, (I.flat, J.flat)), shape=(NN, NN))
        return M

    def convection_matrix(self, u):
        """
        组装总体对流矩阵
        """

        NC = self.number_of_cells() 

        C = ti.field(ti.f64, (NC, 4, 4))
        self.cell_convection_matrices(u, C)

        M = C.to_numpy()

        cell = self.cell.to_numpy()
        I = np.broadcast_to(cell[:, :, None], shape=M.shape)
        J = np.broadcast_to(cell[:, None, :], shape=M.shape)

        NN = self.number_of_nodes()
        M = csr_matrix((M.flat, (I.flat, J.flat)), shape=(NN, NN))
        return M

    def source_vector(self, f):
        """
        组装总体载荷向量
        """
        NN = self.node.shape[0]
        NC = self.cell.shape[0]
        bc = ti.Matrix([
            [0.5854101966249680,	0.1381966011250110,
                0.1381966011250110,	0.1381966011250110],
            [0.1381966011250110,	0.5854101966249680,
                0.1381966011250110,	0.1381966011250110],
            [0.1381966011250110,	0.1381966011250110,
                0.5854101966249680,	0.1381966011250110],
            [0.1381966011250110,	0.1381966011250110,
                0.1381966011250110,	0.5854101966249680]], dt=ti.f64)
        ws = ti.Vector([0.25, 0.25, 0.25, 0.25], dt=ti.f64)

        F = ti.field(ti.f64, (NC, 4))
        self.cell_source_vectors(f, bc, ws, F)

        bb = F.to_numpy()
        F = np.zeros(NN, dtype=np.float64)
        cell = self.cell.to_numpy()
        np.add.at(F, cell, bb)
        return F

    @ti.kernel
    def linear_scalar_interpolation(self, f: ti.template(), R: ti.template()):
        """! 定义在三维区域中的标量函数的线性插值
        """
        for i in range(self.node.shape[0]):
            R[i] = f(self.node[i, 0], self.node[i, 1], self.node[i, 2])

    @ti.kernel
    def linear_vector_interpolation(self, f: ti.template(), R: ti.template()):
        """! 定义在三维区域中的向量函数的线性插值
        """
        for i in range(self.node.shape[0]):
            R[i, 0], R[i, 1], R[i, 2] = f(self.node[i, 0], self.node[i, 1], self.node[i, 2])
