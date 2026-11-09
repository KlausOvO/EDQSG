# -*- coding: utf-8 -*-
"""补充实验：候选排序基线对照 + 关系映射随机删减。

目的：为论文 §6.3 末段的"简化排序对照"与 §7.3(2) 的"关系删减分析"提供可复现实现。

实验 1（基线对照）
  在同一组 9 个受控注入场景（S1~S9）上，比较四种排序策略的 Top-1/Top-3 命中率与 MRR：
    A. severity_only  仅按结构缺陷严重度排序（不使用 Q-S 关系）
    B. strength_only  仅按关系强度排序
    C. simplified     "关系强度 × 已确认质量缺陷程度"简化排序
    D. edqsg_full     完整 EDQSG（含候选准入、冲突复核、RC 贡献度）

实验 2（关系映射删减）
  对 Q-S 关系映射随机删除 25% / 50%，重复 N 次（默认 30），
  比较完整方法（D）与简化排序（C）的 Top-1 命中率。

用法（在仓库根目录下）：
    PYTHONPATH=src python examples/paper_case/paper_baselines.py --reference-date 2026-09-21
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

from edqsg import EDQSGConfig, EDQSGModel
from edqsg.csvsource.profiler import build_indicators

import root_cause_injection as rci

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"


def _config():
    cfg = json.loads(rci.CONFIG.read_text(encoding="utf-8"))
    # 与 root_cause_injection.run_all 保持一致
    for rel in cfg["relationship_controls"]:
        rel["control_coverage"] = 0.99
        rel["control_reliability"] = 0.95
        rel["operating_effectiveness"] = 0.98
    return cfg


def evaluate_scenario(scenario: str, couplings, reference_date):
    """跑单个场景，返回完整报告。"""
    cfg = _config()
    tables = rci.inject(scenario)
    indicators, _metrics = build_indicators(cfg, tables, reference_date=reference_date)
    dq_ids = [i.indicator_id for i in indicators if i.domain.value == "DQ"]
    sg_ids = [i.indicator_id for i in indicators if i.domain.value == "SG"]
    dq_w = {k: 1.0 / len(dq_ids) for k in dq_ids}
    sg_w = {k: 1.0 / len(sg_ids) for k in sg_ids}
    model = EDQSGModel(EDQSGConfig(root_cause_threshold=0.0001))
    return model.evaluate(
        indicators=indicators,
        dq_weights=dq_w,
        sg_weights=sg_w,
        coupling_calibrations=couplings,
        governance_templates=[],
    )


def policy_scores(report):
    """为每个候选构造三种基线的排序分。"""
    sg_score = {i.indicator_id: i.score for i in report.indicator_results
                if i.domain.value == "SG"}
    dq_score = {i.indicator_id: i.score for i in report.indicator_results
                if i.domain.value == "DQ"}
    dq_conf = {i.indicator_id: i.confidence for i in report.indicator_results
               if i.domain.value == "DQ"}

    severity = {sg: max(0.0, (100.0 - sc) / 100.0) for sg, sc in sg_score.items()}
    # 候选集 = 全部结构指标（与“仅严重度”基线一致，避免因有无关系而人为缩小候选池）
    strength = {sg: 0.0 for sg in sg_score}
    simplified = {sg: 0.0 for sg in sg_score}
    for rel in report.coupling_relations:
        sg, dq = rel.sg_indicator_id, rel.dq_indicator_id
        # 已确认质量缺陷程度 = DQ 缺陷度 × 该指标可信度
        defect = max(0.0, (100.0 - dq_score.get(dq, 100.0)) / 100.0) * dq_conf.get(dq, 0.0)
        strength[sg] = max(strength.get(sg, 0.0), rel.strength)
        simplified[sg] = max(simplified.get(sg, 0.0), rel.strength * defect)
    return severity, strength, simplified


def rank_by(score_map):
    return [k for k, _ in sorted(score_map.items(), key=lambda kv: (-kv[1], kv[0]))]


def hit_metrics(order, expected):
    """给定排序，返回 (hit_top1, hit_top3, rank, rr)。"""
    if not expected:
        return None
    rank = next((i for i, sg in enumerate(order, start=1) if sg in expected), None)
    return {
        "hit_top1": int(bool(order) and order[0] in expected),
        "hit_top3": int(any(sg in expected for sg in order[:3])),
        "rank_of_expected": rank,
        "rr": round(1.0 / rank, 4) if rank else 0.0,
    }


def baseline_experiment(reference_date):
    couplings = rci.extended_couplings(_config())
    rows = []
    for name, (scenario, expected) in rci.SCENARIOS.items():
        report = evaluate_scenario(scenario, couplings, reference_date)
        sev, strength, simplified = policy_scores(report)
        full_order = [x.sg_indicator_id for x in rci.ranked_roots(report)]
        orders = {
            "severity_only": rank_by(sev),
            "strength_only": rank_by(strength),
            "simplified": rank_by(simplified),
            "edqsg_full": full_order,
        }
        row = {"scenario": name, "injected": scenario, "expected": expected,
               "policies": {}}
        for pol, order in orders.items():
            m = hit_metrics(order, expected)
            if m is None:  # S0 干净基线无预期根因
                m = {"hit_top1": None, "hit_top3": None, "rank_of_expected": None, "rr": None}
            row["policies"][pol] = {"top3": order[:3], **m}
        rows.append(row)
    return rows


def deletion_experiment(reference_date, n_repeat: int, ratios):
    couplings = rci.extended_couplings(_config())
    n_rel = len(couplings)
    injected = [(n, s, e) for n, (s, e) in rci.SCENARIOS.items() if e]
    out = {}
    for ratio in ratios:
        k = max(1, int(round(n_rel * ratio)))
        res = {"ratio": ratio, "deleted": k, "total_relations": n_rel, "repeats": n_repeat,
               "edqsg_full": [], "simplified": []}
        for seed in range(1, n_repeat + 1):
            rng = random.Random(seed)
            drop = set(rng.sample(range(n_rel), k))
            kept = [c for i, c in enumerate(couplings) if i not in drop]
            full_hits, simp_hits = [], []
            for name, scenario, expected in injected:
                report = evaluate_scenario(scenario, kept, reference_date)
                full_order = [x.sg_indicator_id for x in rci.ranked_roots(report)]
                full_hits.append(hit_metrics(full_order, expected)["hit_top1"])
                _sev, _st, simplified = policy_scores(report)
                simp_order = rank_by(simplified)
                simp_hits.append(hit_metrics(simp_order, expected)["hit_top1"])
            res["edqsg_full"].append(sum(full_hits) / len(full_hits))
            res["simplified"].append(sum(simp_hits) / len(simp_hits))
        res["edqsg_full_mean"] = round(sum(res["edqsg_full"]) / n_repeat, 4)
        res["simplified_mean"] = round(sum(res["simplified"]) / n_repeat, 4)
        res["edqsg_full_std"] = round(_std(res["edqsg_full"]), 4)
        res["simplified_std"] = round(_std(res["simplified"]), 4)
        out[str(ratio)] = res
    return out


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def summarize_baseline(rows):
    injected = [r for r in rows if r["expected"]]
    out = {}
    for pol in ("severity_only", "strength_only", "simplified", "edqsg_full"):
        out[pol] = {
            "top1_accuracy": round(sum(r["policies"][pol]["hit_top1"] for r in injected) / len(injected), 4),
            "top3_hit_rate": round(sum(r["policies"][pol]["hit_top3"] for r in injected) / len(injected), 4),
            "mrr": round(sum(r["policies"][pol]["rr"] for r in injected) / len(injected), 4),
        }
    return out


def markdown(baseline_rows, baseline_summary, deletion, reference_date):
    lines = [
        "# 补充实验：排序基线对照与关系映射删减",
        "",
        f"参考日期：{reference_date.isoformat() if reference_date else '系统日期'}；"
        "受控注入场景 S1~S9（n=9），S0 干净基线不参与命中率统计。",
        "",
        "## 表 A 四种排序策略的命中率",
        "",
        "| 排序策略 | Top-1 | Top-3 | MRR |",
        "|---|---:|---:|---:|",
    ]
    label = {"severity_only": "仅结构缺陷严重度", "strength_only": "仅关系强度",
             "simplified": "简化排序（强度×已确认缺陷）", "edqsg_full": "完整 EDQSG"}
    for pol in ("severity_only", "strength_only", "simplified", "edqsg_full"):
        s = baseline_summary[pol]
        lines.append(f"| {label[pol]} | {s['top1_accuracy']:.2%} | {s['top3_hit_rate']:.2%} | {s['mrr']:.2f} |")
    lines += ["", "## 表 B 逐场景 Top-1", "",
              "| 场景 | 预期根因 | 仅严重度 | 仅关系强度 | 简化排序 | 完整 EDQSG |",
              "|---|---|---|---:|---:|---:|"]
    for r in baseline_rows:
        exp = ",".join(r["expected"]) or "—"
        cells = []
        for pol in ("severity_only", "strength_only", "simplified", "edqsg_full"):
            h = r["policies"][pol]["hit_top1"]
            cells.append("—" if h is None else ("✓" if h else "✗"))
        lines.append(f"| {r['scenario']} | {exp} | " + " | ".join(cells) + " |")
    lines += ["", "## 表 C 关系映射随机删减（Top-1 命中率，均值±标准差）", "",
              "| 删除比例 | 删除关系数 | 重复次数 | 完整 EDQSG | 简化排序 |",
              "|---|---:|---:|---:|---:|"]
    for key, d in deletion.items():
        lines.append(
            f"| {float(key):.0%} | {d['deleted']}/{d['total_relations']} | {d['repeats']} | "
            f"{d['edqsg_full_mean']:.3f}±{d['edqsg_full_std']:.3f} | "
            f"{d['simplified_mean']:.3f}±{d['simplified_std']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference-date", help="ISO-8601 date, e.g. 2026-09-21")
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--ratios", default="0.25,0.50")
    args = ap.parse_args()
    ref = date.fromisoformat(args.reference_date) if args.reference_date else None
    ratios = [float(x) for x in args.ratios.split(",")]

    rows = baseline_experiment(ref)
    summary = summarize_baseline(rows)
    deletion = deletion_experiment(ref, args.repeats, ratios)
    result = {"reference_date": ref.isoformat() if ref else None,
              "baseline": {"scenarios": rows, "summary": summary},
              "deletion": deletion}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "paper_baselines.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    (OUT / "paper_baselines.md").write_text(markdown(rows, summary, deletion, ref),
                                            encoding="utf-8")
    print(markdown(rows, summary, deletion, ref))


if __name__ == "__main__":
    main()
