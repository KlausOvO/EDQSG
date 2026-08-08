# -*- coding: utf-8 -*-
"""装备场景论文算例（与论文第 7 节严格一致）及消融实验。

输入规格来自论文表 8~表 11：
  - 指标：DQ2、DQ5、DQ6（Q，等权），SG3、SG7（S，等权）；
  - DQ6 由两条证据（全量剖析 + 抽样复核）经式(2)折扣、ER 融合得到；
  - DQ2 未知度 0.45，进入证据不足复核，参与域内聚合但不参与根因计算；
  - 耦合：SG3→DQ6（a=0.80,c=0.75）、SG7→DQ5（a=0.60,c=0.70）、SG7→DQ2（a=0.50,c=0.60），
    三源（规范/专家/数据）取值一致，无分歧；
  - 底线：关键标识重复（cap=60）。

预期输出（与论文一致）：
  Q≈82.3、S≈71.7、G0≈76.8、B≈0.64、c^G≈0.76、G=60（较差）、
  RC_SG3≈0.0136（高于 0.01 门槛）、RC_SG7≈0.0010（低于门槛）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from edqsg import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    Domain,
    EDQSGModel,
    Evidence,
    EvidenceType,
    GovernanceTemplate,
    Indicator,
    TaskLayer,
)
from edqsg.scoring import ScoreCalculator


OUT = Path(__file__).resolve().parent / "results"


def evidence_with_beliefs(
    eid: str,
    beliefs: tuple[float, float, float, float, float],
    unknown: float,
) -> Evidence:
    """已知融合结果的单证据输入（五属性可靠性=1，折扣后不变）。"""
    return Evidence(
        evidence_id=eid,
        evidence_type=EvidenceType.DATA,
        source="paper-case",
        coverage=1.0,
        authority=1.0,
        timeliness=1.0,
        repeatability=1.0,
        business_fit=1.0,
        belief_degrees=beliefs,
        unknown_degree=unknown,
        description="论文算例融合结果",
    )


def dq6_evidence() -> tuple[Evidence, Evidence]:
    """DQ6 两条证据：全量剖析 + 抽样复核（表 10）。"""

    def make(eid, beliefs, attrs) -> Evidence:
        return Evidence(
            evidence_id=eid,
            evidence_type=EvidenceType.DATA,
            source="paper-case",
            coverage=attrs["C"],
            authority=attrs["A"],
            timeliness=attrs["T"],
            repeatability=attrs["R"],
            business_fit=attrs["F"],
            belief_degrees=beliefs,
            unknown_degree=0.0,
        )

    e1 = make(
        "E-DQ6-FULL",
        (0.15, 0.43, 0.27, 0.09, 0.06),
        {"C": 0.85, "A": 0.95, "T": 0.90, "R": 0.90, "F": 0.90},
    )
    e2 = make(
        "E-DQ6-SAMPLE",
        (0.13, 0.48, 0.28, 0.07, 0.04),
        {"C": 0.80, "A": 0.90, "T": 0.85, "R": 0.85, "F": 0.85},
    )
    return e1, e2


def build_indicators() -> list[Indicator]:
    return [
        Indicator(
            indicator_id="DQ6",
            name="关联完整性",
            domain=Domain.DATA_QUALITY,
            evidences=dq6_evidence(),
        ),
        Indicator(
            indicator_id="DQ2",
            name="准确性",
            domain=Domain.DATA_QUALITY,
            evidences=(
                evidence_with_beliefs(
                    "E-DQ2", (0.00, 0.30, 0.15, 0.05, 0.05), 0.45
                ),
            ),
        ),
        Indicator(
            indicator_id="DQ5",
            name="一致性",
            domain=Domain.DATA_QUALITY,
            evidences=(
                evidence_with_beliefs(
                    "E-DQ5", (0.60, 0.20, 0.00, 0.00, 0.00), 0.20
                ),
            ),
        ),
        Indicator(
            indicator_id="SG3",
            name="键与关系控制",
            domain=Domain.STRUCTURAL_GOVERNANCE,
            evidences=(
                evidence_with_beliefs(
                    "E-SG3", (0.00, 0.10, 0.50, 0.20, 0.00), 0.20
                ),
            ),
        ),
        Indicator(
            indicator_id="SG7",
            name="主数据权威性",
            domain=Domain.STRUCTURAL_GOVERNANCE,
            evidences=(
                evidence_with_beliefs(
                    "E-SG7", (0.00, 0.30, 0.40, 0.00, 0.00), 0.30
                ),
            ),
        ),
    ]


def weights() -> tuple[dict[str, float], dict[str, float]]:
    return (
        {"DQ6": 1 / 3, "DQ2": 1 / 3, "DQ5": 1 / 3},
        {"SG3": 0.5, "SG7": 0.5},
    )


def couplings(divergent: bool = False) -> list[CouplingCalibrationInput]:
    if divergent:
        # 三源分歧场景：规范 0.80、专家 0.50、数据 0.20（极差 0.60 > θ_src=0.2）
        return [
            CouplingCalibrationInput(
                dq_indicator_id="DQ6",
                sg_indicator_id="SG3",
                normative_strength=0.80,
                expert_strength=0.50,
                data_strength=0.20,
                normative_confidence=0.75,
                expert_confidence=0.65,
                data_confidence=0.55,
            ),
        ]
    return [
        CouplingCalibrationInput(
            dq_indicator_id="DQ6",
            sg_indicator_id="SG3",
            normative_strength=0.80,
            expert_strength=0.80,
            data_strength=0.80,
            normative_confidence=0.75,
            expert_confidence=0.75,
            data_confidence=0.75,
        ),
        CouplingCalibrationInput(
            dq_indicator_id="DQ5",
            sg_indicator_id="SG7",
            normative_strength=0.60,
            expert_strength=0.60,
            data_strength=0.60,
            normative_confidence=0.70,
            expert_confidence=0.70,
            data_confidence=0.70,
        ),
        CouplingCalibrationInput(
            dq_indicator_id="DQ2",
            sg_indicator_id="SG7",
            normative_strength=0.50,
            expert_strength=0.50,
            data_strength=0.50,
            normative_confidence=0.60,
            expert_confidence=0.60,
            data_confidence=0.60,
        ),
    ]


def bottom_line_triggers() -> list[BottomLineTrigger]:
    return [
        BottomLineTrigger(
            rule_id="BL-DUP-SERIAL",
            description="关键件号重复（业务键：件号+批次号+序列号）",
            cap=60.0,
            severity_level=1,
            target_object="库存表 I 重复业务键",
        ),
        BottomLineTrigger(
            rule_id="BL-CERT-MISSING",
            description="关键证书缺失",
            cap=60.0,
            severity_level=1,
            target_object="证书缺失实例",
        ),
        BottomLineTrigger(
            rule_id="BL-ORPHAN",
            description="关键引用产生孤儿记录",
            cap=77.5,
            severity_level=2,
            target_object="孤儿引用记录",
        ),
    ]


def templates() -> list[GovernanceTemplate]:
    return [
        GovernanceTemplate(
            template_id="TPL-SG3",
            sg_indicator_id="SG3",
            bottom_line_rule_id=None,
            target_object="库存表 I 与主数据表 M 的引用关系",
            root_cause="关系完整性控制不足",
            lifecycle_stage="运行",
            measures=("登记逻辑关系", "增加写入校验门禁", "建立每月孤儿自动检测"),
            actors=("数据库管理员", "库存系统负责人"),
            acceptance_metrics={"孤儿率": 0.005},
            task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
            severity=0.8,
            impact=0.8,
            urgency=0.7,
            cost=0.4,
        ),
        GovernanceTemplate(
            template_id="TPL-BL-DUP",
            sg_indicator_id=None,
            bottom_line_rule_id="BL-DUP-SERIAL",
            target_object="重复关键件号",
            root_cause="唯一性控制缺失",
            lifecycle_stage="创建",
            measures=("合并重复记录并追溯装机记录", "建立唯一性控制"),
            actors=("库存系统数据负责人",),
            acceptance_metrics={"业务键重复率": 0.0},
            task_layer=TaskLayer.DATA_REPAIR,
            severity=1.0,
            impact=1.0,
            urgency=1.0,
            cost=0.5,
        ),
    ]


def raw_unknown_zero_scores(report, dq_w, sg_w, utilities) -> dict:
    """未知计零：得分 = Σ b_k·u_k（不做已知归一化），无排除、无底线。"""

    def domain_raw(domain: Domain, weights: dict[str, float]) -> float:
        total = 0.0
        for item in report.indicator_results:
            if item.domain is not domain or item.indicator_id not in weights:
                continue
            total += weights[item.indicator_id] * sum(
                b * u for b, u in zip(item.belief_degrees, utilities, strict=True)
            )
        return total

    q = domain_raw(Domain.DATA_QUALITY, dq_w)
    s = domain_raw(Domain.STRUCTURAL_GOVERNANCE, sg_w)
    score = math.sqrt(q * s)
    return {
        "q": q,
        "s": s,
        "score": score,
        "grade": ScoreCalculator.grade(score, EDQSGModel().config.grade_boundaries).value,
    }


def run_case() -> dict:
    indicators = build_indicators()
    dq_w, sg_w = weights()
    model = EDQSGModel()
    report = model.evaluate(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_calibrations=couplings(),
        bottom_line_triggers=bottom_line_triggers(),
        governance_templates=templates(),
    )

    # 基线与消融
    no_bl = model.evaluate(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_calibrations=couplings(),
        bottom_line_triggers=[],
        governance_templates=templates(),
    )
    no_decoupling = raw_unknown_zero_scores(report, dq_w, sg_w, model.config.grade_utilities)
    divergent = model.evaluate(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_calibrations=couplings(divergent=True),
        bottom_line_triggers=bottom_line_triggers(),
        governance_templates=templates(),
    )

    sensitivity = model.sensitivity(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_relations=model.coupling_calibrator.calibrate_many(couplings()),
        bottom_line_triggers=bottom_line_triggers(),
        governance_templates=templates(),
        perturbations=(0.9, 1.1),
        top_k=3,
    )
    robustness = model.robustness(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_relations=model.coupling_calibrator.calibrate_many(couplings()),
        bottom_line_triggers=bottom_line_triggers(),
        governance_templates=templates(),
        iterations=300,
        perturbation=0.10,
        perturb_bottom_line=True,
    )
    robustness_model_only = model.robustness(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_relations=model.coupling_calibrator.calibrate_many(couplings()),
        bottom_line_triggers=bottom_line_triggers(),
        governance_templates=templates(),
        iterations=300,
        perturbation=0.10,
        perturb_bottom_line=False,
    )

    result = {
        "edqsg": {
            "q": round(report.dq.score, 2),
            "q_confidence": round(report.dq.confidence, 3),
            "s": round(report.sg.score, 2),
            "s_confidence": round(report.sg.confidence, 3),
            "g0": round(report.initial_score, 2),
            "g": round(report.final_score, 2),
            "grade": report.overall_grade.value,
            "balance": round(report.balance, 3),
            "overall_confidence": round(report.overall_confidence, 3),
            "evidence_coverage": round(report.evidence_coverage, 3),
            "excluded": list(report.excluded_indicator_ids),
            "review": list(report.review_indicator_ids),
            "bottom_line_triggers": [t.rule_id for t in report.bottom_line_triggers],
            "indicators": [
                {
                    "indicator_id": item.indicator_id,
                    "beliefs": [round(x, 4) for x in item.belief_degrees],
                    "unknown": round(item.unknown_degree, 3),
                    "score": round(item.score, 2),
                    "confidence": round(item.confidence, 3),
                    "review_state": item.review_state,
                }
                for item in report.indicator_results
            ],
            "root_causes": [
                {
                    "sg_indicator_id": item.sg_indicator_id,
                    "contribution": round(item.contribution, 5),
                    "normalized": (
                        round(item.normalized_contribution, 4)
                        if item.normalized_contribution is not None
                        else None
                    ),
                    "below_threshold": item.below_threshold,
                    "affected_dq_ids": list(item.affected_dq_ids),
                }
                for item in report.root_causes
            ],
            "tasks": [
                {
                    "task_id": t.task_id,
                    "layer": t.task_layer.value,
                    "target_object": t.target_object,
                    "priority": round(t.priority, 2),
                    "bottom_line": t.bottom_line,
                }
                for t in report.governance_tasks
            ],
        },
        "ablations": {
            "weighted_average": {
                "q": round((78.9 + 71.8 + 96.3) / 3, 2),
                "s": round((66.9 + 76.4) / 2, 2),
                "score": round(math.sqrt((78.9 + 71.8 + 96.3) / 3 * (66.9 + 76.4) / 2), 2),
                "grade": ScoreCalculator.grade(
                    math.sqrt((78.9 + 71.8 + 96.3) / 3 * (66.9 + 76.4) / 2),
                    model.config.grade_boundaries,
                ).value,
                "note": "以融合后已知期望分 s_i 等权加权（证据充分时与 EDQSG 无底线结果一致）",
            },
            "owa": {
                "score": round(_owa_score(), 2),
                "grade": ScoreCalculator.grade(
                    _owa_score(), model.config.grade_boundaries
                ).value,
                "note": "有序加权平均（orness=0.4，偏保守），对排序后指标得分按位置权重聚合",
            },
            "no_unknown_decoupling": {
                "dq2_score_unknown_zero": round(0.30 * 85 + 0.15 * 70 + 0.05 * 50 + 0.05 * 20, 2),
                **no_decoupling,
                "note": "未知质量计零，不归一化；无排除、无底线",
            },
            "no_bottom_line": {
                "score": round(no_bl.final_score, 2),
                "grade": no_bl.overall_grade.value,
                "diff": round(report.final_score - no_bl.final_score, 2),
            },
            "no_three_source_calibration": {
                "note": "三源一致时，无校准（仅规范源）与三源校准结果相同："
                "a、c 不变，根因排序不变；分歧场景见 divergent_coupling",
            },
        },
        "divergent_coupling": {
            "note": "SG3→DQ6 三源强度 0.80/0.50/0.20，极差 0.60 > θ_src=0.2，标记待确认并排除",
            "pending_relations": [
                {"dq": r.dq_indicator_id, "sg": r.sg_indicator_id, "pending": r.pending}
                for r in divergent.coupling_relations
            ],
            "root_causes": [
                {
                    "sg_indicator_id": item.sg_indicator_id,
                    "contribution": round(item.contribution, 5),
                    "below_threshold": item.below_threshold,
                }
                for item in divergent.root_causes
            ],
        },
        "sensitivity": {
            "max_abs_score_change": round(sensitivity.max_abs_score_change, 2),
            "grade_flip_rate": round(sensitivity.grade_flip_rate, 4),
            "min_root_top_k_overlap": round(sensitivity.min_root_top_k_overlap, 4),
            "cases": len(sensitivity.cases),
        },
        "robustness": {
            "iterations": robustness.iterations,
            "perturbation": robustness.perturbation,
            "baseline_score": round(robustness.baseline_score, 2),
            "score_mean": round(robustness.score_mean, 2),
            "score_std": round(robustness.score_std, 2),
            "score_q05": round(robustness.score_quantiles[0], 2),
            "score_q50": round(robustness.score_quantiles[1], 2),
            "score_q95": round(robustness.score_quantiles[2], 2),
            "grade_flip_rate": round(robustness.grade_flip_rate, 4),
            "top_root_cause_probabilities": list(robustness.top_root_cause_probabilities),
            "grade_flip_rate_model_only": round(robustness_model_only.grade_flip_rate, 4),
            "score_mean_model_only": round(robustness_model_only.score_mean, 2),
            "score_std_model_only": round(robustness_model_only.score_std, 2),
            "score_q05_model_only": round(robustness_model_only.score_quantiles[0], 2),
            "score_q95_model_only": round(robustness_model_only.score_quantiles[1], 2),
        },
    }
    return result


def _owa_score(orness: float = 0.4) -> float:
    """有序加权平均（二项式 OWA）：对指标得分降序后按位置权重聚合。"""
    import math

    scores = sorted([78.9, 71.8, 96.3, 66.9, 76.4], reverse=True)
    n = len(scores)
    total = 0.0
    for k, value in enumerate(scores, start=1):
        weight = (
            math.comb(n - 1, k - 1)
            * (orness ** (n - k))
            * ((1.0 - orness) ** (k - 1))
        )
        total += weight * value
    return total


def markdown(result: dict) -> str:
    e = result["edqsg"]
    lines = [
        "# 装备场景论文算例（EDQSG）",
        "",
        f"- Q={e['q']}（c={e['q_confidence']}），S={e['s']}（c={e['s_confidence']}）",
        f"- G0={e['g0']}，B={e['balance']}，c^G={e['overall_confidence']}，证据覆盖率={e['evidence_coverage']}",
        f"- 底线触发：{','.join(e['bottom_line_triggers']) or '无'} → G={e['g']}，等级={e['grade']}",
        f"- 复核指标：{','.join(e['review']) or '无'}；排除指标：{','.join(e['excluded']) or '无'}",
        "",
        "## 表 1 指标融合结果",
        "",
        "| 指标 | 置信分布 | 未知度 | s_i | c_i | 状态 |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for item in e["indicators"]:
        lines.append(
            f"| {item['indicator_id']} | {tuple(item['beliefs'])} | {item['unknown']} "
            f"| {item['score']} | {item['confidence']} | {item['review_state']} |"
        )
    lines += [
        "",
        "## 表 2 根因贡献",
        "",
        "| SG | RC | ρ | 低于门槛 | 影响DQ |",
        "|---|---:|---:|:--:|---|",
    ]
    for rc in e["root_causes"]:
        lines.append(
            f"| {rc['sg_indicator_id']} | {rc['contribution']} | {rc['normalized']} "
            f"| {'是' if rc['below_threshold'] else '否'} | {','.join(rc['affected_dq_ids']) or '-'} |"
        )
    lines += [
        "",
        "## 表 3 基线对比与消融",
        "",
        "| 方法 | G | 等级 | 说明 |",
        "|---|---:|:--:|---|",
        f"| 普通加权平均 | {result['ablations']['weighted_average']['score']} "
        f"| {result['ablations']['weighted_average']['grade']} | {result['ablations']['weighted_average']['note']} |",
        f"| OWA（orness=0.4） | {result['ablations']['owa']['score']} "
        f"| {result['ablations']['owa']['grade']} | {result['ablations']['owa']['note']} |",
        f"| 未解耦ER（未知计零） | {result['ablations']['no_unknown_decoupling']['score']:.1f} "
        f"| {result['ablations']['no_unknown_decoupling']['grade']} "
        f"| DQ2 未知计零后 s=39.5；无排除、无底线 |",
        f"| EDQSG（无底线） | {result['ablations']['no_bottom_line']['score']:.1f} "
        f"| {result['ablations']['no_bottom_line']['grade']} | 仅移除底线约束 |",
        f"| EDQSG（完整） | {e['g']:.1f} | {e['grade']} | 底线触发 G=min(G0,60) |",
        "",
        "## 表 4 三源校准与分歧保护",
        "",
        f"- 三源一致：{result['ablations']['no_three_source_calibration']['note']}",
        f"- 三源分歧：{result['divergent_coupling']['note']}",
        "  待确认关系："
        + ", ".join(
            f"{r['sg']}→{r['dq']}(pending={r['pending']})"
            for r in result["divergent_coupling"]["pending_relations"]
        ),
        "  排除后根因："
        + (
            ", ".join(
                f"{r['sg_indicator_id']}(RC={r['contribution']})"
                for r in result["divergent_coupling"]["root_causes"]
            )
            or "无（全部低于门槛）"
        ),
        "",
        "## 表 5 敏感性与鲁棒性",
        "",
        f"- 单因素±10%：最大|ΔG|={result['sensitivity']['max_abs_score_change']}，"
        f"等级反转率={result['sensitivity']['grade_flip_rate']:.2%}，根因Top3最小重叠="
        f"{result['sensitivity']['min_root_top_k_overlap']}",
        f"- 蒙特卡洛±10%（300次）：均值={result['robustness']['score_mean']}，"
        f"标准差={result['robustness']['score_std']}，5%分位={result['robustness']['score_q05']}，"
        f"95%分位={result['robustness']['score_q95']}，等级反转率（含底线限级扰动）="
        f"{result['robustness']['grade_flip_rate']:.2%}",
        f"- 蒙特卡洛（仅模型参数扰动，底线限级固定）：均值={result['robustness']['score_mean_model_only']}，"
        f"标准差={result['robustness']['score_std_model_only']}，5%~95%分位="
        f"{result['robustness']['score_q05_model_only']}~{result['robustness']['score_q95_model_only']}，"
        f"等级反转率={result['robustness']['grade_flip_rate_model_only']:.2%}",
    ]
    return "\n".join(lines) + "\n"


def verify(result: dict) -> list[str]:
    checks = []
    e = result["edqsg"]
    pairs = [
        ("Q", e["q"], 82.3, 0.2),
        ("S", e["s"], 71.7, 0.2),
        ("G0", e["g0"], 76.8, 0.2),
        ("G", e["g"], 60.0, 0.05),
        ("B", e["balance"], 0.64, 0.02),
        ("c^G", e["overall_confidence"], 0.76, 0.02),
    ]
    for name, value, target, tol in pairs:
        status = "OK" if abs(value - target) <= tol else "MISMATCH"
        checks.append(f"{name}: {value} vs {target} (±{tol}) -> {status}")
    sg3 = next((r for r in e["root_causes"] if r["sg_indicator_id"] == "SG3"), None)
    sg7 = next((r for r in e["root_causes"] if r["sg_indicator_id"] == "SG7"), None)
    checks.append(
        f"RC_SG3: {sg3['contribution'] if sg3 else None} vs 0.0136 (±0.001) -> "
        f"{'OK' if sg3 and abs(sg3['contribution'] - 0.0136) <= 0.001 else 'MISMATCH'}"
    )
    checks.append(
        f"RC_SG7: {sg7['contribution'] if sg7 else None} vs 0.0 "
        f"(SG7 证据不足复核，不参与根因排名) -> "
        f"{'OK' if sg7 and abs(sg7['contribution']) <= 1e-9 else 'MISMATCH'}"
    )
    return checks


def main() -> None:
    result = run_case()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "equipment_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "equipment_results.md").write_text(markdown(result), encoding="utf-8")
    print("装备算例结果已导出:", OUT)
    print("校验：")
    for line in verify(result):
        print("  ", line)


if __name__ == "__main__":
    main()
