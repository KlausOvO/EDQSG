# -*- coding: utf-8 -*-
"""对照实验：EDQSG vs 经典数据质量评价方法（审稿意见(8) 最终版 v4）。

本版（按《对比实验最后一轮修正说明_ClassicER最终修正版》）：
  - Classic ER 改为独立的带权多属性 ER（Yang-Xu analytical ER），属性权重 ω_i
    真正进入质量分配，并与 EDQSG 聚合代码完全解耦（见 classic_er.py）；
  - 重新生成全部 Classic ER 结果，新增 Classic_ER_unknown；
  - 修正 hospital 污染实验备注（无底线触发，不再误写“风险平台”）。

其余（CFEM 距离组合、FDM 等先验、PSO-GCA、EDQSG-Q/final 拆分）保持稳定。

运行：与 benchmark/public/benchmark.py、classic_er.py 同目录；PYTHONPATH 指向 src。
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from benchmark import (  # noqa: E402
    DATA,
    DATASETS,
    Domain,
    EDQSGModel,
    build_clean_table,
    build_couplings,
    build_indicators,
    build_triggers,
    calibrate_rule_observability,
    inject_defects,
    load_clean,
    load_table,
    weights,
)
from edqsg import (  # noqa: E402
    BottomLineTrigger,
    CouplingCalibrationInput,
    Evidence,
    EvidenceType,
    Indicator,
)
from classic_er import run_classic_er, grade_interval  # noqa: E402

OUT = _HERE / "results"
UTILITIES = np.array([100.0, 85.0, 70.0, 50.0, 20.0])
LEVELS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.60]
CRULE_SWEEP = [1.0, 0.9, 0.7, 0.5, 0.3, 0.1]


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def grade_of(score: float) -> str:
    if score > 92.5:
        return "优"
    if score > 77.5:
        return "良"
    if score > 60.0:
        return "中"
    if score > 35.0:
        return "较差"
    return "差"


def linear_membership(score100: float) -> np.ndarray:
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


def spearman(xs, ys):
    if len(xs) < 3:
        return None

    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            rk = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = rk
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx * vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def monotonic_violations(gs):
    return sum(1 for k in range(len(gs) - 1) if gs[k + 1] > gs[k])


def discrimination(gs):
    g = np.asarray(gs, dtype=float)
    return float(np.mean(np.abs(g - g.mean())))


def bottom_line_remark(trigger_rates):
    if not trigger_rates:
        return "无底线触发，最终分数随污染率持续变化"
    first_rate = min(trigger_rates)
    return f"{first_rate:.0%}及以上触发底线并形成风险平台"


# --------------------------------------------------------------------------- #
# WSM / CFEM（距离函数组合）
# --------------------------------------------------------------------------- #
def wsm(x_values):
    return 100.0 * float(np.mean(x_values))


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


# --------------------------------------------------------------------------- #
# PSO-GCA
# --------------------------------------------------------------------------- #
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


PSO_CONFIG = {"swarm": 50, "iterations": 200, "c1": 2.0, "c2": 2.0,
              "inertia": 0.7, "seed": 20260720, "rho_gray": 0.5}


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


# --------------------------------------------------------------------------- #
# FDM（岳明桥等：模糊决策图）
# --------------------------------------------------------------------------- #
def fdm_steady_matrix(E, tol=1e-12, max_iter=1000):
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


# --------------------------------------------------------------------------- #
# 经典 ER：调独立 classic_er.py（带权多属性 ER）
# --------------------------------------------------------------------------- #
def _classic_er_items(fused, ind_weights, domain=None):
    items = []
    for f in fused:
        if domain is not None and f.domain is not domain:
            continue
        if f.indicator_id not in ind_weights:
            continue
        items.append({
            "id": f.indicator_id,
            "weight": float(ind_weights[f.indicator_id]),
            "belief": [float(x) for x in f.belief_degrees],
        })
    return items


# --------------------------------------------------------------------------- #
# 公开数据集：单点对比
# --------------------------------------------------------------------------- #
def snapshot_row(name, dataset):
    rows = load_table(DATA / dataset["dirty"])
    clean = load_clean(DATA / dataset["clean"])
    monitor_cols = dataset["monitor_cols"]
    rule_obs = calibrate_rule_observability(rows, clean, dataset)
    indicators, metrics = build_indicators(
        name, rows, dataset["detectors"], monitor_cols, dataset["sg"], 0.95, rule_obs
    )
    dq_ids = [i.indicator_id for i in indicators if i.domain is Domain.DATA_QUALITY]
    sg_ids = [i.indicator_id for i in indicators if i.domain is Domain.STRUCTURAL_GOVERNANCE]
    dq_w = weights(dq_ids)
    sg_w = weights(sg_ids)
    model = EDQSGModel()
    triggers = build_triggers(dataset, metrics)
    couplings = build_couplings(dataset)

    x_values = [1.0 - metrics.get(f"dq.{i}.rate", 0.0) for i in dq_ids]
    g_wsm = wsm(x_values)

    fused = [model.evidence_engine.fuse(item) for item in indicators]
    er_items = _classic_er_items(fused, dq_w, Domain.DATA_QUALITY)
    er_res = run_classic_er(er_items) if er_items else None

    try:
        report = model.evaluate(
            indicators=indicators, dq_weights=dq_w, sg_weights=sg_w,
            coupling_calibrations=couplings, bottom_line_triggers=triggers,
            governance_templates=[],
        )
        edqsg_q = round(report.dq.score, 2)
        edqsg_final = round(report.final_score, 2)
        edqsg_grade = report.overall_grade.value
        coverage = round(report.evidence_coverage, 3)
        excluded = list(report.excluded_indicator_ids)
        bottom_line = ",".join(t.rule_id for t in report.bottom_line_triggers) or "-"
    except ValueError:
        edqsg_q = None
        edqsg_final = None
        edqsg_grade = "不出具等级"
        coverage = 0.0
        excluded = list(dq_ids)
        bottom_line = "-"

    return {
        "dataset": name,
        "WSM_DQ": round(g_wsm, 2),
        "Classic_ER_Umin": round(er_res["U_min"], 2) if er_res else None,
        "Classic_ER_Uavg": round(er_res["U_avg"], 2) if er_res else None,
        "Classic_ER_Umax": round(er_res["U_max"], 2) if er_res else None,
        "Classic_ER_unknown": round(er_res["unknown"], 4) if er_res else None,
        "Classic_ER_grade_range": er_res["grade_range"] if er_res else "-",
        "EDQSG_Q": edqsg_q,
        "EDQSG_final": edqsg_final,
        "EDQSG_grade": edqsg_grade,
        "coverage": coverage,
        "excluded": excluded,
        "bottom_line": bottom_line,
    }


# --------------------------------------------------------------------------- #
# 公开数据集：受控污染序列
# --------------------------------------------------------------------------- #
def contamination_rows(name, dataset):
    rows = load_table(DATA / dataset["dirty"])
    clean = load_clean(DATA / dataset["clean"])
    clean_rows = build_clean_table(rows, clean, dataset)
    monitor_cols = dataset["monitor_cols"]
    rule_obs = calibrate_rule_observability(rows, clean, dataset)

    per_level = []
    X_rows = []
    for level in LEVELS:
        injected = inject_defects(clean_rows, dataset, level, seed=20260808 + int(level * 1000))
        indicators, metrics = build_indicators(
            name, injected, dataset["detectors"], monitor_cols, dataset["sg"], 0.95, rule_obs
        )
        dq_ids = [i.indicator_id for i in indicators if i.domain is Domain.DATA_QUALITY]
        sg_ids = [i.indicator_id for i in indicators if i.domain is Domain.STRUCTURAL_GOVERNANCE]
        dq_w = weights(dq_ids)
        sg_w = weights(sg_ids)
        model = EDQSGModel()
        x_values = [1.0 - metrics.get(f"dq.{i}.rate", 0.0) for i in dq_ids]
        X_rows.append(x_values)

        fused = [model.evidence_engine.fuse(item) for item in indicators]
        er_items = _classic_er_items(fused, dq_w, Domain.DATA_QUALITY)
        er_res = run_classic_er(er_items) if er_items else None

        triggers = build_triggers(dataset, metrics)
        try:
            report = model.evaluate(
                indicators=indicators, dq_weights=dq_w, sg_weights=sg_w,
                coupling_calibrations=build_couplings(dataset),
                bottom_line_triggers=triggers, governance_templates=[],
            )
            edqsg_q = report.dq.score
            edqsg_final = report.final_score
            bl = bool(report.bottom_line_triggers)
        except ValueError:
            edqsg_q = None
            edqsg_final = None
            bl = False

        per_level.append({
            "level": level,
            "x": x_values,
            "WSM": wsm(x_values),
            "Classic_ER_Umin": er_res["U_min"] if er_res else None,
            "Classic_ER_Uavg": er_res["U_avg"] if er_res else None,
            "Classic_ER_Umax": er_res["U_max"] if er_res else None,
            "Classic_ER_unknown": er_res["unknown"] if er_res else None,
            "EDQSG_Q": edqsg_q,
            "EDQSG_final": edqsg_final,
            "bottom_line_triggered": bl,
        })

    X = np.array(X_rows)
    cfem_scores, cfem_comb = cfem(X)
    pso_w, pso_scores = pso_gca(X)
    for i, lv in enumerate(per_level):
        lv["CFEM"] = cfem_scores[i]
        lv["PSO_GCA"] = pso_scores[i]

    return {
        "dataset": name,
        "levels": per_level,
        "cfem_comb": {
            "w_subjective": cfem_comb["w_subjective"],
            "w_objective": cfem_comb["w_objective"],
            "alpha": cfem_comb["alpha"],
            "beta": cfem_comb["beta"],
            "w_final": [float(round(w, 6)) for w in cfem_comb["weights"]],
        },
        "pso": {"config": PSO_CONFIG, "w_optimized": [float(round(w, 6)) for w in pso_w]},
    }


# --------------------------------------------------------------------------- #
# 公开数据集：证据不足压力实验
# --------------------------------------------------------------------------- #
def evidence_pressure(name, dataset):
    rows = load_table(DATA / dataset["dirty"])
    clean = load_clean(DATA / dataset["clean"])
    monitor_cols = dataset["monitor_cols"]
    dq_ids = [d["rule"] for d in dataset["detectors"]]
    dq_ids = list(dict.fromkeys(dq_ids))

    out = []
    for crule in CRULE_SWEEP:
        rule_obs = {k: crule for k in dq_ids}
        indicators, metrics = build_indicators(
            name, rows, dataset["detectors"], monitor_cols, dataset["sg"], 0.95, rule_obs
        )
        dq_w = weights([i.indicator_id for i in indicators if i.domain is Domain.DATA_QUALITY])
        sg_w = weights([i.indicator_id for i in indicators if i.domain is Domain.STRUCTURAL_GOVERNANCE])
        model = EDQSGModel()
        x_values = [1.0 - metrics.get(f"dq.{i}.rate", 0.0) for i in dq_ids]

        fused = [model.evidence_engine.fuse(item) for item in indicators]
        er_items = _classic_er_items(fused, dq_w, Domain.DATA_QUALITY)
        er_res = run_classic_er(er_items) if er_items else None

        dq_fused = [f for f in fused if f.domain is Domain.DATA_QUALITY]
        cond_score = sum(dq_w[f.indicator_id] * f.score for f in dq_fused)
        cond_conf = sum(dq_w[f.indicator_id] * f.confidence for f in dq_fused)

        try:
            report = model.evaluate(
                indicators=indicators, dq_weights=dq_w, sg_weights=sg_w,
                coupling_calibrations=build_couplings(dataset),
                bottom_line_triggers=build_triggers(dataset, metrics),
                governance_templates=[],
            )
            grade_issued = True
        except ValueError:
            grade_issued = False

        out.append({
            "C_rule": crule,
            "WSM": round(wsm(x_values), 2),
            "Classic_ER_Umin": round(er_res["U_min"], 2) if er_res else None,
            "Classic_ER_Uavg": round(er_res["U_avg"], 2) if er_res else None,
            "Classic_ER_Umax": round(er_res["U_max"], 2) if er_res else None,
            "Classic_ER_unknown": round(er_res["unknown"], 4) if er_res else None,
            "Classic_ER_grade_range": er_res["grade_range"] if er_res else "-",
            "EDQSG_conditional_score": round(cond_score, 2),
            "EDQSG_confidence": round(cond_conf, 3),
            "EDQSG_grade_issued": "是" if grade_issued else "否",
        })
    return out


# --------------------------------------------------------------------------- #
# 装备算例：WSM / OWA / FDM / 经典ER / EDQSG
# --------------------------------------------------------------------------- #
def _evidence(eid, beliefs, unknown):
    return Evidence(
        evidence_id=eid, evidence_type=EvidenceType.DATA, source="paper-case",
        coverage=1.0, authority=1.0, timeliness=1.0, repeatability=1.0, business_fit=1.0,
        belief_degrees=beliefs, unknown_degree=unknown, description="论文表9融合结果",
    )


def equipment_case():
    indicators = ["DQ6", "DQ2", "DQ5", "SG3", "SG7"]
    s = {"DQ6": 78.9, "DQ2": 71.8, "DQ5": 96.3, "SG3": 66.9, "SG7": 76.4}
    beliefs = {
        "DQ6": ((0.10, 0.54, 0.25, 0.05, 0.03), 0.03),
        "DQ2": ((0.00, 0.30, 0.15, 0.05, 0.05), 0.45),
        "DQ5": ((0.60, 0.20, 0.00, 0.00, 0.00), 0.20),
        "SG3": ((0.00, 0.10, 0.50, 0.20, 0.00), 0.20),
        "SG7": ((0.00, 0.30, 0.40, 0.00, 0.00), 0.30),
    }
    objs = [
        Indicator(indicator_id="DQ6", name="关联完整性", domain=Domain.DATA_QUALITY,
                  evidences=(_evidence("E-DQ6", beliefs["DQ6"][0], beliefs["DQ6"][1]),)),
        Indicator(indicator_id="DQ2", name="准确性", domain=Domain.DATA_QUALITY,
                  evidences=(_evidence("E-DQ2", beliefs["DQ2"][0], beliefs["DQ2"][1]),)),
        Indicator(indicator_id="DQ5", name="一致性", domain=Domain.DATA_QUALITY,
                  evidences=(_evidence("E-DQ5", beliefs["DQ5"][0], beliefs["DQ5"][1]),)),
        Indicator(indicator_id="SG3", name="键与关系控制", domain=Domain.STRUCTURAL_GOVERNANCE,
                  evidences=(_evidence("E-SG3", beliefs["SG3"][0], beliefs["SG3"][1]),)),
        Indicator(indicator_id="SG7", name="主数据权威性", domain=Domain.STRUCTURAL_GOVERNANCE,
                  evidences=(_evidence("E-SG7", beliefs["SG7"][0], beliefs["SG7"][1]),)),
    ]
    dq_w = {"DQ6": 1 / 3, "DQ2": 1 / 3, "DQ5": 1 / 3}
    sg_w = {"SG3": 0.5, "SG7": 0.5}

    coupling_inputs = [
        CouplingCalibrationInput(dq_indicator_id="DQ6", sg_indicator_id="SG3",
                                 normative_strength=0.80, expert_strength=0.80, data_strength=0.80,
                                 normative_confidence=0.75, expert_confidence=0.75, data_confidence=0.75),
        CouplingCalibrationInput(dq_indicator_id="DQ5", sg_indicator_id="SG7",
                                 normative_strength=0.60, expert_strength=0.60, data_strength=0.60,
                                 normative_confidence=0.70, expert_confidence=0.70, data_confidence=0.70),
        CouplingCalibrationInput(dq_indicator_id="DQ2", sg_indicator_id="SG7",
                                 normative_strength=0.50, expert_strength=0.50, data_strength=0.50,
                                 normative_confidence=0.60, expert_confidence=0.60, data_confidence=0.60),
    ]
    bottom_lines = [
        BottomLineTrigger(rule_id="BL-DUP-SERIAL", description="关键件号重复", cap=60.0, severity_level=1),
        BottomLineTrigger(rule_id="BL-CERT-MISSING", description="关键证书缺失", cap=60.0, severity_level=1),
        BottomLineTrigger(rule_id="BL-ORPHAN", description="关键引用孤儿", cap=77.5, severity_level=2),
    ]

    model = EDQSGModel()
    relations = model.coupling_calibrator.calibrate_many(coupling_inputs)
    a_ij_display = {f"{r.sg_indicator_id}->{r.dq_indicator_id}": round(r.strength, 4) for r in relations}

    report = model.evaluate(
        indicators=objs, dq_weights=dq_w, sg_weights=sg_w,
        coupling_calibrations=coupling_inputs, bottom_line_triggers=bottom_lines,
        governance_templates=[],
    )
    no_bl = model.evaluate(
        indicators=objs, dq_weights=dq_w, sg_weights=sg_w,
        coupling_calibrations=coupling_inputs, bottom_line_triggers=[],
        governance_templates=[],
    )

    q = (s["DQ6"] + s["DQ2"] + s["DQ5"]) / 3
    sg = (s["SG3"] + s["SG7"]) / 2
    g_wsm = 0.5 * (q + sg)

    def _owa(vals, orness=0.4):
        sv = sorted(vals, reverse=True)
        n = len(sv)
        total = 0.0
        for k, v in enumerate(sv, start=1):
            w = math.comb(n - 1, k - 1) * (orness ** (n - k)) * ((1.0 - orness) ** (k - 1))
            total += w * v
        return total

    g_owa = _owa([s[k] for k in indicators])

    idx = {k: i for i, k in enumerate(indicators)}
    E = np.zeros((5, 5))
    for r in relations:
        E[idx[r.sg_indicator_id], idx[r.dq_indicator_id]] = r.strength
    omega, C_star = fdm_weights(E)
    g_fdm = float(omega @ np.array([s[k] for k in indicators]))
    omega0, _ = fdm_weights(np.zeros((5, 5)))
    fdm_checks = {
        "sum_omega": float(omega.sum()),
        "score_in_range": float(min(s.values())) <= g_fdm <= float(max(s.values())),
        "E0_score": float(omega0 @ np.array([s[k] for k in indicators])),
    }

    # 经典 ER：5 指标等权带权多属性 ER（独立 classic_er.py）
    er_items = [{"id": k, "weight": 0.2, "belief": list(beliefs[k][0])} for k in indicators]
    er_res = run_classic_er(er_items)

    return {
        "q": round(q, 2), "s": round(sg, 2),
        "wsm": round(g_wsm, 2),
        "owa": round(g_owa, 2),
        "fdm": round(g_fdm, 2),
        "fdm_weights": {k: round(float(omega[i]), 4) for i, k in enumerate(indicators)},
        "fdm_a_ij": a_ij_display,
        "fdm_E": [[round(float(E[i][j]), 4) for j in range(5)] for i in range(5)],
        "fdm_checks": {
            "sum_omega": round(fdm_checks["sum_omega"], 6),
            "score_in_range": fdm_checks["score_in_range"],
            "E0_score": round(fdm_checks["E0_score"], 2),
        },
        "er_input_beliefs": {k: list(beliefs[k][0]) for k in indicators},
        "er_beta": er_res["beta"],
        "er_unknown": round(er_res["unknown"], 4),
        "er_sum": round(er_res["sum_total"], 6),
        "er_m_grade": [round(x, 4) for x in er_res["m_grade"]],
        "er_m_bar_h": round(er_res["m_bar_h"], 4),
        "er_m_tilde_h": round(er_res["m_tilde_h"], 4),
        "er_m_h": round(er_res["m_h"], 4),
        "er_trace": er_res["trace"],
        "er": [round(er_res["U_min"], 2), round(er_res["U_avg"], 2), round(er_res["U_max"], 2)],
        "er_grade_range": er_res["grade_range"],
        "edqsg_q": round(report.dq.score, 2),
        "edqsg_s": round(report.sg.score, 2),
        "edqsg_no_bl": round(no_bl.final_score, 2),
        "edqsg_final": round(report.final_score, 2),
        "edqsg_grade": report.overall_grade.value,
    }


# --------------------------------------------------------------------------- #
# 导出
# --------------------------------------------------------------------------- #
def _write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def export(snapshots, contaminations, pressures, equip, log_lines):
    OUT.mkdir(parents=True, exist_ok=True)

    payload = {
        "public_single_point": snapshots,
        "contamination": {k: v for k, v in contaminations.items()},
        "observability_stress": pressures,
        "paper_case": equip,
        "PSO_config": PSO_CONFIG,
    }
    (OUT / "对比实验_完整结果.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    _write_csv(OUT / "public_single_point_comparison.csv", [
        "dataset", "WSM_DQ", "Classic_ER_Umin", "Classic_ER_Uavg", "Classic_ER_Umax",
        "Classic_ER_unknown", "Classic_ER_grade_range", "EDQSG_Q", "EDQSG_final",
        "coverage", "excluded", "bottom_line",
    ], snapshots)

    cont_rows = []
    for name, c in contaminations.items():
        for lv in c["levels"]:
            cont_rows.append({
                "dataset": name, "pollution_rate": lv["level"], "WSM": lv["WSM"],
                "CFEM": round(lv["CFEM"], 2), "PSO_GCA": round(lv["PSO_GCA"], 2),
                "Classic_ER_Umin": round(lv["Classic_ER_Umin"], 2) if lv["Classic_ER_Umin"] is not None else "",
                "Classic_ER_Uavg": round(lv["Classic_ER_Uavg"], 2) if lv["Classic_ER_Uavg"] is not None else "",
                "Classic_ER_Umax": round(lv["Classic_ER_Umax"], 2) if lv["Classic_ER_Umax"] is not None else "",
                "Classic_ER_unknown": round(lv["Classic_ER_unknown"], 4) if lv["Classic_ER_unknown"] is not None else "",
                "EDQSG_Q": round(lv["EDQSG_Q"], 2) if lv["EDQSG_Q"] is not None else "",
                "EDQSG_final": round(lv["EDQSG_final"], 2) if lv["EDQSG_final"] is not None else "",
                "bottom_line_triggered": "是" if lv["bottom_line_triggered"] else "否",
            })
    _write_csv(OUT / "contamination_comparison.csv", [
        "dataset", "pollution_rate", "WSM", "CFEM", "PSO_GCA",
        "Classic_ER_Umin", "Classic_ER_Uavg", "Classic_ER_Umax", "Classic_ER_unknown",
        "EDQSG_Q", "EDQSG_final", "bottom_line_triggered",
    ], cont_rows)

    metrics_rows = []
    for name, c in contaminations.items():
        lv = c["levels"]
        methods = {
            "WSM": [x["WSM"] for x in lv],
            "CFEM": [x["CFEM"] for x in lv],
            "PSO_GCA": [x["PSO_GCA"] for x in lv],
            "Classic_ER_Uavg": [x["Classic_ER_Uavg"] for x in lv],
            "EDQSG_Q": [x["EDQSG_Q"] for x in lv],
        }
        remark = {
            "PSO_GCA": "D_G 与其权重优化目标（扩大区分度）直接相关，不作跨方法优劣判据",
            "EDQSG_Q": "仅 Q 域（不经过 S 域与底线）",
            "Classic_ER_Uavg": "以 ER 效用区间中点作为连续点估计",
        }
        for mname, gs in methods.items():
            gv = [g for g in gs if g is not None]
            if len(gv) < 3:
                continue
            rho = spearman([x["level"] for x in lv], gv)
            metrics_rows.append({
                "dataset": name, "method": mname,
                "rho": round(rho, 3) if rho is not None else "",
                "N_vio": monotonic_violations(gv),
                "delta_0_60": round(gv[-1] - gv[0], 1),
                "D_G": round(discrimination(gv), 1),
                "remark": remark.get(mname, ""),
            })
        g_final = [x["EDQSG_final"] for x in lv]
        gv = [g for g in g_final if g is not None]
        if len(gv) >= 3:
            rho = spearman([x["level"] for x in lv], gv)
            bl_levels = [x["level"] for x in lv if x["bottom_line_triggered"]]
            metrics_rows.append({
                "dataset": name, "method": "EDQSG_final",
                "rho": round(rho, 3) if rho is not None else "",
                "N_vio": monotonic_violations(gv),
                "delta_0_60": round(gv[-1] - gv[0], 1),
                "D_G": round(discrimination(gv), 1),
                "remark": bottom_line_remark(bl_levels),
            })
    _write_csv(OUT / "contamination_metrics.csv", [
        "dataset", "method", "rho", "N_vio", "delta_0_60", "D_G", "remark",
    ], metrics_rows)

    _write_csv(OUT / "observability_stress.csv", [
        "C_rule", "WSM", "Classic_ER_Umin", "Classic_ER_Uavg", "Classic_ER_Umax",
        "Classic_ER_unknown", "Classic_ER_grade_range",
        "EDQSG_conditional_score", "EDQSG_confidence", "EDQSG_grade_issued",
    ], pressures.get("adult", []))

    paper_rows = [
        {"method": "WSM", "score_or_interval": f"{equip['wsm']}", "grade_or_grade_range": grade_of(equip['wsm']),
         "handles_uncertainty": "否", "non_compensatory": "否", "root_cause_output": "否", "remark": "两域等权算术平均"},
        {"method": "OWA", "score_or_interval": f"{equip['owa']}", "grade_or_grade_range": grade_of(equip['owa']),
         "handles_uncertainty": "否", "non_compensatory": "部分", "root_cause_output": "否", "remark": "orness=0.4 偏保守位置加权"},
        {"method": "FDM_equal_prior", "score_or_interval": f"{equip['fdm']}", "grade_or_grade_range": grade_of(equip['fdm']),
         "handles_uncertainty": "否", "non_compensatory": "否", "root_cause_output": "仅影响权重",
         "remark": f"等先验 FDM，a_ij={equip['fdm_a_ij']}"},
        {"method": "Classic_ER", "score_or_interval": f"[{equip['er'][0]:.2f}, {equip['er'][2]:.2f}]",
         "grade_or_grade_range": equip['er_grade_range'],
         "handles_uncertainty": "带权多属性ER+效用区间表达无知", "non_compensatory": "否", "root_cause_output": "否",
         "remark": f"等权ω=0.2，未知={equip['er_unknown']}"},
        {"method": "EDQSG_no_bottom_line", "score_or_interval": f"{equip['edqsg_no_bl']}",
         "grade_or_grade_range": grade_of(equip['edqsg_no_bl']),
         "handles_uncertainty": "是", "non_compensatory": "否", "root_cause_output": "是", "remark": "移除底线约束"},
        {"method": "EDQSG_full", "score_or_interval": f"{equip['edqsg_final']}",
         "grade_or_grade_range": equip['edqsg_grade'],
         "handles_uncertainty": "是", "non_compensatory": "是", "root_cause_output": "是", "remark": "完整模型，底线限级"},
    ]
    _write_csv(OUT / "paper_case_comparison.csv", [
        "method", "score_or_interval", "grade_or_grade_range", "handles_uncertainty",
        "non_compensatory", "root_cause_output", "remark",
    ], paper_rows)

    L: list[str] = []
    L.append("# EDQSG vs 经典数据质量评价方法（对照实验 v4）")
    L.append("")
    L.append("## 表 X　公开基准单点对比")
    L.append("")
    L.append("| 数据集 | WSM | 经典ER区间 | ER未知 | ER等级 | EDQSG-Q | EDQSG-final | 覆盖率 | 排除 | 底线 |")
    L.append("|---|---:|---:|---:|---|---:|---:|---|---|---|")
    for r in snapshots:
        L.append(
            f"| {r['dataset']} | {r['WSM_DQ']} | [{r['Classic_ER_Umin']}, {r['Classic_ER_Umax']}] "
            f"| {r['Classic_ER_unknown']} | {r['Classic_ER_grade_range']} "
            f"| {r['EDQSG_Q'] if r['EDQSG_Q'] is not None else '-'} "
            f"| {r['EDQSG_final'] if r['EDQSG_final'] is not None else '不出具等级'} "
            f"| {r['coverage']:.2f} | {','.join(r['excluded']) or '-'} | {r['bottom_line']} |"
        )
    L.append("")
    L.append("## 表 Y　受控污染序列（0%→60%）")
    L.append("")
    L.append("| 数据集 | 污染率 | WSM | CFEM | PSO-GCA | ER区间 | EDQSG-Q | EDQSG-final | 底线 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for name, c in contaminations.items():
        for lv in c["levels"]:
            L.append(
                f"| {name} | {lv['level']:.0%} | {lv['WSM']:.1f} | {lv['CFEM']:.1f} | {lv['PSO_GCA']:.1f} "
                f"| [{lv['Classic_ER_Umin']:.1f},{lv['Classic_ER_Umax']:.1f}] "
                f"| {lv['EDQSG_Q']:.1f} | {lv['EDQSG_final']:.1f} "
                f"| {'是' if lv['bottom_line_triggered'] else '否'} |"
            )
    L.append("")
    L.append("## 证据不足压力实验（adult）")
    L.append("")
    L.append("| C_rule | WSM | 经典ER区间 | ER未知 | ER平均 | EDQSG条件质量 | 可信度 | 正式出等级 |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---|")
    for p in pressures.get("adult", []):
        star = "" if p["EDQSG_grade_issued"] == "是" else "*"
        L.append(
            f"| {p['C_rule']} | {p['WSM']} | [{p['Classic_ER_Umin']},{p['Classic_ER_Umax']}] "
            f"| {p['Classic_ER_unknown']} | {p['Classic_ER_Uavg']} "
            f"| {p['EDQSG_conditional_score']}{star} | {p['EDQSG_confidence']} | {p['EDQSG_grade_issued']} |"
        )
    L.append("")
    L.append("> *：仅表示已知证据条件下的条件质量水平，不作为正式总体质量评价结果。")
    L.append("")
    L.append("## 装备算例　经典方法比较与消融")
    L.append("")
    L.append("| 方法 | 得分/区间 | 等级 | 证据不足 | 非补偿 | 根因 |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| WSM | {equip['wsm']} | {grade_of(equip['wsm'])} | 否 | 否 | 否 |")
    L.append(f"| OWA | {equip['owa']} | {grade_of(equip['owa'])} | 否 | 部分 | 否 |")
    L.append(f"| FDM(等先验) | {equip['fdm']} | {grade_of(equip['fdm'])} | 否 | 否 | 仅权重 |")
    L.append(f"| 经典ER | [{equip['er'][0]:.2f},{equip['er'][2]:.2f}] | {equip['er_grade_range']} | 区间表达无知 | 否 | 否 |")
    L.append(f"| EDQSG(无底线) | {equip['edqsg_no_bl']} | {grade_of(equip['edqsg_no_bl'])} | 是 | 否 | 是 |")
    L.append(f"| EDQSG(完整) | {equip['edqsg_final']} | {equip['edqsg_grade']} | 是 | 是 | 是 |")
    L.append("")
    L.append(f"> FDM a_ij（式(10)校准）：{equip['fdm_a_ij']}")
    L.append(f"> FDM E 矩阵：{equip['fdm_E']}")
    L.append(f"> FDM 权重：{equip['fdm_weights']}；G_FDM={equip['fdm']}；自检 Σω={equip['fdm_checks']['sum_omega']}、E=0→{equip['fdm_checks']['E0_score']}")
    L.append(f"> 经典ER 总体置信分布 β={equip['er_beta']}，未知={equip['er_unknown']}，sum={equip['er_sum']}")
    L.append("")
    (OUT / "对比实验_完整结果.md").write_text("\n".join(L), encoding="utf-8")

    log: list[str] = []
    log.append("[CFEM] 距离函数组合权重")
    for name, c in contaminations.items():
        comb = c["cfem_comb"]
        log.append(f"  {name}: alpha={round(comb['alpha'],4)} beta={round(comb['beta'],4)} "
                   f"w_subjective={comb['w_subjective']} w_objective={comb['w_objective']} w_final={comb['w_final']}")
    log.append("")
    log.append("[PSO-GCA] 参数与优化权重")
    log.append(f"  config={PSO_CONFIG}")
    for name, c in contaminations.items():
        log.append(f"  {name}: w_optimized={c['pso']['w_optimized']}")
    log.append("")
    log.append("[FDM]")
    log.append(f"  a_ij={equip['fdm_a_ij']}")
    log.append(f"  E={equip['fdm_E']}")
    log.append(f"  weights={equip['fdm_weights']} sum={equip['fdm_checks']['sum_omega']}")
    log.append(f"  G_FDM={equip['fdm']} E=0 self-test={equip['fdm_checks']['E0_score']}")
    log.append("")
    log.append("[Classic ER] 带权多属性 ER（独立 classic_er.py）")
    log.append("  装备算例 attribute weights: DQ6=DQ2=DQ5=SG3=SG7=0.2")
    log.append(f"  input beliefs: {equip['er_input_beliefs']}")
    log.append(f"  聚合后 beta={equip['er_beta']}")
    log.append(f"  unknown={equip['er_unknown']} sum(beta)+unknown={equip['er_sum']}")
    log.append(f"  U_min/U_avg/U_max={equip['er']}")
    log.append(f"  等级范围={equip['er_grade_range']}")
    log.append(f"  final m_grade={equip['er_m_grade']} m_bar_h={equip['er_m_bar_h']} m_tilde_h={equip['er_m_tilde_h']} m_h={equip['er_m_h']}")
    log.append(f"  aggregation trace={equip['er_trace']}")
    log.append("")
    log.append("[EDQSG] 装备算例")
    log.append(f"  Q={equip['edqsg_q']} S={equip['edqsg_s']} no_bottom_line={equip['edqsg_no_bl']} "
               f"final={equip['edqsg_final']} grade={equip['edqsg_grade']}")
    log.append("")
    (OUT / "run_log.txt").write_text("\n".join(log), encoding="utf-8")
    log_lines.extend(log)


def main() -> None:
    snapshots = [snapshot_row(name, ds) for name, ds in DATASETS.items()]
    contaminations = {name: contamination_rows(name, DATASETS[name]) for name in ("hospital", "flight")}
    pressures = {"adult": evidence_pressure("adult", DATASETS["adult"])}
    equip = equipment_case()

    log_lines: list[str] = []
    export(snapshots, contaminations, pressures, equip, log_lines)
    print("完成。输出目录:", OUT)


if __name__ == "__main__":
    main()
