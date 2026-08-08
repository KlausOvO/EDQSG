"""CSV 离线评价入口：读取 CSV 与 JSON 配置，调用 EDQSG 核心完成评价。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from edqsg import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    EDQSGModel,
    GovernanceTemplate,
    TaskLayer,
)

from .loader import load_config, load_table, resolve_paths
from .profiler import build_indicators


def _weights(indicator_ids: list[str], configured: dict) -> dict[str, float]:
    """域权重：优先用配置，缺失指标按等权补齐并归一化。"""

    ids = list(indicator_ids)
    weights = {item: float(configured.get(item, 1.0)) for item in ids}
    total = sum(weights.values())
    return {item: weight / total for item, weight in weights.items()}


def _evaluate_condition(metrics: dict[str, float], condition: dict) -> bool:
    metric = condition["metric"]
    value = float(condition.get("value", 0.0))
    operator = condition.get("operator", ">")
    actual = float(metrics.get(metric, 0.0))
    if operator == ">":
        return actual > value
    if operator == ">=":
        return actual >= value
    if operator == "<":
        return actual < value
    if operator == "<=":
        return actual <= value
    if operator == "==":
        return actual == value
    raise ValueError(f"不支持的比较运算符：{operator}")


def _build_triggers(config: dict, metrics: dict[str, float]) -> list[BottomLineTrigger]:
    triggers: list[BottomLineTrigger] = []
    for rule in config.get("bottom_line_rules", []):
        if _evaluate_condition(metrics, rule["condition"]):
            triggers.append(
                BottomLineTrigger(
                    rule_id=rule["rule_id"],
                    description=rule.get("description", rule["rule_id"]),
                    cap=float(rule.get("cap", 100.0)),
                    penalty=float(rule.get("penalty", 0.0)),
                    severity_level=int(rule.get("severity_level", 0)),
                    target_object=rule.get("target_object", ""),
                    evidence_ids=tuple(rule.get("evidence_ids", [])),
                )
            )
    return triggers


def _build_calibrations(config: dict) -> list[CouplingCalibrationInput]:
    items: list[CouplingCalibrationInput] = []
    for rel in config.get("coupling", []):
        items.append(
            CouplingCalibrationInput(
                dq_indicator_id=rel["dq"],
                sg_indicator_id=rel["sg"],
                normative_strength=float(rel.get("strength", 0.5)),
                normative_confidence=float(rel.get("confidence", 0.5)),
            )
        )
    return items


def _build_templates(config: dict) -> list[GovernanceTemplate]:
    layer_map = {
        "DATA_REPAIR": TaskLayer.DATA_REPAIR,
        "STRUCTURE_GOVERNANCE": TaskLayer.STRUCTURE_GOVERNANCE,
        "MECHANISM_GOVERNANCE": TaskLayer.MECHANISM_GOVERNANCE,
    }
    templates: list[GovernanceTemplate] = []
    for item in config.get("governance_templates", []):
        templates.append(
            GovernanceTemplate(
                template_id=item["template_id"],
                sg_indicator_id=item.get("sg_indicator_id"),
                bottom_line_rule_id=item.get("bottom_line_rule_id"),
                target_object=item["target_object"],
                root_cause=item["root_cause"],
                lifecycle_stage=item.get("lifecycle_stage", ""),
                measures=tuple(item.get("measures", [])),
                actors=tuple(item.get("actors", [])),
                acceptance_metrics=item.get("acceptance_metrics", {}),
                task_layer=layer_map[item["task_layer"]],
                severity=float(item.get("severity", 0.5)),
                impact=float(item.get("impact", 0.5)),
                urgency=float(item.get("urgency", 0.5)),
                cost=float(item.get("cost", 0.5)),
            )
        )
    return templates


def run_assessment(
    config_path: str | os.PathLike,
    output_dir: str | os.PathLike | None = None,
) -> dict:
    """执行一次完整离线 CSV 评价，返回报告字典并导出 JSON/Markdown。"""

    config_path = Path(config_path)
    base_dir = config_path.resolve().parent
    config = load_config(config_path)
    table_paths = resolve_paths(config, base_dir)
    tables = {
        name: load_table(path)
        for name, path in table_paths.items()
    }

    indicators, metrics = build_indicators(config, tables)
    dq_ids = [item.indicator_id for item in indicators if item.domain.value == "DQ"]
    sg_ids = [item.indicator_id for item in indicators if item.domain.value == "SG"]
    dq_weights = _weights(dq_ids, config.get("dq_weights", {}))
    sg_weights = _weights(sg_ids, config.get("sg_weights", {}))

    model = EDQSGModel()
    report = model.evaluate(
        indicators=indicators,
        dq_weights=dq_weights,
        sg_weights=sg_weights,
        coupling_calibrations=_build_calibrations(config),
        bottom_line_triggers=_build_triggers(config, metrics),
        governance_templates=_build_templates(config),
        metadata={
            "source": "csv-offline",
            "config": str(config_path),
            "metrics": metrics,
        },
    )

    data = report.to_dict()
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "assessment.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "assessment.md").write_text(_markdown(report, metrics), encoding="utf-8")
        print("报告已导出：", out)
    return data


def run_paper_results(
    config_path: str | os.PathLike,
    output_dir: str | os.PathLike,
) -> dict:
    """离线评价 + 论文结果导出：基线对比、敏感性、蒙特卡洛与论文表格。

    输出：
      paper_results.json   论文结果汇总（指标表、双域表、根因表、基线对比、敏感性）
      paper_results.md     可直接整理的论文表格
    """

    config_path = Path(config_path)
    base_dir = config_path.resolve().parent
    config = load_config(config_path)
    table_paths = resolve_paths(config, base_dir)
    tables = {name: load_table(path) for name, path in table_paths.items()}
    indicators, metrics = build_indicators(config, tables)
    dq_ids = [item.indicator_id for item in indicators if item.domain.value == "DQ"]
    sg_ids = [item.indicator_id for item in indicators if item.domain.value == "SG"]
    dq_weights = _weights(dq_ids, config.get("dq_weights", {}))
    sg_weights = _weights(sg_ids, config.get("sg_weights", {}))
    calibrations = _build_calibrations(config)
    triggers = _build_triggers(config, metrics)
    templates = _build_templates(config)

    model = EDQSGModel()
    calibrated_relations = model.coupling_calibrator.calibrate_many(calibrations)
    report = model.evaluate(
        indicators=indicators,
        dq_weights=dq_weights,
        sg_weights=sg_weights,
        coupling_calibrations=calibrations,
        bottom_line_triggers=triggers,
        governance_templates=templates,
    )

    # 基线：简单加权平均（无底线约束），用于对比“底线是否改变结论”。
    baseline_score = (report.dq.score + report.sg.score) / 2.0
    baseline_grade = model.config.grade_boundaries
    baseline_grade_value = _grade_name(baseline_score, baseline_grade)

    # 敏感性：±10% 参数扰动。
    sensitivity = model.sensitivity(
        indicators=indicators,
        dq_weights=dq_weights,
        sg_weights=sg_weights,
        coupling_relations=calibrated_relations,
        bottom_line_triggers=triggers,
        governance_templates=templates,
        perturbations=(0.9, 1.1),
        top_k=3,
    )

    summary = {
        "final_score": report.final_score,
        "initial_score": report.initial_score,
        "overall_grade": report.overall_grade.value,
        "dq": {"score": report.dq.score, "confidence": report.dq.confidence},
        "sg": {"score": report.sg.score, "confidence": report.sg.confidence},
        "balance": report.balance,
        "overall_confidence": report.overall_confidence,
        "baseline": {
            "score": baseline_score,
            "grade": baseline_grade_value,
            "grade_changed": baseline_grade_value != report.overall_grade.value,
        },
        "sensitivity": {
            "max_abs_score_change": sensitivity.max_abs_score_change,
            "grade_flip_rate": sensitivity.grade_flip_rate,
            "min_root_top_k_overlap": sensitivity.min_root_top_k_overlap,
        },
        "bottom_line_triggers": [
            {"rule_id": t.rule_id, "description": t.description, "cap": t.cap}
            for t in report.bottom_line_triggers
        ],
        "indicators": [
            {
                "indicator_id": item.indicator_id,
                "score": round(item.score, 2),
                "confidence": round(item.confidence, 3),
                "unknown": round(item.unknown_degree, 3),
                "conflict": round(item.conflict_degree, 3),
                "review": item.review_required,
            }
            for item in report.indicator_results
        ],
        "root_causes": [
            {
                "sg_indicator_id": item.sg_indicator_id,
                "contribution": round(item.contribution, 5),
                "rho": round(item.normalized_contribution, 4) if item.normalized_contribution is not None else None,
                "low_confidence": item.low_confidence,
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
            for t in report.governance_tasks[:10]
        ],
        "metrics": metrics,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "paper_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "paper_results.md").write_text(_paper_markdown(report, summary), encoding="utf-8")
    print("论文结果已导出：", out)
    return summary


def _grade_name(score: float, boundaries) -> str:
    from edqsg.scoring import ScoreCalculator
    return ScoreCalculator.grade(score, boundaries).value


def _paper_markdown(report, summary: dict) -> str:
    lines = [
        "# EDQSG 论文结果汇总",
        "",
        "## 表1 指标评价结果",
        "",
        "| 指标 | 分数 | 可信度 | 未知度 | 冲突度 | 复核 |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for item in summary["indicators"]:
        lines.append(
            f"| {item['indicator_id']} | {item['score']} | {item['confidence']} "
            f"| {item['unknown']} | {item['conflict']} | {'是' if item['review'] else ''} |"
        )
    lines += [
        "",
        "## 表2 双域与综合评价",
        "",
        f"- Q={summary['dq']['score']:.2f}（可信度 {summary['dq']['confidence']:.2f}），"
        f"S={summary['sg']['score']:.2f}（可信度 {summary['sg']['confidence']:.2f}）",
        f"- 初始 G0={summary['initial_score']:.2f} → 最终 G={summary['final_score']:.2f}，"
        f"等级={summary['overall_grade']}",
        f"- 双域协同度 B={summary['balance']:.3f}，综合可信度 c^G={summary['overall_confidence']:.3f}",
        "",
        "## 表3 底线触发",
        "",
    ]
    if summary["bottom_line_triggers"]:
        for t in summary["bottom_line_triggers"]:
            lines.append(f"- {t['rule_id']}：{t['description']}（cap={t['cap']}）")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 表4 根因排序",
        "",
        "| SG指标 | 贡献RC | 占比ρ | 低可信 | 影响DQ |",
        "|---|---:|---:|:--:|---|",
    ]
    for item in summary["root_causes"]:
        lines.append(
            f"| {item['sg_indicator_id']} | {item['contribution']} | "
            f"{item['rho'] if item['rho'] is not None else '-'} | "
            f"{'是' if item['low_confidence'] else ''} | {','.join(item['affected_dq_ids'])} |"
        )
    lines += [
        "",
        "## 表5 基线对比（EDQSG vs 简单加权平均）",
        "",
        f"- 加权平均基线：G={summary['baseline']['score']:.2f}，等级={summary['baseline']['grade']}",
        f"- EDQSG：G={summary['final_score']:.2f}，等级={summary['overall_grade']}",
        f"- 等级是否被底线改变：{'是' if summary['baseline']['grade_changed'] else '否'}",
        "",
        "## 表6 敏感性（±10% 参数扰动）",
        "",
        f"- 最大分数变化：{summary['sensitivity']['max_abs_score_change']:.2f}",
        f"- 等级反转率：{summary['sensitivity']['grade_flip_rate']:.2%}",
        f"- 根因前K最小重合度：{summary['sensitivity']['min_root_top_k_overlap']:.2f}",
        "",
        "## 表7 治理任务（前10）",
        "",
        "| 任务 | 层级 | 对象 | 优先级 | 底线 |",
        "|---|---|---|---:|:--:|",
    ]
    for t in summary["tasks"]:
        lines.append(
            f"| {t['task_id']} | {t['layer']} | {t['target_object']} | {t['priority']} "
            f"| {'是' if t['bottom_line'] else ''} |"
        )
    return "\n".join(lines) + "\n"


def _markdown(report, metrics: dict[str, float]) -> str:
    lines = [
        "# EDQSG CSV 离线评价报告",
        "",
        f"- 数据质量域 Q：{report.dq.score:.1f}（可信度 {report.dq.confidence:.2f}）",
        f"- 结构治理域 S：{report.sg.score:.1f}（可信度 {report.sg.confidence:.2f}）",
        f"- 综合得分：初始 {report.initial_score:.1f} → 最终 {report.final_score:.1f}",
        f"- 双域协同度：{report.balance:.3f}",
        f"- 总体等级：{report.overall_grade.value}",
        "",
        "## 底线触发",
        "",
    ]
    if report.bottom_line_triggers:
        for trigger in report.bottom_line_triggers:
            lines.append(f"- {trigger.rule_id}：{trigger.description}（cap={trigger.cap}）")
    else:
        lines.append("- 无")
    lines += ["", "## 根因排序（前3）", ""]
    ranked_roots = [
        item
        for item in report.root_causes
        if not item.below_threshold and not item.low_confidence
    ]
    for item in ranked_roots[:3]:
        lines.append(f"- {item.sg_indicator_id}：贡献 {item.contribution:.4f}")
    if not ranked_roots:
        lines.append("- 所有根因候选均低于诊断充分性门槛，未输出首要根因")
    lines += ["", "## 治理任务", ""]
    for task in report.governance_tasks[:5]:
        lines.append(
            f"- {task.task_id} [{task.task_layer.value}] {task.target_object}（优先级 {task.priority:.2f}）"
        )
    lines += ["", "## 关键原始指标", ""]
    for key in ("raw.dup_rate", "raw.orphan_rate", "raw.missing_rate.audit"):
        if key in metrics:
            lines.append(f"- {key} = {metrics[key]:.4f}")
    return "\n".join(lines) + "\n"
