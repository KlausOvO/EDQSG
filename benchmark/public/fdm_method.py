# -*- coding: utf-8 -*-
"""FDM（等先验模糊决策图）独立实现 —— 供审阅与三项自检。

按岳明桥等流程：
  1) 等先验 Saaty 判断矩阵（全 1）→ 初始权重 z=(0.2,...,0.2)；
  2) 影响矩阵 E[k,j] = 指标 k 对指标 j 的影响强度（取 EDQSG 式(10) 三源校准
     关系强度 a_ij，非可信度 c_ij、非根因贡献 RC）；
  3) 迭代 C_(t+1)=tanh(C_(t)·E)，C* = Σ_{t>=1} C_(t)；
  4) ω = norm(z_bar + C_bar·z_bar)，其中 z_bar=z/max(z)，
     C_bar=C*/γ，γ=max_i Σ_j C*_ij；
  5) G_FDM = ω·v（v 为各指标已知期望分）。

运行：python fdm_method.py
"""

import numpy as np


def fdm_steady_matrix(E, tol=1e-12, max_iter=1000):
    """C_(t+1)=tanh(C_(t)·E)，C*=Σ_{t≥1} C_(t)。"""
    E = np.asarray(E, dtype=float)
    n = E.shape[0]
    C = np.eye(n)
    C_star = np.zeros((n, n), dtype=float)
    for _ in range(max_iter):
        C_next = np.tanh(C @ E)
        C_star += C_next
        if np.max(np.abs(C_next)) < tol:
            break
        C = C_next
    else:
        raise RuntimeError("FDM iteration did not converge; check E.")
    return C_star


def fdm_weights(E):
    """等先验 FDM 权重：z=1/n → C* → ω=norm(z_bar + C_bar·z_bar)。"""
    E = np.asarray(E, dtype=float)
    n = E.shape[0]
    z = np.ones(n) / n
    C_star = fdm_steady_matrix(E)
    z_bar = z / np.max(z)
    gamma = np.max(np.sum(C_star, axis=1))
    C_bar = C_star / gamma if gamma > 0 else C_star.copy()
    omega_raw = z_bar + C_bar @ z_bar
    omega = omega_raw / np.sum(omega_raw)
    return omega, C_star


if __name__ == "__main__":
    # 装备构造算例（论文表 9）
    indicators = ["DQ6", "DQ2", "DQ5", "SG3", "SG7"]
    scores = np.array([78.9, 71.8, 96.3, 66.9, 76.4])
    # 三源校准关系强度 a_ij（EDQSG 式(10)，本算例三源一致）
    couplings = {("SG3", "DQ6"): 0.80, ("SG7", "DQ5"): 0.60, ("SG7", "DQ2"): 0.50}
    idx = {k: i for i, k in enumerate(indicators)}
    E = np.zeros((5, 5))
    for (src, dst), a in couplings.items():
        E[idx[src], idx[dst]] = a

    omega, C_star = fdm_weights(E)
    G = float(omega @ scores)

    print("指标顺序:", indicators)
    print("指标分数 v =", scores.tolist())
    print("三源关系强度 a_ij =", {f"{s}->{d}": a for (s, d), a in couplings.items()})
    print("影响矩阵 E =\n", E)
    print("C* =\n", np.round(C_star, 4))
    print("FDM 权重 ω =", dict(zip(indicators, np.round(omega, 4))))
    print("自检1  Σω =", round(float(omega.sum()), 6), "->", "通过" if abs(omega.sum() - 1.0) < 1e-9 else "失败")
    print(f"自检2  G_FDM = {G:.2f}  ∈ [{scores.min():.1f}, {scores.max():.1f}] ->",
          "通过" if scores.min() <= G <= scores.max() else "失败")
    # E=0 退化等权
    omega0, _ = fdm_weights(np.zeros((5, 5)))
    G0 = float(omega0 @ scores)
    print("自检3  E=0: ω =", np.round(omega0, 4), f" G = {G0:.2f} ->",
          "通过（退化为等权）" if np.allclose(omega0, 0.2) else "失败")
    print(f"\n最终 FDM(等先验) 得分 G_FDM = {G:.2f}")
