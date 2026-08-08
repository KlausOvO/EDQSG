# -*- coding: utf-8 -*-
"""EDQSG 公开基准双表验证（HoloClean dirty+clean）。

实验定位（与论文第 7 节对应）：
  E1 检测性能：规则检测层对公开基准已知缺陷的逐单元 P/R/F1（按行实例计）；
  E2 评价一致性：按数据块比较 EDQSG 综合得分与真实缺陷率的 Spearman 相关，
     并与简单加权平均基线对比；
  E3 敏感性：单因素 ±10% 扰动下的等级反转率与前 K 根因重叠度；
  E4 蒙特卡洛鲁棒性：±10% 联合随机扰动下的得分分布与等级翻转率。

说明：
  - ground truth 采用 HoloClean (tid, attribute, correct_val) 单元级真值；
  - flight 每个航班有多个来源行，评估按“行实例”计，避免按航班去重丢失来源级缺陷；
  - 结构治理域（SG）在公开数据上为 schema 级观测（键完整性、权威源存在性），
    根因与治理闭环验证仍以装备构造算例为主。
"""

from __future__ import annotations

import collections
import csv
import json
import math
import os
import re
from pathlib import Path

import numpy as np

from edqsg import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    Domain,
    EDQSGModel,
    Evidence,
    EvidenceType,
    Indicator,
    TaskLayer,
    GovernanceTemplate,
)
from edqsg.scoring import ScoreCalculator


BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "results"

US_STATES = set(
    """al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo
    mt ne nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy dc""".split()
)

TIME_COLS = [
    "scheduled_dept",
    "actual_dept",
    "dept_gate",
    "scheduled_arrival",
    "actual_arrival",
    "arrival_gate",
]


DATASETS = {
    "hospital": {
        "dirty": "hospital.csv",
        "clean": "hospital_clean.csv",
        "tid_mode": "row_index",
        "monitor_cols": [
            "ProviderNumber",
            "HospitalName",
            "City",
            "State",
            "ZipCode",
            "PhoneNumber",
            "EmergencyService",
        ],
        "detectors": [
            {"rule": "DQ1", "kind": "missing", "columns": ["ProviderNumber", "HospitalName", "City", "State", "ZipCode", "PhoneNumber"]},
            {"rule": "DQ3", "kind": "domain", "column": "State", "allowed": US_STATES, "case_insensitive": True},
            {"rule": "DQ3", "kind": "domain", "column": "EmergencyService", "allowed": {"yes", "no"}, "case_insensitive": True},
            {"rule": "DQ3", "kind": "format", "column": "ZipCode", "pattern": r"^\d{5}$"},
            {"rule": "DQ3", "kind": "format", "column": "ProviderNumber", "pattern": r"^\d{5}$"},
        ],
        "sg": {
            "SG3": {"observed": 100.0, "note": "业务键（ProviderNumber）无缺失，键完整性 100%"},
            "SG7": {"observed": 100.0, "note": "单源权威表，无多源冲突"},
        },
        "coupling": [],
        "bottom_line_rules": [],
        "blocks": 10,
    },
    "adult": {
        "dirty": "adult_dirty0.1.csv",
        "clean": "adult_clean.csv",
        "tid_mode": "row_index",
        "monitor_cols": ["Age", "Workclass", "Education", "Maritalstatus", "Occupation", "Relationship", "Race", "Sex", "HoursPerWeek", "Country", "Income"],
        "detectors": [
            {"rule": "DQ1", "kind": "missing", "columns": ["Age", "Workclass", "Education", "Maritalstatus", "Occupation", "Relationship", "Race", "Sex", "HoursPerWeek", "Country", "Income"]},
            {"rule": "DQ3", "kind": "domain", "column": "Sex", "allowed": {"Male", "Female"}},
            {"rule": "DQ3", "kind": "domain", "column": "Income", "allowed": {"LessThan50K", "MoreThan50K"}},
        ],
        "sg": {
            "SG3": {"observed": 100.0, "note": "全表业务键完整"},
            "SG7": {"observed": 100.0, "note": "单源权威表"},
        },
        "coupling": [],
        "bottom_line_rules": [],
        "blocks": 10,
    },
    "flight": {
        "dirty": "flight.csv",
        "clean": "flight_clean.csv",
        "tid_mode": "flight",
        "monitor_cols": TIME_COLS,
        "detectors": [
            {"rule": "DQ1", "kind": "missing", "columns": TIME_COLS},
            {"rule": "DQ2", "kind": "conflict", "columns": TIME_COLS, "group": "flight"},
        ],
        "sg": {
            "SG3": {"observed": 100.0, "note": "航班键完整"},
            "SG7": {"observed": 40.0, "note": "多来源且无权威源标记，主数据权威性不足"},
        },
        "coupling": [
            {"dq": "DQ2", "sg": "SG7", "strength": 0.80, "confidence": 0.90},
        ],
        "bottom_line_rules": [
            {
                "rule_id": "BL-FLIGHT-MISSING",
                "description": "关键时间字段缺失率超阈值，等级不高于“中”",
                "metric": "dq.DQ1.rate",
                "operator": ">",
                "value": 0.30,
                "cap": 60.0,
            },
        ],
        "blocks": 10,
    },
}


def load_table(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def load_clean(path: Path) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["tid"], row["attribute"])
            result.setdefault(key, row["correct_val"])
    return result


def tid_of(row: dict[str, str], mode: str, index: int) -> str:
    return row[mode] if mode != "row_index" else str(index)


def build_ground_truth(
    rows: list[dict[str, str]],
    clean: dict[tuple[str, str], str],
    tid_mode: str,
    cols: list[str],
    start_index: int = 0,
    index_map: list[int] | None = None,
) -> tuple[set[tuple[int, str]], collections.Counter]:
    """逐行实例的真值缺陷集合与类型分布。"""
    truth: set[tuple[int, str]] = set()
    types: collections.Counter = collections.Counter()
    for i, row in enumerate(rows):
        global_index = index_map[i] if index_map is not None else i + start_index
        tid = tid_of(row, tid_mode, global_index)
        for col in cols:
            if (tid, col) not in clean:
                continue
            dirty = str(row.get(col, "")).strip()
            correct = str(clean[(tid, col)]).strip()
            if dirty != correct:
                truth.add((i, col))
                if dirty == "":
                    types["missing"] += 1
                elif correct == "":
                    types["extra_value"] += 1
                else:
                    types["wrong_value"] += 1
    return truth, types


def detect_missing(rows, columns) -> set[tuple[int, str]]:
    return {
        (i, col)
        for i, row in enumerate(rows)
        for col in columns
        if str(row.get(col, "")).strip() == ""
    }


def detect_domain(rows, column, allowed, case_insensitive=False) -> set[tuple[int, str]]:
    flags: set[tuple[int, str]] = set()
    for i, row in enumerate(rows):
        value = str(row.get(column, "")).strip()
        if not value:
            continue
        candidate = value.lower() if case_insensitive else value
        if candidate not in allowed:
            flags.add((i, column))
    return flags


def detect_format(rows, column, pattern) -> set[tuple[int, str]]:
    compiled = re.compile(pattern)
    return {
        (i, column)
        for i, row in enumerate(rows)
        if str(row.get(column, "")).strip()
        and not compiled.fullmatch(str(row.get(column, "")).strip())
    }


def detect_duplicate(rows, columns) -> set[tuple[int, str]]:
    seen: dict[tuple[str, ...], list[int]] = collections.defaultdict(list)
    for i, row in enumerate(rows):
        key = tuple(str(row.get(col, "")).strip() for col in columns)
        if all(k != "" for k in key):
            seen[key].append(i)
    flags: set[tuple[int, str]] = set()
    for members in seen.values():
        if len(members) > 1:
            for i in members[1:]:
                for col in columns:
                    flags.add((i, col))
    return flags


def detect_conflict(rows, columns, group_col) -> set[tuple[int, str]]:
    """多数投票：组内众数非空值存在且无并列时，与众数不一致的单元格标记为冲突。"""
    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, row in enumerate(rows):
        groups[str(row.get(group_col, "")).strip()].append(i)
    flags: set[tuple[int, str]] = set()
    for members in groups.values():
        for col in columns:
            counter: collections.Counter = collections.Counter()
            for i in members:
                value = str(rows[i].get(col, "")).strip()
                if value:
                    counter[value] += 1
            if not counter:
                continue
            top, count = counter.most_common(1)[0]
            if count < 2:
                continue
            if len(counter) >= 2 and sorted(counter.values(), reverse=True)[1] == count:
                continue
            for i in members:
                value = str(rows[i].get(col, "")).strip()
                if value and value != top:
                    flags.add((i, col))
    return flags


def run_detector(rows, detector) -> set[tuple[int, str]]:
    kind = detector["kind"]
    if kind == "missing":
        return detect_missing(rows, detector["columns"])
    if kind == "domain":
        return detect_domain(
            rows,
            detector["column"],
            detector["allowed"],
            detector.get("case_insensitive", False),
        )
    if kind == "format":
        return detect_format(rows, detector["column"], detector["pattern"])
    if kind == "duplicate":
        return detect_duplicate(rows, detector["columns"])
    if kind == "conflict":
        return detect_conflict(rows, detector["columns"], detector["group"])
    raise ValueError(f"未知检测规则: {kind}")


def prf(flagged: set[tuple[int, str]], truth: set[tuple[int, str]]) -> dict:
    tp = len(flagged & truth)
    fp = len(flagged - truth)
    fn = len(truth - flagged)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def detector_rate(flagged: set[tuple[int, str]], total_cells: int) -> float:
    return len(flagged) / total_cells if total_cells else 0.0


CALIB_SPLIT = 0.7
CALIB_SEED = 20260720
# 标定子集经验并集召回率分档：<0.35 → 低(0.3)，0.35~0.7 → 中(0.6)，>0.7 → 高(0.9)
C_RULE_BUCKETS = ((0.35, 0.3), (0.70, 0.6), (1.01, 0.9))


def calibrate_rule_observability(rows, clean, dataset) -> dict[str, float]:
    """在 70% 标定子集上估计各 DQ 规则并集召回率，按低/中/高分档为 C_rule。
    标定子集用固定种子随机抽取；flight 按航班分组切分，保持组内多源结构完整
    （见论文 7.1 节）。
    """
    rng = np.random.default_rng(CALIB_SEED)
    if dataset["tid_mode"] == "flight":
        flight_ids = list(dict.fromkeys(str(row.get("flight", "")).strip() for row in rows))
        rng.shuffle(flight_ids)
        n_cal = max(1, int(round(len(flight_ids) * CALIB_SPLIT)))
        cal_flights = set(flight_ids[:n_cal])
        cal_idx = [
            i for i, row in enumerate(rows)
            if str(row.get("flight", "")).strip() in cal_flights
        ]
    else:
        order = rng.permutation(len(rows))
        n_cal = max(1, int(round(len(rows) * CALIB_SPLIT)))
        cal_idx = order[:n_cal].tolist()
    index_map = [i for i in range(len(rows)) if i in set(cal_idx)]
    cal_rows = [rows[i] for i in index_map]
    monitor_cols = dataset["monitor_cols"]
    truth, _ = build_ground_truth(
        cal_rows, clean, dataset["tid_mode"], monitor_cols, index_map=index_map
    )
    by_rule: dict[str, set[tuple[int, str]]] = collections.defaultdict(set)
    for detector in dataset["detectors"]:
        flagged = run_detector(cal_rows, detector)
        by_rule[detector["rule"]] |= flagged
    result: dict[str, float] = {}
    for rule, flagged in by_rule.items():
        recall = len(flagged & truth) / len(truth) if truth else 1.0
        for threshold, bucket in C_RULE_BUCKETS:
            if recall < threshold:
                result[rule] = bucket
                break
        else:
            result[rule] = 0.9
    return result


def build_clean_table(rows, clean, dataset) -> list[dict[str, str]]:
    """用单元级真值替换监测单元格，构造干净对照表。"""
    result = []
    for i, row in enumerate(rows):
        new_row = dict(row)
        tid = tid_of(row, dataset["tid_mode"], i)
        for col in dataset["monitor_cols"]:
            if (tid, col) in clean:
                new_row[col] = clean[(tid, col)]
        result.append(new_row)
    return result


def inject_defects(
    clean_rows: list[dict[str, str]],
    dataset: dict,
    level: float,
    seed: int,
) -> list[dict[str, str]]:
    """按水平注入与参与指标规则可观测的缺陷类型：
    hospital 注入 DQ3 观测列的域值/格式违规；flight 注入 DQ1 观测列缺失。
    """
    rows = [dict(r) for r in clean_rows]
    if dataset["dirty"].startswith("hospital"):
        target_cols = ["State", "EmergencyService", "ZipCode", "ProviderNumber"]
        types = ["domain", "format"]
    else:
        target_cols = dataset["monitor_cols"]
        types = ["missing"]
    total = len(rows) * len(target_cols)
    n = int(round(level * total))
    rng = np.random.default_rng(seed)
    cells = rng.choice(total, size=n, replace=False)
    for pos in cells:
        r, c = divmod(int(pos), len(target_cols))
        col = target_cols[c]
        kind = types[rng.integers(0, len(types))]
        if kind == "missing":
            rows[r][col] = ""
        elif kind == "domain":
            if col == "State":
                rows[r][col] = "XX"
            elif col == "EmergencyService":
                rows[r][col] = "Maybe"
            else:
                rows[r][col] = "BADVALUE"
        elif kind == "format":
            rows[r][col] = "1234x"
    return rows


def run_contamination(dataset_name: str, dataset: dict, rule_obs: dict[str, float], reliability: float = 0.95) -> dict:
    """污染率控制实验：0%~60% 七档，报告得分单调性、ρ 与 95% 置信区间。"""
    rows = load_table(DATA / dataset["dirty"])
    clean = load_clean(DATA / dataset["clean"])
    clean_rows = build_clean_table(rows, clean, dataset)
    levels = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.60]
    scores = []
    rows_out = []
    for level in levels:
        injected = inject_defects(clean_rows, dataset, level, seed=20260808 + int(level * 1000))
        indicators, metrics = build_indicators(
            dataset_name,
            injected,
            dataset["detectors"],
            dataset["monitor_cols"],
            dataset["sg"],
            reliability,
            rule_obs,
        )
        dq_ids = [item.indicator_id for item in indicators if item.domain is Domain.DATA_QUALITY]
        sg_ids = [item.indicator_id for item in indicators if item.domain is Domain.STRUCTURAL_GOVERNANCE]
        model = EDQSGModel()
        try:
            report = model.evaluate(
                indicators=indicators,
                dq_weights=weights(dq_ids),
                sg_weights=weights(sg_ids),
                coupling_calibrations=build_couplings(dataset),
                bottom_line_triggers=build_triggers(dataset, metrics),
                governance_templates=[],
            )
            score = report.final_score
            grade = report.overall_grade.value
        except ValueError:
            score = None
            grade = "证据不足"
        rows_out.append({"level": level, "score": score, "grade": grade})
        if score is not None:
            scores.append((level, score))
    rho = None
    ci = None
    if len(scores) >= 3:
        rho = _spearman([x for x, _ in scores], [y for _, y in scores])
        ci = _bootstrap_rho([x for x, _ in scores], [y for _, y in scores], seed=20260809)
    return {
        "dataset": dataset_name,
        "levels": rows_out,
        "spearman": round(rho, 4) if rho is not None else None,
        "bootstrap_95ci": ci,
    }


def _bootstrap_rho(xs, ys, seed: int = 20260809, n: int = 1000) -> list[float]:
    rng = np.random.default_rng(seed)
    values = []
    data = list(zip(xs, ys))
    for _ in range(n):
        sample = [data[int(rng.integers(0, len(data)))] for _ in range(len(data))]
        rho = _spearman([a for a, _ in sample], [b for _, b in sample])
        if rho is not None:
            values.append(rho)
    if not values:
        return []
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def make_evidence(
    evidence_id: str,
    etype: EvidenceType,
    observed: float,
    reliability: float,
    rule_observability: float = 1.0,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        evidence_type=etype,
        source="holoclean-benchmark",
        coverage=reliability,
        authority=reliability,
        timeliness=reliability,
        repeatability=reliability,
        business_fit=reliability,
        rule_observability=rule_observability,
        sample_coverage=1.0,
        observed_score=observed,
        description="公开基准规则检测证据",
    )


def build_indicators(
    dataset_name: str,
    rows: list[dict[str, str]],
    detectors: list[dict],
    monitor_cols: list[str],
    sg: dict,
    reliability: float = 0.95,
    rule_observability: dict[str, float] | None = None,
) -> tuple[list[Indicator], dict[str, float]]:
    rule_observability = rule_observability or {}
    total_monitored = len(rows) * len(monitor_cols)
    rate_by_rule: dict[str, list[float]] = collections.defaultdict(list)
    for detector in detectors:
        flagged = run_detector(rows, detector)
        rate = detector_rate(flagged, total_monitored)
        rule = detector["rule"]
        key = f"det.{rule}.{detector['kind']}.{detector.get('column', detector.get('group', ''))}"
        rate_by_rule[rule].append(rate)
    metrics: dict[str, float] = {}
    indicators: list[Indicator] = []
    for rule, rates in rate_by_rule.items():
        worst = max(rates)
        metrics[f"dq.{rule}.rate"] = worst
        observed = 100.0 * (1.0 - worst)
        indicators.append(
            Indicator(
                indicator_id=rule,
                name=rule,
                domain=Domain.DATA_QUALITY,
                evidences=(
                    make_evidence(
                        f"CSV-{rule}",
                        EvidenceType.DATA,
                        observed,
                        reliability,
                        rule_observability.get(rule, 1.0),
                    ),
                ),
            )
        )
    for sg_id, spec in sg.items():
        indicators.append(
            Indicator(
                indicator_id=sg_id,
                name=sg_id,
                domain=Domain.STRUCTURAL_GOVERNANCE,
                evidences=(
                    make_evidence(
                        f"CSV-{sg_id}",
                        EvidenceType.STRUCTURE,
                        float(spec["observed"]),
                        reliability,
                        rule_observability.get(sg_id, 1.0),
                    ),
                ),
            )
        )
        metrics[f"sg.{sg_id}.observed"] = float(spec["observed"])
    return indicators, metrics


def weights(indicator_ids: list[str]) -> dict[str, float]:
    w = {item: 1.0 / len(indicator_ids) for item in indicator_ids}
    return w


def build_triggers(dataset: dict, metrics: dict[str, float]) -> list[BottomLineTrigger]:
    triggers: list[BottomLineTrigger] = []
    for rule in dataset.get("bottom_line_rules", []):
        actual = float(metrics.get(rule["metric"], 0.0))
        op = rule.get("operator", ">")
        hit = actual > float(rule["value"]) if op == ">" else actual >= float(rule["value"])
        if hit:
            triggers.append(
                BottomLineTrigger(
                    rule_id=rule["rule_id"],
                    description=rule["description"],
                    cap=float(rule["cap"]),
                )
            )
    return triggers


def build_couplings(dataset: dict) -> list[CouplingCalibrationInput]:
    return [
        CouplingCalibrationInput(
            dq_indicator_id=item["dq"],
            sg_indicator_id=item["sg"],
            normative_strength=float(item["strength"]),
            normative_confidence=float(item["confidence"]),
        )
        for item in dataset.get("coupling", [])
    ]


def evaluate_dataset(
    dataset_name: str,
    dataset: dict,
    reliability: float = 0.95,
) -> dict:
    rows = load_table(DATA / dataset["dirty"])
    clean = load_clean(DATA / dataset["clean"])
    monitor_cols = dataset["monitor_cols"]
    truth, truth_types = build_ground_truth(rows, clean, dataset["tid_mode"], monitor_cols)

    detector_results = []
    union_flags: set[tuple[int, str]] = set()
    for detector in dataset["detectors"]:
        flagged = run_detector(rows, detector)
        union_flags |= flagged
        detector_results.append(
            {
                "rule": detector["rule"],
                "kind": detector["kind"],
                "column": detector.get("column", detector.get("group", "")),
                "flagged": len(flagged),
                "rate": round(detector_rate(flagged, len(rows) * len(monitor_cols)), 4),
                **prf(flagged, truth),
            }
        )

    rule_obs = calibrate_rule_observability(rows, clean, dataset)
    indicators, metrics = build_indicators(
        dataset_name, rows, dataset["detectors"], monitor_cols, dataset["sg"],
        reliability, rule_obs,
    )
    dq_ids = [item.indicator_id for item in indicators if item.domain is Domain.DATA_QUALITY]
    sg_ids = [item.indicator_id for item in indicators if item.domain is Domain.STRUCTURAL_GOVERNANCE]
    dq_w = weights(dq_ids)
    sg_w = weights(sg_ids)
    triggers = build_triggers(dataset, metrics)
    couplings = build_couplings(dataset)

    model = EDQSGModel()
    fused = [model.evidence_engine.fuse(item) for item in indicators]
    try:
        report = model.evaluate(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_calibrations=couplings,
            bottom_line_triggers=triggers,
            governance_templates=[],
        )
        evaluated = True
    except ValueError as exc:
        report = None
        evaluated = False
        evaluate_error = str(exc)

    if evaluated:
        sensitivity = model.sensitivity(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_relations=model.coupling_calibrator.calibrate_many(couplings),
            bottom_line_triggers=triggers,
            perturbations=(0.9, 1.1),
            top_k=3,
        )
        robustness = model.robustness(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_relations=model.coupling_calibrator.calibrate_many(couplings),
            bottom_line_triggers=triggers,
            iterations=300,
            perturbation=0.10,
            perturb_bottom_line=True,
        )
        # 仅模型参数扰动（底线限级值固定为政策参数）的蒙特卡洛
        robustness_model_only = model.robustness(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_relations=model.coupling_calibrator.calibrate_many(couplings),
            bottom_line_triggers=triggers,
            iterations=300,
            perturbation=0.10,
            perturb_bottom_line=False,
        )

    # 基线：简单加权平均（同一指标集、同一权重）
    raw_scores = {
        item.indicator_id: 100.0 * (1.0 - metrics.get(f"dq.{item.indicator_id}.rate", 0.0))
        if item.domain is Domain.DATA_QUALITY
        else float(metrics.get(f"sg.{item.indicator_id}.observed", 100.0))
        for item in indicators
    }
    baseline_q = sum(dq_w[i] * raw_scores[i] for i in dq_ids)
    baseline_s = sum(sg_w[i] * raw_scores[i] for i in sg_ids)
    baseline_g = math.sqrt(baseline_q * baseline_s)

    # 消融：未知度不解耦（未知质量计零，不归一化）、无排除、无底线
    if evaluated:
        abl_score = _raw_unknown_zero_score(report, dq_w, sg_w, model.config.grade_utilities)
        no_bl_report = model.evaluate(
            indicators=indicators,
            dq_weights=dq_w,
            sg_weights=sg_w,
            coupling_calibrations=couplings,
            bottom_line_triggers=[],
            governance_templates=[],
        )
    else:
        abl_score = None
        no_bl_report = None

    block_rows = _block_results(rows, clean, dataset, dq_w, sg_w, reliability, rule_obs)
    corr = _spearman_correlations(block_rows)

    if evaluated:
        edqsg_out = {
            "status": "evaluated",
            "dq_score": round(report.dq.score, 2),
            "dq_confidence": round(report.dq.confidence, 3),
            "sg_score": round(report.sg.score, 2),
            "sg_confidence": round(report.sg.confidence, 3),
            "initial_score": round(report.initial_score, 2),
            "final_score": round(report.final_score, 2),
            "grade": report.overall_grade.value,
            "evidence_coverage": round(report.evidence_coverage, 3),
            "excluded_indicators": list(report.excluded_indicator_ids),
            "review_indicators": list(report.review_indicator_ids),
            "bottom_line_triggers": [t.rule_id for t in report.bottom_line_triggers],
            "root_causes": [
                {
                    "sg_indicator_id": r.sg_indicator_id,
                    "contribution": round(r.contribution, 5),
                    "normalized": round(r.normalized_contribution, 4) if r.normalized_contribution is not None else None,
                }
                for r in report.root_causes
                if not r.below_threshold and not r.low_confidence
            ],
            "indicator_results": [
                {
                    "indicator_id": item.indicator_id,
                    "score": round(item.score, 2),
                    "confidence": round(item.confidence, 3),
                    "unknown": round(item.unknown_degree, 3),
                    "review_state": item.review_state,
                }
                for item in report.indicator_results
            ],
        }
    else:
        edqsg_out = {
            "status": "evidence_insufficient",
            "reason": evaluate_error,
            "excluded_indicators": [
                item.indicator_id
                for item in fused
                if item.unknown_degree > 0.5 or item.review_state == "conflict"
            ],
            "review_indicators": [item.indicator_id for item in fused if item.review_required],
            "indicator_results": [
                {
                    "indicator_id": item.indicator_id,
                    "score": round(item.score, 2),
                    "confidence": round(item.confidence, 3),
                    "unknown": round(item.unknown_degree, 3),
                    "review_state": item.review_state,
                }
                for item in fused
            ],
        }

    contamination = None
    if dataset_name in ("hospital", "flight"):
        contamination = run_contamination(dataset_name, dataset, rule_obs, reliability)

    return {
        "dataset": dataset_name,
        "dirty_file": dataset["dirty"],
        "clean_file": dataset["clean"],
        "rows": len(rows),
        "columns": len(monitor_cols),
        "monitored_cells": len(rows) * len(monitor_cols),
        "truth": {
            "total_defects": len(truth),
            "by_type": dict(truth_types),
            "defect_rate": round(len(truth) / (len(rows) * len(monitor_cols)), 4),
        },
        "rule_observability": {key: value for key, value in rule_obs.items()},
        "detectors": detector_results,
        "union_detection": {
            "flagged": len(union_flags),
            **prf(union_flags, truth),
        },
        "edqsg": edqsg_out,
        "baseline": {
            "weighted_average_score": round(baseline_g, 2),
            "grade": ScoreCalculator.grade(baseline_g, model.config.grade_boundaries).value,
            "score_diff": round(report.final_score - baseline_g, 2) if evaluated else None,
        },
        "ablation_unknown_decoupled": (
            None
            if abl_score is None
            else {
                "score": round(abl_score["score"], 2),
                "grade": abl_score["grade"],
                "score_diff": round(report.final_score - abl_score["score"], 2),
            }
        ),
        "ablation_no_bottom_line": (
            None
            if no_bl_report is None
            else {
                "final_score": round(no_bl_report.final_score, 2),
                "grade": no_bl_report.overall_grade.value,
                "score_diff": round(report.final_score - no_bl_report.final_score, 2),
            }
        ),
        "sensitivity": (
            None
            if not evaluated
            else {
                "max_abs_score_change": round(sensitivity.max_abs_score_change, 2),
                "grade_flip_rate": round(sensitivity.grade_flip_rate, 4),
                "min_root_top_k_overlap": round(sensitivity.min_root_top_k_overlap, 4),
                "cases": len(sensitivity.cases),
            }
        ),
        "robustness": (
            None
            if not evaluated
            else {
                "policy_inclusive": {
                    "iterations": robustness.iterations,
                    "perturbation": robustness.perturbation,
                    "baseline_score": round(robustness.baseline_score, 2),
                    "score_mean": round(robustness.score_mean, 2),
                    "score_std": round(robustness.score_std, 2),
                    "score_q05": round(robustness.score_quantiles[0], 2),
                    "score_q50": round(robustness.score_quantiles[1], 2),
                    "score_q95": round(robustness.score_quantiles[2], 2),
                    "grade_flip_rate": round(robustness.grade_flip_rate, 4),
                },
                "model_only": {
                    "iterations": robustness_model_only.iterations,
                    "perturbation": robustness_model_only.perturbation,
                    "baseline_score": round(robustness_model_only.baseline_score, 2),
                    "score_mean": round(robustness_model_only.score_mean, 2),
                    "score_std": round(robustness_model_only.score_std, 2),
                    "score_q05": round(robustness_model_only.score_quantiles[0], 2),
                    "score_q50": round(robustness_model_only.score_quantiles[1], 2),
                    "score_q95": round(robustness_model_only.score_quantiles[2], 2),
                    "grade_flip_rate": round(robustness_model_only.grade_flip_rate, 4),
                },
            }
        ),
        "contamination": contamination,
        "block_correlation": corr,
        "blocks": block_rows,
    }


def _raw_unknown_zero_score(report, dq_w, sg_w, utilities) -> dict:
    """“未知度不解耦”口径：未知质量计零，得分 = Σ b_k·u_k（不做已知归一化）。
    同时不执行排除（全部指标参与）与底线约束。"""

    def domain_raw(domain: Domain, weights: dict[str, float]) -> float:
        total = 0.0
        for item in report.indicator_results:
            if item.domain is not domain:
                continue
            if item.indicator_id not in weights:
                continue
            raw = float(np.dot(item.belief_degrees, utilities))
            total += weights[item.indicator_id] * raw
        return total

    q = domain_raw(Domain.DATA_QUALITY, dq_w)
    s = domain_raw(Domain.STRUCTURAL_GOVERNANCE, sg_w)
    score = math.sqrt(q * s)
    return {
        "score": score,
        "grade": ScoreCalculator.grade(score, EDQSGModel().config.grade_boundaries).value,
    }


def _block_results(rows, clean, dataset, dq_w, sg_w, reliability, rule_obs=None) -> list[dict]:
    rule_obs = rule_obs or {}
    n_blocks = int(dataset.get("blocks", 10))
    if dataset["tid_mode"] == "row_index":
        size = max(1, math.ceil(len(rows) / n_blocks))
        chunks = [
            (rows[b * size : (b + 1) * size], b * size)
            for b in range(n_blocks)
            if rows[b * size : (b + 1) * size]
        ]
    else:
        # flight：按航班分组切块，保持组内完整性
        flight_ids = []
        for row in rows:
            fid = str(row.get("flight", "")).strip()
            if not flight_ids or flight_ids[-1][0] != fid:
                flight_ids.append([fid, []])
            flight_ids[-1][1].append(row)
        chunks = []
        current: list[dict] = []
        target = max(1, math.ceil(len(rows) / n_blocks))
        for _, group in flight_ids:
            current.extend(group)
            if len(current) >= target:
                chunks.append((current, 0))
                current = []
        if current:
            chunks.append((current, 0))
    results = []
    for b, (chunk, start) in enumerate(chunks):
        monitor_cols = dataset["monitor_cols"]
        truth, _ = build_ground_truth(
            chunk, clean, dataset["tid_mode"], monitor_cols, start_index=start
        )
        rate = len(truth) / (len(chunk) * len(monitor_cols)) if chunk else 0.0
        indicators, metrics = build_indicators(
            dataset["dirty"], chunk, dataset["detectors"], monitor_cols, dataset["sg"],
            reliability, rule_obs,
        )
        dq_ids = [item.indicator_id for item in indicators if item.domain is Domain.DATA_QUALITY]
        sg_ids = [item.indicator_id for item in indicators if item.domain is Domain.STRUCTURAL_GOVERNANCE]
        model = EDQSGModel()
        try:
            report = model.evaluate(
                indicators=indicators,
                dq_weights={k: v for k, v in dq_w.items() if k in dq_ids},
                sg_weights={k: v for k, v in sg_w.items() if k in sg_ids},
                coupling_calibrations=build_couplings(dataset),
                bottom_line_triggers=build_triggers(dataset, metrics),
                governance_templates=[],
            )
            evaluated = True
        except ValueError:
            report = None
            evaluated = False
        raw = {
            item.indicator_id: (
                100.0 * (1.0 - metrics.get(f"dq.{item.indicator_id}.rate", 0.0))
                if item.domain is Domain.DATA_QUALITY
                else float(metrics.get(f"sg.{item.indicator_id}.observed", 100.0))
            )
            for item in indicators
        }
        base_q = sum((dq_w.get(i, 0.0)) * raw[i] for i in dq_ids)
        base_s = sum((sg_w.get(i, 0.0)) * raw[i] for i in sg_ids)
        base_g = math.sqrt(base_q * base_s)
        results.append(
            {
                "block": b + 1,
                "rows": len(chunk),
                "truth_defect_rate": round(rate, 4),
                "edqsg_score": round(report.final_score, 2) if evaluated else None,
                "edqsg_grade": report.overall_grade.value if evaluated else "证据不足",
                "weighted_average_score": round(base_g, 2),
                "evidence_coverage": round(report.evidence_coverage, 3) if evaluated else 0.0,
            }
        )
    return results


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                result[order[k]] = rank
            i = j + 1
        return result

    rx = ranks(xs)
    ry = ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx * vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def _spearman_correlations(blocks: list[dict]) -> dict:
    valid = [b for b in blocks if b["edqsg_score"] is not None]
    if len(valid) < 3:
        return {}
    defect = [b["truth_defect_rate"] for b in valid]
    edqsg = [b["edqsg_score"] for b in valid]
    wavg = [b["weighted_average_score"] for b in valid]
    result: dict = {}
    edqsg_rho = _spearman(defect, edqsg)
    wavg_rho = _spearman(defect, wavg)
    if edqsg_rho is not None:
        result["spearman_truth_vs_edqsg"] = round(edqsg_rho, 4)
    if wavg_rho is not None:
        result["spearman_truth_vs_wavg"] = round(wavg_rho, 4)
    return result


def markdown_report(results: list[dict]) -> str:
    lines = [
        "# EDQSG 公开基准验证结果（HoloClean dirty+clean）",
        "",
        "## 表 A 数据集概况与真值",
        "",
        "| 数据集 | 行数 | 监测单元 | 真值缺陷数 | 缺失 | 错误值 | 缺陷率 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        t = r["truth"]
        lines.append(
            f"| {r['dataset']} | {r['rows']} | {r['monitored_cells']} | {t['total_defects']} "
            f"| {t['by_type'].get('missing', 0)} | {t['by_type'].get('wrong_value', 0)} "
            f"| {t['defect_rate']:.1%} |"
        )
    lines += [
        "",
        "## 表 B 检测性能（逐单元 P/R/F1，按行实例）",
        "",
        "| 数据集 | 规则 | 检出数 | 精确率 | 召回率 | F1 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in results:
        for d in r["detectors"]:
            lines.append(
                f"| {r['dataset']} | {d['rule']}({d['kind']}:{d['column']}) | {d['flagged']} "
                f"| {d['precision']:.3f} | {d['recall']:.3f} | {d['f1']:.3f} |"
            )
        u = r["union_detection"]
        lines.append(
            f"| {r['dataset']} | 并集 | {u['flagged']} | {u['precision']:.3f} "
            f"| {u['recall']:.3f} | {u['f1']:.3f} |"
        )
    lines += [
        "",
        "## 表 C EDQSG 评价与基线对比",
        "",
        "| 数据集 | C_rule | Q | S | G(EDQSG) | 等级 | 加权平均G | 加权平均等级 | 差 | 覆盖率 | 排除指标 | 复核指标 | 底线 |",
        "|---|---:|---:|---:|---:|:--:|---:|:--:|---:|---|---|---|---|",
    ]
    for r in results:
        e = r["edqsg"]
        b = r["baseline"]
        crow = "、".join(f"{k}:{v}" for k, v in r["rule_observability"].items())
        if e["status"] == "evidence_insufficient":
            lines.append(
                f"| {r['dataset']} | {crow} | - | - | - | 不出具等级（证据不足） "
                f"| {b['weighted_average_score']:.1f} | {b['grade']} | - | 0.00 "
                f"| {','.join(e['excluded_indicators']) or '-'} "
                f"| {','.join(e['review_indicators']) or '-'} | - |"
            )
        else:
            lines.append(
                f"| {r['dataset']} | {crow} | {e['dq_score']:.1f} | {e['sg_score']:.1f} "
                f"| {e['final_score']:.1f} | {e['grade']} | {b['weighted_average_score']:.1f} "
                f"| {b['grade']} | {b['score_diff']:+.1f} | {e['evidence_coverage']:.2f} "
                f"| {','.join(e['excluded_indicators']) or '-'} "
                f"| {','.join(e['review_indicators']) or '-'} "
                f"| {','.join(e['bottom_line_triggers']) or '-'} |"
            )
    lines += [
        "",
        "## 表 D 消融：底线约束与未知度解耦",
        "",
        "| 数据集 | EDQSG G | 无底线 G | 不解耦(未知计零)+无底线 G | EDQSG-无底线 |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        nbl = r["ablation_no_bottom_line"]
        a = r["ablation_unknown_decoupled"]
        if nbl is None or a is None:
            lines.append(f"| {r['dataset']} | 不出具等级（证据不足） | - | - | - |")
        else:
            lines.append(
                f"| {r['dataset']} | {r['edqsg']['final_score']:.1f} | {nbl['final_score']:.1f} "
                f"| {a['score']:.1f} | {nbl['score_diff']:+.1f} |"
            )
    lines += [
        "",
        "## 表 E 敏感性（±10%单因素）与蒙特卡洛鲁棒性",
        "",
        "| 数据集 | 最大|ΔG| | 单因素反转率 | 根因Top3最小重叠 | MC(含底线)反转率 | MC(仅模型)反转率 | MC(仅模型)5%~95% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        s = r["sensitivity"]
        m = r["robustness"]
        if s is None or m is None:
            lines.append(f"| {r['dataset']} | - | - | - | - | - | - |")
        else:
            mi = m["policy_inclusive"]
            mo = m["model_only"]
            lines.append(
                f"| {r['dataset']} | {s['max_abs_score_change']:.1f} | {s['grade_flip_rate']:.2%} "
                f"| {s['min_root_top_k_overlap']:.2f} | {mi['grade_flip_rate']:.2%} "
                f"| {mo['grade_flip_rate']:.2%} | {mo['score_q05']:.1f}~{mo['score_q95']:.1f} |"
            )
    lines += [
        "",
        "## 表 F 分块评价一致性（Spearman）",
        "",
        "| 数据集 | ρ(缺陷率, EDQSG) | ρ(缺陷率, 加权平均) |",
        "|---|---:|---:|",
    ]
    for r in results:
        c = r["block_correlation"]
        lines.append(
            f"| {r['dataset']} | {c.get('spearman_truth_vs_edqsg', '-'):} "
            f"| {c.get('spearman_truth_vs_wavg', '-'):} |"
        )
    lines += [
        "",
        "## 表 G 污染率控制实验（规则可观测缺陷注入）",
        "",
        "| 数据集 | 0% | 5% | 10% | 20% | 30% | 40% | 60% | ρ | 95%CI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        c = r["contamination"]
        if c is None:
            continue
        vals = []
        for item in c["levels"]:
            vals.append(f"{item['score']:.1f}" if item["score"] is not None else "证据不足")
        ci = (
            f"[{c['bootstrap_95ci'][0]:.3f}, {c['bootstrap_95ci'][1]:.3f}]"
            if c["bootstrap_95ci"]
            else "-"
        )
        lines.append(
            f"| {r['dataset']} | " + " | ".join(vals) + f" | {c['spearman']} | {ci} |"
        )
    lines.append("")
    return "\n".join(lines)


def _pooled_correlation(results: list[dict]) -> dict:
    defects = []
    edqsg = []
    wavg = []
    for r in results:
        for b in r["blocks"]:
            if b["edqsg_score"] is not None:
                defects.append(b["truth_defect_rate"])
                edqsg.append(b["edqsg_score"])
                wavg.append(b["weighted_average_score"])
    result: dict = {}
    edqsg_rho = _spearman(defects, edqsg)
    wavg_rho = _spearman(defects, wavg)
    if edqsg_rho is not None:
        result["spearman_truth_vs_edqsg"] = round(edqsg_rho, 4)
    if wavg_rho is not None:
        result["spearman_truth_vs_wavg"] = round(wavg_rho, 4)
    return result


def main() -> None:
    results = []
    for name, dataset in DATASETS.items():
        print(f"==> 运行 {name} 基准")
        results.append(evaluate_dataset(name, dataset))
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "datasets": results,
        "pooled_correlation": _pooled_correlation(results),
    }
    (OUT / "benchmark_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "benchmark_results.md").write_text(markdown_report(results), encoding="utf-8")
    print("结果已输出:", OUT)


if __name__ == "__main__":
    main()
