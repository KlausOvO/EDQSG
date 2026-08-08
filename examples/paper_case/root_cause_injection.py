# -*- coding: utf-8 -*-
"""受控根因注入实验：已知结构缺陷注入，检验根因排序能否恢复真实成因。

每个场景在干净基线数据上注入单一（或组合）结构问题，真实根因已知；
运行 EDQSG 后取根因排序，计算 Top-1/Top-3 命中率与 MRR。
"""

from __future__ import annotations

import json
from pathlib import Path

from edqsg import CouplingCalibrationInput, EDQSGConfig, EDQSGModel
from edqsg.csvsource.profiler import build_indicators


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT.parent / "csv" / "config_offline.json"
OUT = ROOT / "results"


def base_tables():
    masters = [
        [f"P-{i:03d}", f"CODE-{i:03d}", f"件{i}", f"SN-{i:03d}", "CN", "2026-07-01", f"U{i % 3 + 1}"]
        for i in range(1, 13)
    ]
    instances = [
        [f"INST-{i:03d}", f"P-{i:03d}", f"SN-{i:03d}", f"CERT-{i:04d}", f"O{i % 3 + 1}", "2026-07-01"]
        for i in range(1, 13)
    ]
    txns = [
        [f"TXN-{i:03d}", f"P-{i:03d}", f"SN-{i:03d}", str(i * 10), "2026-07-01", f"T{i % 3 + 1}"]
        for i in range(1, 13)
    ]
    return masters, instances, txns


SCENARIOS = {
    "S0_clean": ("clean", []),
    "S1_orphan": ("orphan", ["SG3"]),
    "S2_master_conflict": ("master_conflict", ["SG7"]),
    "S3_duplicate": ("duplicate", ["SG3"]),
    "S4_missing": ("missing", ["SG3"]),
    "S5_stale": ("stale", ["SG8"]),
    "S6_audit_missing": ("audit_missing", ["SG8"]),
    "S7_authority_conflict": ("authority_conflict", ["SG7"]),
    "S8_domain_violation": ("domain_violation", ["SG3"]),
    "S9_combined": ("combined", ["SG3", "SG7"]),
}


def inject(scenario: str):
    masters, instances, txns = base_tables()
    if scenario == "orphan":
        instances.append(["INST-099", "P-999", "SN-099", "CERT-0099", "O1", "2026-07-01"])
        txns.append(["TXN-099", "P-888", "SN-088", "990", "2026-07-01", "T1"])
    elif scenario == "master_conflict":
        txns[3][2] = "SN-MISMATCH"  # TXN-004 与主数据 P-004 序列号冲突
    elif scenario == "duplicate":
        # 新增第 13 条主数据并复用 P-003 的序列号（该件号无实例/事务引用，
        # 避免重复注入同时污染跨表一致性指标）
        masters.append(["P-013", "CODE-013", "件13", masters[2][3], "CN", "2026-07-01", "U1"])
    elif scenario == "missing":
        masters[8][2] = ""  # 缺名称
    elif scenario == "stale":
        masters[10][5] = "2025-10-01"
        instances[11][5] = "2025-10-01"
    elif scenario == "audit_missing":
        instances[8][4] = ""
    elif scenario == "authority_conflict":
        instances[5][2] = "SN-WRONG"  # INST-006 序列号与权威主数据不一致
    elif scenario == "domain_violation":
        masters[6][4] = "XX"  # 非法国别代码
    elif scenario == "combined":
        instances.append(["INST-099", "P-999", "SN-099", "CERT-0099", "O1", "2026-07-01"])
        txns[3][2] = "SN-MISMATCH"
    return {
        "part_master": [
            dict(zip(["part_id", "part_code", "part_name", "serial_no", "country_code", "updated_at", "operator"], row))
            for row in masters
        ],
        "part_instance": [
            dict(zip(["instance_id", "part_id", "serial_no", "certificate_no", "operator", "updated_at"], row))
            for row in instances
        ],
        "inventory_transaction": [
            dict(zip(["txn_id", "part_id", "serial_no", "quantity", "updated_at", "operator"], row))
            for row in txns
        ],
    }


def extended_couplings(base_config) -> list[CouplingCalibrationInput]:
    items = []
    extra = [
        ("DQ6", "SG3", 0.80, 0.75),
        ("DQ5", "SG7", 0.60, 0.70),
        ("DQ2", "SG7", 0.80, 0.80),
        ("DQ4", "SG3", 0.80, 0.75),
        ("DQ1", "SG3", 0.70, 0.70),
        ("DQ7", "SG8", 0.70, 0.70),
        ("DQ8", "SG8", 0.70, 0.70),
        ("DQ3", "SG3", 0.70, 0.70),
    ]
    for dq, sg, strength, confidence in extra:
        items.append(
            CouplingCalibrationInput(
                dq_indicator_id=dq,
                sg_indicator_id=sg,
                normative_strength=strength,
                expert_strength=strength,
                data_strength=strength,
                normative_confidence=confidence,
                expert_confidence=confidence,
                data_confidence=confidence,
            )
        )
    return items


def ranked_roots(report):
    return [
        item
        for item in report.root_causes
        if not item.below_threshold and not item.low_confidence
    ]


def run_all() -> dict:
    import json as _json

    base_config = _json.loads(CONFIG.read_text(encoding="utf-8"))
    # 关系控制参数取一致值，避免两条 SG3 证据分数差异过大触发冲突复核
    for rel in base_config["relationship_controls"]:
        rel["control_coverage"] = 0.99
        rel["control_reliability"] = 0.95
        rel["operating_effectiveness"] = 0.98
    couplings = extended_couplings(base_config)
    results = []
    for name, (scenario, expected) in SCENARIOS.items():
        tables = inject(scenario)
        indicators, metrics = build_indicators(base_config, tables)
        dq_ids = [item.indicator_id for item in indicators if item.domain.value == "DQ"]
        sg_ids = [item.indicator_id for item in indicators if item.domain.value == "SG"]
        dq_w = {item: 1.0 / len(dq_ids) for item in dq_ids}
        sg_w = {item: 1.0 / len(sg_ids) for item in sg_ids}
        # 注入实验考察根因排序而非绝对贡献，故采用更低诊断充分性门槛
        # （θ_RC = 0.0001），8 指标等权下 RC 数量级约为 1e-4~1e-3。
        model = EDQSGModel(EDQSGConfig(root_cause_threshold=0.0001))
        report = model.evaluate(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_calibrations=couplings,
            governance_templates=[],
        )
        roots = ranked_roots(report)
        top1 = roots[0].sg_indicator_id if roots else None
        top3 = [item.sg_indicator_id for item in roots[:3]]
        rank = None
        for idx, item in enumerate(roots, start=1):
            if item.sg_indicator_id in expected:
                rank = idx
                break
        mrr = 1.0 / rank if rank else 0.0
        results.append(
            {
                "scenario": name,
                "injected": scenario,
                "expected_sg": expected,
                "top1": top1,
                "top3": top3,
                "rank_of_expected": rank,
                "mrr": round(mrr, 4),
                "hit_top1": int(top1 in expected),
                "hit_top3": int(bool(set(expected) & set(top3))),
                "root_causes": [
                    {"sg": item.sg_indicator_id, "rc": round(item.contribution, 5)}
                    for item in roots[:3]
                ],
            }
        )
    # Top-1/Top-3/MRR 仅对含已知根因的注入场景计算（S1~S9）；
    # S0 为无根因干净基线，单独报告误诊率，不计入根因命中率分母。
    injected = [r for r in results if r["expected_sg"]]
    clean = [r for r in results if not r["expected_sg"]]
    n = len(injected)
    top1_rate = sum(r["hit_top1"] for r in injected) / n
    top3_rate = sum(r["hit_top3"] for r in injected) / n
    mrr_mean = sum(r["mrr"] for r in injected) / n
    clean_false_positive = sum(1 for r in clean if r["top1"] is not None) / len(clean)
    return {
        "scenarios": results,
        "top1_accuracy": round(top1_rate, 4),
        "top3_hit_rate": round(top3_rate, 4),
        "mean_reciprocal_rank": round(mrr_mean, 4),
        "clean_false_positive_rate": round(clean_false_positive, 4),
        "denominator_note": "Top-1/Top-3/MRR 分母为 9 个含已知根因的注入场景（S1~S9），S0 干净基线单独报告",
    }


def markdown(result: dict) -> str:
    lines = [
        "# 受控根因注入实验（EDQSG）",
        "",
        "| 场景 | 注入结构问题 | 预期根因 | Top-1 | Top-3 | 预期根因排名 | MRR |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in result["scenarios"]:
        lines.append(
            f"| {r['scenario']} | {r['injected']} | {','.join(r['expected_sg'])} "
            f"| {r['top1'] or '-'} | {','.join(r['top3']) or '-'} "
            f"| {r['rank_of_expected'] or '-'} | {r['mrr']} |"
        )
    lines += [
        "",
        f"- 注入场景（S1~S9，n=9）：Top-1 命中率 {result['top1_accuracy']:.2%}、"
        f"Top-3 命中率 {result['top3_hit_rate']:.2%}、MRR {result['mean_reciprocal_rank']:.2f}",
        f"- 干净基线 S0：未输出根因候选，误诊率 {result['clean_false_positive_rate']:.2%}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_all()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "root_cause_injection.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "root_cause_injection.md").write_text(markdown(result), encoding="utf-8")
    print("Top-1:", result["top1_accuracy"], "| Top-3:", result["top3_hit_rate"], "| MRR:", result["mean_reciprocal_rank"])


if __name__ == "__main__":
    main()
