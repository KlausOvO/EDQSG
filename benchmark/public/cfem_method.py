# -*- coding: utf-8 -*-
"""适配CFEM（adapted CFEM）独立实现 —— 供审阅。

组合系数不再固定 0.5/0.5，改为按主客观权重“距离函数”确定：
  alpha = 0.5 + sqrt(Σ(w_subjective - w_objective)^2 / 8)
  beta  = 1 - alpha
  w = (alpha·w_subjective + beta·w_objective) / Σ(...)

运行：python cfem_method.py
"""

import math

import numpy as np

UTILITIES = np.array([100.0, 85.0, 70.0, 50.0, 20.0])


def entropy_weights(X):
    n, m = X.shape
    col_sum = X.sum(axis=0)
    p = np.where(col_sum > 0, X / col_sum, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        plog = np.where(p > 0, p * np.log(p), 0.0)
    k = 1.0 / math.log(n) if n > 1 else 0.0
    e = -k * plog.sum(axis=0)
    d = 1.0 - e
    d = np.where(d < 1e-10, 0.0, d)
    if d.sum() == 0:
        return np.full(m, 1.0 / m)
    return d / d.sum()


def cfem_combination_weights(w_subjective, w_objective):
    w_subjective = np.asarray(w_subjective, dtype=float)
    w_objective = np.asarray(w_objective, dtype=float)
    diff = w_subjective - w_objective
    alpha = 0.5 + np.sqrt(np.sum(diff ** 2) / 8.0)
    beta = 1.0 - alpha
    w = alpha * w_subjective + beta * w_objective
    w = w / np.sum(w)
    return {"weights": w, "alpha": float(alpha), "beta": float(beta),
            "w_subjective": w_subjective.tolist(), "w_objective": w_objective.tolist()}


def linear_membership(score100):
    mu = np.zeros(5)
    u = UTILITIES
    if score100 >= u[0]:
        mu[0] = 1.0
    elif score100 <= u[-1]:
        mu[-1] = 1.0
    else:
        for k in range(4):
            high, low = u[k], u[k + 1]
            if high >= score100 >= low:
                span = high - low
                mu[k] = (score100 - low) / span
                mu[k + 1] = (high - score100) / span
                break
    return mu


def cfem(X):
    n, m = X.shape
    w_subjective = np.full(m, 1.0 / m)
    w_objective = entropy_weights(X)
    comb = cfem_combination_weights(w_subjective, w_objective)
    w = comb["weights"]
    scores = []
    for j in range(n):
        B = np.zeros(5)
        for i in range(m):
            B += w[i] * linear_membership(100.0 * X[j, i])
        scores.append(float(np.dot(B, UTILITIES)))
    return scores, comb


if __name__ == "__main__":
    # 示例：hospital 污染序列（DQ1 恒定、DQ3 随污染下降）
    Xh = np.array([[1.0, 1.0], [1.0, 0.99], [1.0, 0.98], [1.0, 0.96],
                   [1.0, 0.94], [1.0, 0.92], [1.0, 0.88]])
    scores, comb = cfem(Xh)
    print("hospital 污染序列")
    print("  w_subjective =", comb["w_subjective"])
    print("  w_objective  =", comb["w_objective"])
    print(f"  alpha={comb['alpha']:.4f}  beta={comb['beta']:.4f}")
    print("  w_final      =", [round(float(w), 6) for w in comb["weights"]])
    print("  自检1 Σw =", round(float(comb["weights"].sum()), 10), "->",
          "通过" if abs(comb["weights"].sum() - 1.0) < 1e-10 else "失败")
    print("  自检2 CFEM 得分 ∈ [0,100]:", [round(s, 2) for s in scores])
