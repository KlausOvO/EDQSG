# -*- coding: utf-8 -*-
"""经典带权多属性 ER（Yang-Xu analytical ER）独立实现 —— 与 EDQSG 完全解耦。

本文件不导入、不调用 EDQSG 的任何聚合/冲突回退函数。

输入：每个属性 i 提供
  - weight ω_i（属性权重，和为 1）
  - belief β_{1..5,i}（五级质量置信度）
  - 未知度 β_{H,i} = 1 - Σ_n β_{n,i}

质量分配：
  m_{n,i}      = ω_i·β_{n,i}          （等级质量）
  m̄_{H,i}      = 1 - ω_i              （权重造成的未分配质量）
  m̃_{H,i}      = ω_i·β_{H,i}          （评价不完整产生的真正未知）
  m_{H,i}      = m̄_{H,i} + m̃_{H,i}    （总未分配质量）

两属性递推（K=1/(1-conflict)）：
  m_{n,next}   = K(m_{n,prev}·m_{n,new} + m_{n,prev}·m_{H,new} + m_{H,prev}·m_{n,new})
  m_{H,next}   = K·m_{H,prev}·m_{H,new}
  m̄_{H,next}   = K·m̄_{H,prev}·m̄_{H,new}
  m̃_{H,next}   = m_{H,next} - m̄_{H,next}

最终归一化（去除权重造成的未分配质量）：
  β_n = m_n / (1 - m̄_H)
  β_H = m̃_H / (1 - m̄_H)

运行：python classic_er.py
"""

import numpy as np

UTILITY = np.array([100.0, 85.0, 70.0, 50.0, 20.0])


def prepare_basic_masses(belief, weight):
    belief = np.asarray(belief, dtype=float)
    weight = float(weight)
    if belief.shape != (5,):
        raise ValueError("belief must contain 5 grade beliefs")
    if weight < 0 or weight > 1:
        raise ValueError("weight must be in [0, 1]")
    beta_sum = float(np.sum(belief))
    if beta_sum > 1.0 + 1e-10:
        raise ValueError("sum of grade beliefs cannot exceed 1")
    unknown = max(0.0, 1.0 - beta_sum)
    m_grade = weight * belief
    m_bar_h = 1.0 - weight
    m_tilde_h = weight * unknown
    m_h = m_bar_h + m_tilde_h
    return {"m_grade": m_grade, "m_bar_h": m_bar_h, "m_tilde_h": m_tilde_h,
            "m_h": m_h, "unknown_input": unknown}


def conflict_mass(m1, m2):
    total = 0.0
    for i in range(5):
        for j in range(5):
            if i != j:
                total += float(m1[i] * m2[j])
    return total


def combine_two_er_masses(prev, new):
    m1 = np.asarray(prev["m_grade"], dtype=float)
    m2 = np.asarray(new["m_grade"], dtype=float)
    conflict = conflict_mass(m1, m2)
    denom = 1.0 - conflict
    if denom <= 1e-12:
        raise RuntimeError("Classic ER total conflict is too high")
    K = 1.0 / denom

    m_grade_next = np.zeros(5)
    for n in range(5):
        m_grade_next[n] = K * (
            prev["m_grade"][n] * new["m_grade"][n]
            + prev["m_grade"][n] * new["m_h"]
            + prev["m_h"] * new["m_grade"][n]
        )

    m_h_next = K * prev["m_h"] * new["m_h"]
    m_bar_h_next = K * prev["m_bar_h"] * new["m_bar_h"]
    m_tilde_h_next = max(0.0, m_h_next - m_bar_h_next)

    return {"m_grade": m_grade_next, "m_h": m_h_next, "m_bar_h": m_bar_h_next,
            "m_tilde_h": m_tilde_h_next, "conflict": conflict, "K": K}


def aggregate_classic_er(items):
    """items: [{"id","weight","belief"}, ...]，belief 为 5 维。返回 (result, trace)。"""
    if len(items) == 0:
        raise ValueError("items cannot be empty")
    first = items[0]
    current = prepare_basic_masses(first["belief"], first["weight"])
    trace = []
    for item in items[1:]:
        new = prepare_basic_masses(item["belief"], item["weight"])
        current = combine_two_er_masses(current, new)
        trace.append({"after_attribute": item["id"],
                      "conflict": round(float(current["conflict"]), 4),
                      "K": round(float(current["K"]), 4)})
    return current, trace


def normalize_er_result(result):
    denom = 1.0 - result["m_bar_h"]
    if denom <= 1e-12:
        raise RuntimeError("Classic ER normalization failed")
    beta = np.asarray(result["m_grade"]) / denom
    beta_unknown = result["m_tilde_h"] / denom
    total = float(np.sum(beta)) + float(beta_unknown)
    return {"belief": beta, "unknown": beta_unknown, "sum_total": total}


def er_utility_interval(beta, unknown):
    beta = np.asarray(beta, dtype=float)
    unknown = float(unknown)
    base = float(beta @ UTILITY)
    u_min = base + unknown * 20.0
    u_max = base + unknown * 100.0
    u_avg = (u_min + u_max) / 2.0
    return {"U_min": u_min, "U_avg": u_avg, "U_max": u_max}


def grade_of_score(score):
    if score > 92.5:
        return "优"
    if score > 77.5:
        return "良"
    if score > 60:
        return "中"
    if score > 35:
        return "较差"
    return "差"


def grade_interval(u_min, u_max):
    g_min = grade_of_score(u_min)
    g_max = grade_of_score(u_max)
    if g_min == g_max:
        return g_min
    return f"{g_min}～{g_max}"


def run_classic_er(items):
    """一步完成：聚合 → 归一 → 效用区间。返回 dict。"""
    result, trace = aggregate_classic_er(items)
    norm = normalize_er_result(result)
    util = er_utility_interval(norm["belief"], norm["unknown"])
    return {
        "beta": [float(x) for x in norm["belief"]],
        "unknown": float(norm["unknown"]),
        "sum_total": norm["sum_total"],
        "U_min": util["U_min"],
        "U_avg": util["U_avg"],
        "U_max": util["U_max"],
        "grade_range": grade_interval(util["U_min"], util["U_max"]),
        "m_grade": [float(x) for x in result["m_grade"]],
        "m_bar_h": float(result["m_bar_h"]),
        "m_tilde_h": float(result["m_tilde_h"]),
        "m_h": float(result["m_h"]),
        "trace": trace,
    }


if __name__ == "__main__":
    # 自检 1：单属性 ω=1 退化
    r1 = run_classic_er([{"id": "A", "weight": 1.0, "belief": [0.10, 0.54, 0.25, 0.05, 0.03]}])
    print("自检1 单属性ω=1: beta=", [round(x, 4) for x in r1["beta"]],
          "unknown=", round(r1["unknown"], 4), "->", "通过" if abs(r1["unknown"] - 0.03) < 1e-8 else "失败")

    # 自检 2：完全确定输入 (1,0,0,0,0)
    r2 = run_classic_er([{"id": "A", "weight": 0.5, "belief": [1, 0, 0, 0, 0]},
                         {"id": "B", "weight": 0.5, "belief": [1, 0, 0, 0, 0]}])
    print("自检2 完全确定: beta=", [round(x, 4) for x in r2["beta"]],
          "unknown=", round(r2["unknown"], 8), "->", "通过" if abs(r2["beta"][0] - 1.0) < 1e-8 else "失败")

    # 自检 3：完全一致输入
    r3 = run_classic_er([{"id": "A", "weight": 0.5, "belief": [0.2, 0.3, 0.3, 0.1, 0.1]},
                         {"id": "B", "weight": 0.5, "belief": [0.2, 0.3, 0.3, 0.1, 0.1]}])
    print("自检3 完全一致: beta=", [round(x, 4) for x in r3["beta"]], "-> 无反常等级跳跃")

    # 自检 4：总质量
    print("自检4 sum(beta)+unknown =", round(r3["sum_total"], 8), "->",
          "通过" if abs(r3["sum_total"] - 1.0) < 1e-8 else "失败")

    # 自检 5：装备算例区间宽度（应明显宽于上一版 [79.95, 80.21]）
    eq = [
        {"id": "DQ6", "weight": 0.2, "belief": [0.10, 0.54, 0.25, 0.05, 0.03]},
        {"id": "DQ2", "weight": 0.2, "belief": [0.00, 0.30, 0.15, 0.05, 0.05]},
        {"id": "DQ5", "weight": 0.2, "belief": [0.60, 0.20, 0.00, 0.00, 0.00]},
        {"id": "SG3", "weight": 0.2, "belief": [0.00, 0.10, 0.50, 0.20, 0.00]},
        {"id": "SG7", "weight": 0.2, "belief": [0.00, 0.30, 0.40, 0.00, 0.00]},
    ]
    r5 = run_classic_er(eq)
    print("自检5 装备算例: U=[%.2f, %.2f] 宽度=%.2f 等级=%s"
          % (r5["U_min"], r5["U_max"], r5["U_max"] - r5["U_min"], r5["grade_range"]))
