import numpy as np
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from fealpy.mesh.uniform_mesh_2d import UniformMesh2d
from scipy.sparse.linalg import spsolve
from fealpy.decorator import cartesian
class MembraneOscillationPDEData: 

    def __init__(self, D=[0, 1, 0, 1], T=[0, 5]):
        """
        @brief 模型初始化函数

        @param[in] D 模型空间定义域
        @param[in] T 模型时间定义域
        """
        self._domain = D
        self._duration = T

    def domain(self):
        """
        @brief 空间区间
        """
        return self._domain

    def duration(self):
        """
        @brief 时间区间
        """
        return self._duration


    @cartesian
    def source(self, p, t):
        """
        @brief 方程右端项 
        
        @param[in] p numpy.ndarray, 空间点
        @param[in] t float, 时间点 

        @return 0
        """
        return np.zeros_like(p[..., 0])

    @cartesian
    def init_solution(self, p):
        """
        @brief 初值条件

        @param[in] p numpy.ndarray, 空间点
        @param[in] t float, 时间点 

        @return 返回 val
        """

        x, y = p[..., 0], p[..., 1]
      
        val = x**2*(x+y)
        return val

    @cartesian
    def init_solution_diff_t(self, p):
        """
         @brief 初值条件的导数

         @param[in] p numpy.ndarray, 空间点
        """
        return np.zeros_like(p[..., 0])

    @cartesian
    def dirichlet(self, p, t):
        """
        @brief Dirichlet 边界条件

        @param[in] p numpy.ndarray, 空间点
        @param[in] t float, 时间点 

        @return 边界条件函数值
        """
        return np.zeros_like(p[..., 0])

pde = MembraneOscillationPDEData()
domain = pde.domain()

# 空间离散
domain = pde.domain()
nx = 100
ny = 100
hx = (domain[1] - domain[0])/nx
hy = (domain[3] - domain[2])/ny
mesh = UniformMesh2d([0, nx, 0, ny], h=(hx, hy), origin=(domain[0], domain[2]))

# 时间离散
duration = pde.duration()
nt = 1000
tau = (duration[1] - duration[0])/nt
# 准备初值
uh0 = mesh.interpolate(pde.init_solution, 'node') # （nx+1, ny+1)
vh0 = mesh.interpolate(pde.init_solution_diff_t, 'node') # (nx+1, ny+1)
uh1 = mesh.function('node') # (nx+1, ny+1)
def advance_implicit(n, *frags):
    """
    @brief 时间步进为隐格式

    @param[in] n int, 表示第 n 个时间步
    """
    t = duration[0] + n*tau
    if n == 0:
        return uh0, t
    elif n == 1:
        rx = tau/hx
        ry = tau/hy
        uh1[1:-1, 1:-1] = 0.5*rx**2*(uh0[0:-2, 1:-1] + uh0[2:, 1:-1]) + \
                0.5*ry**2*(uh0[1:-1, 0:-2] + uh0[1:-1, 2:]) + \
                (1 - rx**2 - ry**2)*uh0[1:-1, 1:-1] + tau*vh0[1:-1, 1:-1]
        gD = lambda p: pde.dirichlet(p, t)
        mesh.update_dirichlet_bc(gD, uh1)
        return uh1, t
    else:
        A0, A1, A2 = mesh.wave_operator_implicit(tau) 
        source = lambda p: pde.source(p, t + tau)
        f = mesh.interpolate(source, intertype='node')
        f *= tau**2
        f.flat += A1@uh1.flat + A2@uh0.flat

        uh0[:] = uh1[:]
        gD = lambda p: pde.dirichlet(p, t + tau)
        A0, f = mesh.apply_dirichlet_bc(gD, A0, f)
        uh1.flat = spsolve(A0, f)


        return uh1, t
box = [0, 1, 0, 1, -1, 1]

fig = plt.figure()
axes = fig.add_subplot(111, projection='3d')
mesh.show_animation(fig, axes, box, advance_implicit,
                    fname='implicit_test!!!!!.mp4', plot_type='surface', frames=nt+1)
plt.show()
