"""CSV 剖析：把 CSV 表按 DQ/SG 规则映射为 EDQSG 指标与证据（仅标准库）。"""

from __future__ import annotations

from typing import Any

from edqsg import Domain, Evidence, EvidenceType, Indicator


def _is_missing(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _rate(bad: int, total: int) -> float:
    return bad / total if total else 0.0


def _score(rate: float) -> float:
    return max(0.0, 100.0 * (1.0 - rate))


def _evidence(eid: str, etype: EvidenceType, score: float, reliability: dict) -> Evidence:
    return Evidence(
        evidence_id=eid,
        evidence_type=etype,
        source="csv-profiler",
        coverage=reliability.get("coverage", 0.9),
        authority=reliability.get("authority", 0.9),
        timeliness=reliability.get("timeliness", 0.9),
        repeatability=reliability.get("repeatability", 0.9),
        business_fit=reliability.get("business_fit", 0.9),
        observed_score=score,
        description="CSV 剖析自动生成的观测证据",
    )


def _missing_rates(tables: dict[str, list[dict]], checks: list[dict]) -> list[float]:
    rates: list[float] = []
    for check in checks:
        rows = tables[check["table"]]
        cols = check["columns"]
        bad = 0
        for row in rows:
            if any(_is_missing(row.get(col)) for col in cols):
                bad += 1
        rates.append(_rate(bad, len(rows)))
    return rates


def _domain_rates(tables: dict[str, list[dict]], checks: list[dict]) -> list[float]:
    rates: list[float] = []
    for check in checks:
        rows = tables[check["table"]]
        column = check["column"]
        allowed = set(check.get("allowed", []))
        bad = 0
        for row in rows:
            value = str(row.get(column, "")).strip()
            if not _is_missing(value) and value not in allowed:
                bad += 1
        rates.append(_rate(bad, len(rows)))
    return rates


def _duplicate_rates(tables: dict[str, list[dict]], checks: list[dict]) -> list[float]:
    rates: list[float] = []
    for check in checks:
        rows = tables[check["table"]]
        keys = check["columns"]
        seen: dict[tuple, int] = {}
        for row in rows:
            key = tuple(str(row.get(k, "")).strip() for k in keys)
            if all(k != "" for k in key):
                seen[key] = seen.get(key, 0) + 1
        dup_rows = sum(n - 1 for n in seen.values() if n > 1)
        rates.append(_rate(dup_rows, len(rows)))
    return rates


def _orphan_rates(
    tables: dict[str, list[dict]], checks: list[dict]
) -> list[tuple[str, str, float]]:
    results: list[tuple[str, str, float]] = []
    for check in checks:
        child_rows = tables[check["child_table"]]
        parent_rows = tables[check["parent_table"]]
        child_col = check["child_column"]
        parent_col = check["parent_column"]
        parent_keys = {
            str(row.get(parent_col, "")).strip()
            for row in parent_rows
            if not _is_missing(row.get(parent_col))
        }
        bad = 0
        for row in child_rows:
            value = str(row.get(child_col, "")).strip()
            if not _is_missing(value) and value not in parent_keys:
                bad += 1
        rate = _rate(bad, len(child_rows))
        results.append((f"{check['child_table']}.{child_col}", check["parent_table"], rate))
    return results


def _cross_table_rates(
    tables: dict[str, list[dict]], checks: list[dict]
) -> list[float]:
    rates: list[float] = []
    for check in checks:
        child_rows = tables[check["child_table"]]
        parent_rows = tables[check["parent_table"]]
        child_link = check["child_link"]
        parent_link = check["parent_link"]
        child_col = check["child_column"]
        parent_col = check["parent_column"]
        parent_map = {
            str(row.get(parent_link, "")).strip(): str(row.get(parent_col, "")).strip()
            for row in parent_rows
            if not _is_missing(row.get(parent_link))
        }
        bad = 0
        total = 0
        for row in child_rows:
            link = str(row.get(child_link, "")).strip()
            value = str(row.get(child_col, "")).strip()
            if link in parent_map and not _is_missing(value):
                total += 1
                if value != parent_map[link]:
                    bad += 1
        rates.append(_rate(bad, max(total, 1)))
    return rates


def _stale_rates(
    tables: dict[str, list[dict]], checks: list[dict], max_age_days: int
) -> list[float]:
    from datetime import date, datetime

    rates: list[float] = []
    today = date.today()
    for check in checks:
        rows = tables[check["table"]]
        column = check["column"]
        bad = 0
        for row in rows:
            raw = str(row.get(column, "")).strip()
            if _is_missing(raw):
                continue
            try:
                value = datetime.fromisoformat(raw).date()
            except ValueError:
                bad += 1
                continue
            if (today - value).days > max_age_days:
                bad += 1
        rates.append(_rate(bad, len(rows)))
    return rates


def compute_metrics(config: dict, tables: dict[str, list[dict]]) -> dict[str, float]:
    """按配置的 DQ/SG 规则计算各维度问题率与原始指标。"""

    metrics: dict[str, float] = {}
    dq_rules = config.get("dq_rules", {})

    def worst(rates: list[float]) -> float:
        return max(rates) if rates else 0.0

    if "DQ1" in dq_rules:
        missing_rates = _missing_rates(tables, dq_rules["DQ1"]["checks"])
        metrics["dq.DQ1.rate"] = worst(missing_rates)
        for check, rate in zip(dq_rules["DQ1"]["checks"], missing_rates):
            key = check.get("metric_key")
            if key:
                metrics[key] = rate
    if "DQ2" in dq_rules:
        metrics["dq.DQ2.rate"] = worst(_cross_table_rates(tables, dq_rules["DQ2"]["checks"]))
    if "DQ3" in dq_rules:
        metrics["dq.DQ3.rate"] = worst(_domain_rates(tables, dq_rules["DQ3"]["checks"]))
    if "DQ4" in dq_rules:
        metrics["dq.DQ4.rate"] = worst(_duplicate_rates(tables, dq_rules["DQ4"]["checks"]))
    if "DQ5" in dq_rules:
        metrics["dq.DQ5.rate"] = worst(_cross_table_rates(tables, dq_rules["DQ5"]["checks"]))
    if "DQ6" in dq_rules:
        orphan = _orphan_rates(tables, dq_rules["DQ6"]["checks"])
        for key, parent, rate in orphan:
            metrics[f"raw.orphan.{key}->{parent}"] = rate
        metrics["dq.DQ6.rate"] = worst([r for _, _, r in orphan])
    if "DQ7" in dq_rules:
        max_age = int(config.get("stale_max_age_days", 90))
        metrics["dq.DQ7.rate"] = worst(_stale_rates(tables, dq_rules["DQ7"]["checks"], max_age))
    if "DQ8" in dq_rules:
        metrics["dq.DQ8.rate"] = worst(_missing_rates(tables, dq_rules["DQ8"]["checks"]))

    # 原始指标：供底线规则使用
    if "DQ4" in dq_rules:
        dup = _duplicate_rates(tables, dq_rules["DQ4"]["checks"])
        if dup:
            metrics["raw.dup_rate"] = max(dup)
    if "DQ6" in dq_rules:
        orphans = _orphan_rates(tables, dq_rules["DQ6"]["checks"])
        if orphans:
            metrics["raw.orphan_rate"] = max(r for _, _, r in orphans)
    if "DQ8" in dq_rules:
        miss = _missing_rates(tables, dq_rules["DQ8"]["checks"])
        if miss:
            metrics["raw.missing_rate.audit"] = max(miss)
    return metrics


def build_dq_indicators(
    config: dict, tables: dict[str, list[dict]], metrics: dict[str, float]
) -> list[Indicator]:
    reliability = config.get("evidence_reliability", {})
    indicators: list[Indicator] = []
    dq_rules = config.get("dq_rules", {})
    for dq_id in ("DQ1", "DQ2", "DQ3", "DQ4", "DQ5", "DQ6", "DQ7", "DQ8"):
        if dq_id not in dq_rules:
            continue
        rate = metrics.get(f"dq.{dq_id}.rate", 0.0)
        indicators.append(
            Indicator(
                indicator_id=dq_id,
                name=dq_rules[dq_id].get("name", dq_id),
                domain=Domain.DATA_QUALITY,
                evidences=(
                    _evidence(f"CSV-{dq_id}", EvidenceType.DATA, _score(rate), reliability),
                ),
            )
        )
    return indicators


def build_sg_indicators(
    config: dict, tables: dict[str, list[dict]], metrics: dict[str, float]
) -> list[Indicator]:
    """SG 证据：关系控制（SG3）、主数据权威性（SG7）及其余可配置 SG。"""

    reliability = config.get("evidence_reliability", {})
    indicators: list[Indicator] = []

    sg3_evidences: list[Evidence] = []
    for rel in config.get("relationship_controls", []):
        control_score = (
            float(rel.get("control_coverage", 1.0))
            * float(rel.get("control_reliability", 1.0))
            * float(rel.get("operating_effectiveness", 1.0))
        )
        orphan_rate = metrics.get(
            f"raw.orphan.{rel['child_table']}.{rel['child_column']}->{rel['parent_table']}",
            0.0,
        )
        observed = 100.0 * control_score * (1.0 - orphan_rate)
        sg3_evidences.append(
            _evidence(
                f"CSV-SG3-{rel['relationship_id']}",
                EvidenceType.STRUCTURE,
                observed,
                reliability,
            )
        )
    if sg3_evidences:
        indicators.append(
            Indicator(
                indicator_id="SG3",
                name="键与关系控制",
                domain=Domain.STRUCTURAL_GOVERNANCE,
                evidences=tuple(sg3_evidences),
            )
        )

    authority = config.get("master_data_authority", {})
    if authority:
        conflict_rate = metrics.get("dq.DQ5.rate", 0.0)
        observed = 100.0 * float(authority.get("authority_coverage", 1.0)) * (1.0 - conflict_rate)
        indicators.append(
            Indicator(
                indicator_id="SG7",
                name="主数据权威性",
                domain=Domain.STRUCTURAL_GOVERNANCE,
                evidences=(
                    _evidence(
                        "CSV-SG7",
                        EvidenceType.STRUCTURE,
                        observed,
                        reliability,
                    ),
                ),
            )
        )

    for extra in config.get("sg_extra", []):
        indicators.append(
            Indicator(
                indicator_id=extra["indicator_id"],
                name=extra.get("name", extra["indicator_id"]),
                domain=Domain.STRUCTURAL_GOVERNANCE,
                evidences=(
                    _evidence(
                        f"CSV-{extra['indicator_id']}-EXPERT",
                        EvidenceType.EXPERT,
                        float(extra["score"]),
                        reliability,
                    ),
                ),
            )
        )
    return indicators


def build_indicators(
    config: dict, tables: dict[str, list[dict]]
) -> tuple[list[Indicator], dict[str, float]]:
    metrics = compute_metrics(config, tables)
    indicators = build_dq_indicators(config, tables, metrics)
    indicators.extend(build_sg_indicators(config, tables, metrics))
    return indicators, metrics
