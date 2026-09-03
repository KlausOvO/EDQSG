# -*- coding: utf-8 -*-
"""PSO-GCA（灰色关联 + 粒子群优化权重）独立实现 —— 供审阅。

流程：灰色关联系数（正理想=1、负理想=0）→ TOPSIS 式相对贴近度 → 以“扩大
评价对象得分差异（区分度）”为目标，PSO 优化指标权重。

PSO 参数为通用设置（论文表述：为保证复现性，固定粒子数、迭代次数、学习因子、
惯性权重与随机种子，具体参数见实验设置），不作为“原文参数”表述。

运行：python pso_gca_method.py
"""

import numpy as np

PSO_CONFIG = {"swarm": 50, "iterations": 200, "c1": 2.0, "c2": 2.0,
              "inertia": 0.7, "seed": 20260720, "rho_gray": 0.5}


def gray_coefficients(X, rho=0.5):
    d_pos = np.abs(1.0 - X)
    d_neg = np.abs(0.0 - X)
    dmax_pos = d_pos.max() if d_pos.size else 1.0
    dmin_pos = d_pos.min() if d_pos.size else 0.0
    dmax_neg = d_neg.max() if d_neg.size else 1.0
    dmin_neg = d_neg.min() if d_neg.size else 0.0
    xi_pos = (dmin_pos + rho * dmax_pos) / (d_pos + rho * dmax_pos)
    xi_neg = (dmin_neg + rho * dmax_neg) / (d_neg + rho * dmax_neg)
    return xi_pos, xi_neg


def pso_gca(X):
    rng = np.random.default_rng(PSO_CONFIG["seed"])
    n, m = X.shape
    xi_pos, xi_neg = gray_coefficients(X, PSO_CONFIG["rho_gray"])

    def scores_of(w):
        gp = xi_pos @ w
        gn = xi_neg @ w
        return 100.0 * (gp / (gp + gn))

    def J(w):
        g = scores_of(w)
        return float(np.mean(np.abs(g - g.mean())))

    def project(w):
        w = np.clip(w, 0.0, None)
        s = w.sum()
        return w / s if s > 0 else np.full_like(w, 1.0 / len(w))

    swarm, iters, c1, c2, inertia = (PSO_CONFIG["swarm"], PSO_CONFIG["iterations"],
                                     PSO_CONFIG["c1"], PSO_CONFIG["c2"], PSO_CONFIG["inertia"])
    pos = np.array([project(rng.random(m)) for _ in range(swarm)])
    vel = np.zeros((swarm, m))
    pbest = pos.copy()
    pbest_f = np.array([J(p) for p in pos])
    gbest = pbest[int(np.argmax(pbest_f))]
    gbest_f = float(pbest_f.max())
    for _ in range(iters):
        r1 = rng.random((swarm, m))
        r2 = rng.random((swarm, m))
        vel = inertia * vel + c1 * r1 * (pbest - pos) + c2 * r2 * (gbest - pos)
        pos = np.array([project(p + v) for p, v in zip(pos, vel)])
        f = np.array([J(p) for p in pos])
        improved = f > pbest_f
        pbest[improved] = pos[improved]
        pbest_f[improved] = f[improved]
        if f.max() > gbest_f:
            gbest_f = float(f.max())
            gbest = pos[int(np.argmax(f))]
    return gbest, [float(x) for x in scores_of(gbest)]


if __name__ == "__main__":
    X = np.array([[1.0, 1.0], [1.0, 0.99], [1.0, 0.98], [1.0, 0.96],
                  [1.0, 0.94], [1.0, 0.92], [1.0, 0.88]])
    w, scores = pso_gca(X)
    print("PSO 参数:", PSO_CONFIG)
    print("优化权重 w =", [round(float(x), 4) for x in w])
    print("G 序列   =", [round(s, 1) for s in scores])
    print("区分度 D_G =", round(float(np.mean(np.abs(np.asarray(scores) - np.mean(scores)))), 2))
