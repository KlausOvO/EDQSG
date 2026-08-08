"""[CORE] 将SQL Server元数据与剖析结果映射为EDQSG模型输入。

本模块提供通用自动初评。无法仅凭数据库自动确定的业务语义会降低证据的
``business_fit``并保留未知度；业务规则配置越充分，评价可信度越高。
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from itertools import combinations
from typing import Iterable

from ..config import EDQSGConfig
from ..models import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    Domain,
    Evidence,
    EvidenceType,
    GovernanceTemplate,
    Indicator,
    RedundancyAssessment,
    TaskLayer,
)
from ..redundancy import RedundancyAnalyzer

from .config import SQLServerRuleConfig, SQLServerScanConfig
from .metadata import ColumnMetadata, DatabaseMetadata, TableMetadata
from .profiler import DatabaseProfile


INDICATOR_NAMES = {
    "DQ1": "完整性",
    "DQ2": "准确性",
    "DQ3": "规范性",
    "DQ4": "唯一性",
    "DQ5": "一致性",
    "DQ6": "关联完整性",
    "DQ7": "时效性",
    "DQ8": "可追溯性",
    "SG1": "数据元与字段设计规范性",
    "SG2": "表模型合理性",
    "SG3": "键与关系控制",
    "SG4": "表间关系清晰性",
    "SG5": "字段冗余控制",
    "SG6": "表冗余控制",
    "SG7": "主数据权威性",
    "SG8": "结构生命周期与互操作准备度",
}


class SQLServerEvidenceBuilder:
    """构建指标、耦合、底线、冗余与治理知识模板。"""

    def __init__(
        self,
        metadata: DatabaseMetadata,
        profile: DatabaseProfile,
        scan: SQLServerScanConfig,
        rules: SQLServerRuleConfig,
        model_config: EDQSGConfig | None = None,
    ):
        self.metadata = metadata
        self.profile = profile
        self.scan = scan
        self.rules = rules
        self.model_config = model_config or EDQSGConfig()
        self.table_map = metadata.table_map()
        self.redundancy_analyzer = RedundancyAnalyzer(
            self.model_config.field_similarity_weights,
            self.model_config.table_similarity_weights,
            self.model_config.redundancy_risk_weights,
            self.model_config.redundancy_risk_thresholds,
        )

    @staticmethod
    def _weighted_rate(items: Iterable[tuple[int, int]]) -> tuple[float | None, int]:
        """由(问题数,适用数)计算加权问题率。"""

        numerator = 0
        denominator = 0
        for bad, applicable in items:
            if applicable <= 0:
                continue
            numerator += max(0, bad)
            denominator += applicable
        if denominator <= 0:
            return None, 0
        return min(1.0, numerator / denominator), denominator

    @staticmethod
    def _score_from_rate(rate: float) -> float:
        return max(0.0, min(100.0, 100.0 * (1.0 - rate)))

    @staticmethod
    def _mean(values: Iterable[float]) -> float | None:
        data = list(values)
        return None if not data else sum(data) / len(data)

    def _evidence(
        self,
        evidence_id: str,
        evidence_type: EvidenceType,
        source: str,
        score: float,
        *,
        coverage: float,
        authority: float,
        business_fit: float,
        description: str,
        basis: str = "",
        unknown: float = 0.0,
        importance: float = 1.0,
    ) -> Evidence:
        return Evidence(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            source=source,
            coverage=max(0.0, min(1.0, coverage)),
            authority=max(0.0, min(1.0, authority)),
            timeliness=0.95,
            repeatability=0.98,
            business_fit=max(0.0, min(1.0, business_fit)),
            observed_score=max(0.0, min(100.0, score)),
            unknown_degree=max(0.0, min(1.0, unknown)),
            importance=max(0.0, min(1.0, importance)),
            description=description,
            collected_at=self.profile.collected_at,
            scope=self.metadata.database_name,
            basis=basis,
        )

    @staticmethod
    def _indicator(indicator_id: str, evidences: list[Evidence]) -> Indicator:
        domain = Domain.DATA_QUALITY if indicator_id.startswith("DQ") else Domain.STRUCTURAL_GOVERNANCE
        return Indicator(
            indicator_id=indicator_id,
            name=INDICATOR_NAMES[indicator_id],
            domain=domain,
            evidences=tuple(evidences),
            base_score=70.0 if not evidences else None,
            description=(
                "缺少直接证据，暂以中性基础分占位并标记高未知度。"
                if not evidences
                else ""
            ),
        )

    def build_indicators(
        self, redundancy_results: list[RedundancyAssessment] | None = None
    ) -> list[Indicator]:
        evidence_map: dict[str, list[Evidence]] = {key: [] for key in INDICATOR_NAMES}
        self._build_dq_evidence(evidence_map)
        redundancy = (
            self.build_redundancy_results()
            if redundancy_results is None
            else redundancy_results
        )
        self._build_sg_evidence(evidence_map, redundancy)
        self._build_supplemental_evidence(evidence_map)
        return [self._indicator(key, evidence_map[key]) for key in INDICATOR_NAMES]

    def _build_supplemental_evidence(self, out: dict[str, list[Evidence]]) -> None:
        """把流程日志、制度审查和专家判断作为一等证据接入自动流水线。"""

        for item in self.rules.supplemental_evidence:
            out[item.indicator_id].append(
                Evidence(
                    evidence_id=item.evidence_id,
                    evidence_type=EvidenceType(item.evidence_type),
                    source=item.source,
                    coverage=item.coverage,
                    authority=item.authority,
                    timeliness=item.timeliness,
                    repeatability=item.repeatability,
                    business_fit=item.business_fit,
                    observed_score=item.observed_score,
                    belief_degrees=item.belief_degrees,
                    unknown_degree=item.unknown_degree,
                    importance=item.importance,
                    description=item.description,
                    collected_at=item.collected_at or self.profile.collected_at,
                    scope=item.scope or self.metadata.database_name,
                    basis=item.basis,
                )
            )

    def _build_dq_evidence(self, out: dict[str, list[Evidence]]) -> None:
        # DQ1：优先使用业务必填规则；规则缺失时使用通用缺失率，但降低业务适配度。
        if self.profile.required_columns:
            rate, applicable = self._weighted_rate(
                (item.missing_count, item.applicable_count)
                for item in self.profile.required_columns
            )
            if rate is not None:
                out["DQ1"].append(
                    self._evidence(
                        "SQL-DQ1-REQUIRED",
                        EvidenceType.RULE,
                        "必填与条件必填规则执行",
                        self._score_from_rate(rate),
                        coverage=1.0,
                        authority=0.95,
                        business_fit=1.0,
                        description=f"共评价{applicable}个适用单元，缺失率{rate:.4%}。",
                        basis="required_columns",
                    )
                )
        elif self.profile.columns:
            rate, applicable = self._weighted_rate(
                (item.missing_count, item.observed_rows) for item in self.profile.columns
            )
            if rate is not None:
                avg_coverage = self._mean(item.coverage for item in self.profile.columns) or 0.0
                out["DQ1"].append(
                    self._evidence(
                        "SQL-DQ1-GENERIC",
                        EvidenceType.DATA,
                        "通用字段空值与空字符串剖析",
                        self._score_from_rate(rate),
                        coverage=avg_coverage,
                        authority=0.95,
                        business_fit=0.45,
                        unknown=0.25,
                        description=(
                            f"缺少业务必填口径，按全部已剖析字段计算通用缺失率{rate:.4%}；"
                            "该结果仅用于初评。"
                        ),
                    )
                )

        # DQ2、DQ3、DQ5允许由自定义规则提供；DQ3额外吸收代码值域规则。
        for indicator_id in ("DQ2", "DQ3", "DQ5"):
            items = [item for item in self.profile.custom_rules if item.indicator_id == indicator_id]
            rate, applicable = self._weighted_rate(
                (item.invalid_count, item.applicable_count) for item in items
            )
            if rate is not None:
                out[indicator_id].append(
                    self._evidence(
                        f"SQL-{indicator_id}-CUSTOM",
                        EvidenceType.RULE,
                        "自定义业务SQL规则",
                        self._score_from_rate(rate),
                        coverage=1.0,
                        authority=0.95,
                        business_fit=1.0,
                        description=f"执行{len(items)}项规则，违规率{rate:.4%}。",
                        basis=",".join(item.rule_id for item in items),
                    )
                )
        domain_rate, domain_n = self._weighted_rate(
            (item.invalid_count, item.applicable_count) for item in self.profile.domains
        )
        if domain_rate is not None:
            out["DQ3"].append(
                self._evidence(
                    "SQL-DQ3-DOMAIN",
                    EvidenceType.RULE,
                    "标准代码集和值域规则",
                    self._score_from_rate(domain_rate),
                    coverage=1.0,
                    authority=0.95,
                    business_fit=1.0,
                    description=f"评价{domain_n}个适用值，非法值率{domain_rate:.4%}。",
                )
            )

        master_issue_rate, master_n = self._weighted_rate(
            (item.issue_count, item.applicable_count)
            for item in self.profile.master_data_consistency
        )
        if master_issue_rate is not None:
            mismatch_rate, mismatch_n = self._weighted_rate(
                (item.mismatch_count, item.applicable_count)
                for item in self.profile.master_data_consistency
            )
            # 同一组权威值比对同时支持“准确性”和“跨表一致性”：
            # DQ2回答业务快照是否与权威值相符，DQ5回答不同存储位置是否一致。
            for indicator_id, evidence_id, source in (
                ("DQ2", "SQL-DQ2-AUTHORITATIVE-MATCH", "业务快照与权威主数据准确性比对"),
                ("DQ5", "SQL-DQ5-MASTER-CONSISTENCY", "权威主数据与业务复制属性一致性"),
            ):
                out[indicator_id].append(
                    self._evidence(
                        evidence_id,
                        EvidenceType.RULE,
                        source,
                        self._score_from_rate(mismatch_rate or 0.0),
                        coverage=1.0,
                        authority=0.97,
                        business_fit=1.0,
                        description=(
                            f"评价{mismatch_n}条主数据引用，复制属性不一致率"
                            f"{0.0 if mismatch_rate is None else mismatch_rate:.4%}。"
                        ),
                    )
                )

        # DQ4：业务键重复优先；无业务键配置时仅以主键覆盖率作为低适配度结构证据。
        duplicate_rate, duplicate_n = self._weighted_rate(
            (item.duplicate_rows, item.applicable_count) for item in self.profile.business_keys
        )
        if duplicate_rate is not None:
            out["DQ4"].append(
                self._evidence(
                    "SQL-DQ4-BUSINESS-KEY",
                    EvidenceType.DATA,
                    "业务唯一键重复检测",
                    self._score_from_rate(duplicate_rate),
                    coverage=1.0,
                    authority=0.98,
                    business_fit=1.0,
                    description=f"评价{duplicate_n}条业务对象，重复记录率{duplicate_rate:.4%}。",
                )
            )
        elif self.metadata.tables:
            pk_rate = sum(table.primary_key is not None for table in self.metadata.tables) / len(
                self.metadata.tables
            )
            out["DQ4"].append(
                self._evidence(
                    "SQL-DQ4-PK-PROXY",
                    EvidenceType.STRUCTURE,
                    "主键覆盖率代理证据",
                    100.0 * pk_rate,
                    coverage=1.0,
                    authority=0.98,
                    business_fit=0.45,
                    unknown=0.35,
                    description="未配置业务唯一键，使用主键覆盖率作为弱代理，不能替代业务唯一性检测。",
                )
            )

        # DQ6：以“预期业务关系”作为首选检测入口。关系可由物理外键或
        # 经验证的替代控制实现，数据完整性检测不依赖物理外键是否存在。
        if self.profile.relationship_controls:
            relationship_orphan_rate, relationship_orphan_n = self._weighted_rate(
                (item.orphan_count, item.applicable_count)
                for item in self.profile.relationship_controls
            )
            if relationship_orphan_rate is not None:
                no_fk_n = sum(
                    not item.physical_fk_trusted for item in self.profile.relationship_controls
                )
                out["DQ6"].append(
                    self._evidence(
                        "SQL-DQ6-RELATIONSHIP-CONTROL",
                        EvidenceType.RULE,
                        "预期业务关系孤儿记录检测",
                        self._score_from_rate(relationship_orphan_rate),
                        coverage=1.0,
                        authority=0.98,
                        business_fit=1.0,
                        description=(
                            f"评价{relationship_orphan_n}条预期关系记录，孤儿率"
                            f"{relationship_orphan_rate:.4%}；其中{no_fk_n}条关系未使用"
                            "可信物理外键，但仍通过登记关系持续检测。"
                        ),
                        basis="relationship_controls",
                    )
                )
        else:
            orphan_rate, orphan_n = self._weighted_rate(
                (item.orphan_count, item.applicable_count) for item in self.profile.foreign_keys
            )
            if orphan_rate is not None:
                out["DQ6"].append(
                    self._evidence(
                        "SQL-DQ6-FK",
                        EvidenceType.DATA,
                        "已声明外键孤儿记录检测",
                        self._score_from_rate(orphan_rate),
                        coverage=1.0,
                        authority=0.98,
                        business_fit=0.9,
                        description=f"评价{orphan_n}条可关联记录，孤儿率{orphan_rate:.4%}。",
                        unknown=0.05,
                    )
                )

            logical_orphan_rate, logical_orphan_n = self._weighted_rate(
                (item.orphan_count, item.applicable_count)
                for item in self.profile.logical_foreign_keys
            )
            if logical_orphan_rate is not None:
                out["DQ6"].append(
                    self._evidence(
                        "SQL-DQ6-LOGICAL-FK",
                        EvidenceType.RULE,
                        "逻辑关系孤儿记录检测",
                        self._score_from_rate(logical_orphan_rate),
                        coverage=1.0,
                        authority=0.97,
                        business_fit=1.0,
                        description=(
                            f"评价{logical_orphan_n}条逻辑关联记录，孤儿率"
                            f"{logical_orphan_rate:.4%}；检测不依赖物理外键存在。"
                        ),
                    )
                )
        master_orphan_rate, master_orphan_n = self._weighted_rate(
            (item.orphan_count, item.applicable_count)
            for item in self.profile.master_data_consistency
        )
        if master_orphan_rate is not None:
            out["DQ6"].append(
                self._evidence(
                    "SQL-DQ6-MASTER-REFERENCE",
                    EvidenceType.RULE,
                    "主数据权威引用完整性",
                    self._score_from_rate(master_orphan_rate),
                    coverage=1.0,
                    authority=0.97,
                    business_fit=1.0,
                    description=f"评价{master_orphan_n}条主数据引用，孤儿率{master_orphan_rate:.4%}。",
                )
            )

        # DQ7：配置的时效性规则。
        stale_rate, stale_n = self._weighted_rate(
            (item.stale_count, item.applicable_count) for item in self.profile.freshness
        )
        if stale_rate is not None:
            out["DQ7"].append(
                self._evidence(
                    "SQL-DQ7-FRESHNESS",
                    EvidenceType.RULE,
                    "数据更新时间阈值规则",
                    self._score_from_rate(stale_rate),
                    coverage=1.0,
                    authority=0.95,
                    business_fit=1.0,
                    description=f"评价{stale_n}条时间记录，超期率{stale_rate:.4%}。",
                )
            )

        # DQ8：审计字段/系统版本表是可追溯性的结构代理；同时检查审计字段缺失。
        audit_names = {name.lower() for name in self.scan.audit_column_aliases}
        tables_with_audit = 0
        audit_profiles = []
        column_profile_map = {
            (item.table, item.column): item for item in self.profile.columns
        }
        for table in self.metadata.tables:
            audit_columns = [
                column for column in table.columns if column.name.lower() in audit_names
            ]
            if audit_columns or table.temporal_type > 0:
                tables_with_audit += 1
            for column in audit_columns:
                profile = column_profile_map.get((table.qualified_name, column.name))
                if profile:
                    audit_profiles.append(profile)
        if self.metadata.tables:
            trace_structure = tables_with_audit / len(self.metadata.tables)
            out["DQ8"].append(
                self._evidence(
                    "SQL-DQ8-AUDIT-STRUCTURE",
                    EvidenceType.STRUCTURE,
                    "审计字段与系统版本表覆盖",
                    100.0 * trace_structure,
                    coverage=1.0,
                    authority=0.98,
                    business_fit=0.75,
                    unknown=0.15,
                    description=f"具有审计字段或系统版本能力的表占比{trace_structure:.2%}。",
                )
            )
        audit_rate, audit_n = self._weighted_rate(
            (item.missing_count, item.observed_rows) for item in audit_profiles
        )
        if audit_rate is not None:
            out["DQ8"].append(
                self._evidence(
                    "SQL-DQ8-AUDIT-DATA",
                    EvidenceType.DATA,
                    "审计字段完整性检测",
                    self._score_from_rate(audit_rate),
                    coverage=self._mean(item.coverage for item in audit_profiles) or 0.0,
                    authority=0.95,
                    business_fit=0.85,
                    description=f"评价{audit_n}个审计字段单元，缺失率{audit_rate:.4%}。",
                )
            )

    def _build_sg_evidence(
        self,
        out: dict[str, list[Evidence]],
        redundancy_results: list[RedundancyAssessment],
    ) -> None:
        tables = list(self.metadata.tables)
        columns = [column for table in tables for column in table.columns]
        if columns:
            description_rate = sum(bool(column.description) for column in columns) / len(columns)
            naming_rate = sum(self._valid_column_name(column.name) for column in columns) / len(columns)
            max_type_rate = sum(
                column.data_type.lower() in {"varchar", "nvarchar", "varbinary"}
                and column.max_length == -1
                for column in columns
            ) / len(columns)
            score = 100.0 * (
                0.45 * description_rate + 0.35 * naming_rate + 0.20 * (1.0 - max_type_rate)
            )
            out["SG1"].append(
                self._evidence(
                    "SQL-SG1-COLUMNS",
                    EvidenceType.STRUCTURE,
                    "字段定义、命名和大字段类型审查",
                    score,
                    coverage=1.0,
                    authority=0.98,
                    business_fit=0.75,
                    unknown=0.10,
                    description=(
                        f"字段说明覆盖率{description_rate:.2%}，命名基本符合率{naming_rate:.2%}，"
                        f"MAX大字段比例{max_type_rate:.2%}。"
                    ),
                )
            )

        if tables:
            if self.rules.table_model_rules:
                scores: list[float] = []
                grain_ok_n = repeating_n = 0
                business_keys = {
                    (item.table, frozenset(item.columns)) for item in self.rules.business_keys
                }
                for rule in self.rules.table_model_rules:
                    table = self.table_map.get(rule.table)
                    if table is None:
                        scores.append(0.0)
                        continue
                    key_sets = []
                    if table.primary_key is not None:
                        key_sets.append(frozenset(table.primary_key.columns))
                    key_sets.extend(frozenset(item.columns) for item in table.unique_constraints)
                    grain = frozenset(rule.grain_columns)
                    grain_ok = not grain or grain in key_sets or (rule.table, grain) in business_keys
                    grain_ok_n += int(grain_ok)
                    bases: dict[str, int] = {}
                    for column in table.columns:
                        match = re.match(r"(.+?)[_]?\d+$", column.name.lower())
                        if match:
                            bases[match.group(1)] = bases.get(match.group(1), 0) + 1
                    repeating = any(count >= 2 for count in bases.values())
                    configured_multivalue = any(
                        column in {item.name for item in table.columns}
                        for column in rule.forbidden_multivalue_columns
                    )
                    repeating = repeating or configured_multivalue
                    repeating_n += int(repeating)
                    components = [
                        1.0 if grain_ok else 0.0,
                        1.0 if (not rule.require_description or bool(table.description)) else 0.0,
                        1.0 if len(table.columns) <= rule.max_columns else 0.0,
                        1.0 if (rule.allow_heap or not table.is_heap) else 0.0,
                        0.0 if repeating else 1.0,
                    ]
                    scores.append(
                        100.0
                        * sum(
                            w * x
                            for w, x in zip(
                                (0.40, 0.20, 0.15, 0.10, 0.15),
                                components,
                                strict=True,
                            )
                        )
                    )
                score = self._mean(scores) or 0.0
                total_rules = len(self.rules.table_model_rules)
                out["SG2"].append(
                    self._evidence(
                        "SQL-SG2-MODEL-RULES",
                        EvidenceType.RULE,
                        "表职责与记录粒度显式规则核验",
                        score,
                        coverage=1.0,
                        authority=0.96,
                        business_fit=1.0,
                        description=(
                            f"核验{total_rules}张业务表，记录粒度键满足{grain_ok_n}张，"
                            f"发现疑似重复组字段{repeating_n}张。"
                        ),
                    )
                )
            else:
                table_description = sum(bool(table.description) for table in tables) / len(tables)
                wide_rate = sum(len(table.columns) > 50 for table in tables) / len(tables)
                heap_rate = sum(table.is_heap for table in tables) / len(tables)
                score = 100.0 * (
                    0.50 * table_description + 0.30 * (1.0 - wide_rate) + 0.20 * (1.0 - heap_rate)
                )
                out["SG2"].append(
                    self._evidence(
                        "SQL-SG2-TABLES",
                        EvidenceType.STRUCTURE,
                        "表职责说明、宽表和堆表初筛",
                        score,
                        coverage=1.0,
                        authority=0.98,
                        business_fit=0.55,
                        unknown=0.25,
                        description=(
                            f"表说明覆盖率{table_description:.2%}，宽表比例{wide_rate:.2%}，"
                            f"堆表比例{heap_rate:.2%}；未配置记录粒度规则，结果仅作初筛。"
                        ),
                    )
                )

            pk_rate = sum(table.primary_key is not None for table in tables) / len(tables)
            checks = [check for table in tables for check in table.checks]
            trusted_check = (
                sum(not item.is_disabled and not item.is_not_trusted for item in checks) / len(checks)
                if checks
                else 0.5
            )
            unique_rate = sum(bool(table.unique_constraints) for table in tables) / len(tables)
            foundational_score = 100.0 * (
                0.45 * pk_rate + 0.25 * trusted_check + 0.30 * unique_rate
            )
            out["SG3"].append(
                self._evidence(
                    "SQL-SG3-FOUNDATIONAL-CONSTRAINTS",
                    EvidenceType.STRUCTURE,
                    "主键、唯一约束和检查约束审查",
                    foundational_score,
                    coverage=1.0,
                    authority=0.99,
                    business_fit=0.90,
                    description=(
                        f"主键覆盖率{pk_rate:.2%}，可信检查约束率{trusted_check:.2%}，"
                        f"唯一约束表覆盖率{unique_rate:.2%}。"
                    ),
                )
            )

            if self.profile.relationship_controls:
                weight_sum = sum(item.criticality_weight for item in self.profile.relationship_controls)
                control_effectiveness = (
                    sum(
                        item.control_score * item.criticality_weight
                        for item in self.profile.relationship_controls
                    )
                    / weight_sum
                    if weight_sum
                    else 0.0
                )
                physical_n = sum(
                    item.physical_fk_trusted for item in self.profile.relationship_controls
                )
                alternative_n = len(self.profile.relationship_controls) - physical_n
                out["SG3"].append(
                    self._evidence(
                        "SQL-SG3-RELATIONSHIP-CONTROL",
                        EvidenceType.RULE,
                        "预期关系完整性控制有效性",
                        100.0 * control_effectiveness,
                        coverage=1.0,
                        authority=0.97,
                        business_fit=1.0,
                        description=(
                            f"评价{len(self.profile.relationship_controls)}条预期业务关系："
                            f"{physical_n}条由可信物理外键控制，{alternative_n}条由应用、"
                            "存储过程、ETL门禁、消息校验或审计等替代机制控制；"
                            f"重要度加权控制有效度{control_effectiveness:.2%}。"
                        ),
                        basis="relationship_controls",
                    )
                )

                semantic_clarity = (
                    sum(
                        item.semantic_score * item.criticality_weight
                        for item in self.profile.relationship_controls
                    )
                    / weight_sum
                    if weight_sum
                    else 0.0
                )
                approved_exception_n = sum(
                    (not item.physical_fk_trusted)
                    and item.exception_governance_score >= 0.8
                    for item in self.profile.relationship_controls
                )
                out["SG4"].append(
                    self._evidence(
                        "SQL-SG4-RELATIONSHIP-SEMANTICS",
                        EvidenceType.RULE,
                        "预期关系表达、责任与受控例外",
                        100.0 * semantic_clarity,
                        coverage=1.0,
                        authority=0.96,
                        business_fit=1.0,
                        description=(
                            f"预期关系语义与治理信息加权完整度{semantic_clarity:.2%}；"
                            f"未使用可信物理外键且受控例外证据充分的关系{approved_exception_n}条。"
                        ),
                        basis="relationship_controls",
                    )
                )
            else:
                # 未配置预期关系清单时，物理外键只能作为弱代理；数据库没有外键
                # 不再直接记为零分，以避免误罚无关系表或采用替代控制的系统。
                trusted_fk = (
                    sum(not fk.is_disabled and not fk.is_not_trusted for fk in self.metadata.foreign_keys)
                    / len(self.metadata.foreign_keys)
                    if self.metadata.foreign_keys
                    else 0.70
                )
                out["SG3"].append(
                    self._evidence(
                        "SQL-SG3-PHYSICAL-FK-PROXY",
                        EvidenceType.STRUCTURE,
                        "物理外键可信状态弱代理",
                        100.0 * trusted_fk,
                        coverage=1.0,
                        authority=0.95,
                        business_fit=0.45,
                        unknown=0.35,
                        description=(
                            f"可信物理外键率{trusted_fk:.2%}；未配置预期关系与替代控制清单，"
                            "该结果不能直接判定关系控制质量。"
                        ),
                    )
                )
                related_tables = (
                    {fk.parent_qualified_name for fk in self.metadata.foreign_keys}
                    | {fk.referenced_qualified_name for fk in self.metadata.foreign_keys}
                    | {item.child_table for item in self.profile.logical_foreign_keys}
                    | {item.parent_table for item in self.profile.logical_foreign_keys}
                )
                relation_coverage = len(related_tables) / len(tables)
                out["SG4"].append(
                    self._evidence(
                        "SQL-SG4-RELATION-PROXY",
                        EvidenceType.STRUCTURE,
                        "物理或逻辑关系涉及表覆盖弱代理",
                        100.0 * relation_coverage,
                        coverage=1.0,
                        authority=0.90,
                        business_fit=0.45,
                        unknown=0.35,
                        description=(
                            f"物理或逻辑关系涉及表覆盖率{relation_coverage:.2%}；"
                            "未配置预期关系语义、责任和控制方式，仅作初筛。"
                        ),
                    )
                )

        field_risks = [item.risk_index for item in redundancy_results if item.object_type == "field"]
        table_risks = [item.risk_index for item in redundancy_results if item.object_type == "table"]
        if self.scan.detect_field_redundancy:
            risk = max(field_risks, default=0.0)
            out["SG5"].append(
                self._evidence(
                    "SQL-SG5-REDUNDANCY",
                    EvidenceType.STRUCTURE,
                    "字段冗余候选风险",
                    self._score_from_rate(risk),
                    coverage=1.0,
                    authority=0.8,
                    business_fit=0.55,
                    unknown=0.30,
                    description=f"识别{len(field_risks)}组字段候选，最高风险指数{risk:.3f}。",
                )
            )
        if self.scan.detect_table_redundancy:
            risk = max(table_risks, default=0.0)
            out["SG6"].append(
                self._evidence(
                    "SQL-SG6-REDUNDANCY",
                    EvidenceType.STRUCTURE,
                    "表冗余候选风险",
                    self._score_from_rate(risk),
                    coverage=1.0,
                    authority=0.8,
                    business_fit=0.55,
                    unknown=0.30,
                    description=f"识别{len(table_risks)}组表候选，最高风险指数{risk:.3f}。",
                )
            )

        # SG7必须基于主数据权威配置，避免自动猜测权威来源。
        if self.rules.master_data_groups:
            valid_groups = 0
            duplicate_authorities = 0
            for group in self.rules.master_data_groups:
                authority_exists = group.authoritative_table in self.table_map
                related_exist = all(table in self.table_map for table in group.related_tables)
                valid_groups += int(authority_exists and related_exist)
                duplicate_authorities += int(
                    group.authoritative_table in set(group.related_tables)
                )
            total = len(self.rules.master_data_groups)
            score = 100.0 * max(0.0, (valid_groups - duplicate_authorities) / total)
            out["SG7"].append(
                self._evidence(
                    "SQL-SG7-MASTER",
                    EvidenceType.RULE,
                    "主数据权威来源配置核验",
                    score,
                    coverage=1.0,
                    authority=0.95,
                    business_fit=1.0,
                    description=f"核验{total}类主数据对象，完整有效配置{valid_groups}类。",
                )
            )

        master_rate, master_count = self._weighted_rate(
            (item.issue_count, item.applicable_count)
            for item in self.profile.master_data_consistency
        )
        if master_rate is not None:
            out["SG7"].append(
                self._evidence(
                    "SQL-SG7-MASTER-CONSISTENCY",
                    EvidenceType.RULE,
                    "主数据单一权威与复制属性冲突检测",
                    self._score_from_rate(master_rate),
                    coverage=1.0,
                    authority=0.97,
                    business_fit=1.0,
                    description=f"评价{master_count}条主数据引用，权威性或复制属性问题率{master_rate:.4%}。",
                )
            )

        if tables:
            if self.rules.lifecycle_control_rules:
                scores: list[float] = []
                for rule in self.rules.lifecycle_control_rules:
                    table = self.table_map.get(rule.table)
                    if table is None:
                        scores.append(0.0)
                        continue
                    names = {column.name for column in table.columns}
                    audit_rate = (
                        sum(column in names for column in rule.required_audit_columns)
                        / len(rule.required_audit_columns)
                        if rule.required_audit_columns else 1.0
                    )
                    interop_rate = (
                        sum(column in names for column in rule.interoperability_columns)
                        / len(rule.interoperability_columns)
                        if rule.interoperability_columns else 1.0
                    )
                    temporal_ok = 1.0 if (not rule.require_temporal or table.temporal_type > 0) else 0.0
                    description_ok = 1.0 if (not rule.require_description or bool(table.description)) else 0.0
                    scores.append(100.0 * (0.35 * audit_rate + 0.30 * interop_rate + 0.20 * temporal_ok + 0.15 * description_ok))
                score = self._mean(scores) or 0.0
                out["SG8"].append(
                    self._evidence(
                        "SQL-SG8-CONTROL-RULES",
                        EvidenceType.RULE,
                        "结构生命周期与互操作控制规则",
                        score,
                        coverage=1.0,
                        authority=0.96,
                        business_fit=1.0,
                        description=f"核验{len(self.rules.lifecycle_control_rules)}张表的审计、版本与互操作字段要求。",
                    )
                )
            else:
                audit_names = {item.lower() for item in self.scan.audit_column_aliases}
                lifecycle_rate = sum(
                    table.temporal_type > 0
                    or any(column.name.lower() in audit_names for column in table.columns)
                    for table in tables
                ) / len(tables)
                metadata_rate = (
                    sum(bool(table.description) for table in tables)
                    + sum(bool(column.description) for column in columns)
                ) / max(1, len(tables) + len(columns))
                score = 100.0 * (0.55 * lifecycle_rate + 0.45 * metadata_rate)
                out["SG8"].append(
                    self._evidence(
                        "SQL-SG8-LIFECYCLE",
                        EvidenceType.STRUCTURE,
                        "结构生命周期、审计与元数据覆盖",
                        score,
                        coverage=1.0,
                        authority=0.98,
                        business_fit=0.70,
                        unknown=0.20,
                        description=(
                            f"审计或系统版本能力覆盖率{lifecycle_rate:.2%}，"
                            f"表字段说明综合覆盖率{metadata_rate:.2%}；未配置显式生命周期要求。"
                        ),
                    )
                )

    @staticmethod
    def _valid_column_name(name: str) -> bool:
        return not bool(re.search(r"\s", name)) and not name.startswith("_") and len(name) <= 128

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", name).lower()

    @staticmethod
    def _token_similarity(left: str | None, right: str | None) -> float:
        if not left or not right:
            return 0.0
        left_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", left.lower()))
        right_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", right.lower()))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    @staticmethod
    def _type_compatibility(left: ColumnMetadata, right: ColumnMetadata) -> float:
        if left.data_type.lower() == right.data_type.lower():
            return 1.0
        text = {"char", "nchar", "varchar", "nvarchar", "text", "ntext"}
        numeric = {
            "tinyint", "smallint", "int", "bigint", "decimal", "numeric", "money",
            "smallmoney", "float", "real",
        }
        date = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"}
        for group in (text, numeric, date):
            if left.data_type.lower() in group and right.data_type.lower() in group:
                return 0.75
        return 0.1

    def build_redundancy_results(self) -> list[RedundancyAssessment]:
        results: list[RedundancyAssessment] = []
        if self.scan.detect_field_redundancy:
            results.extend(self._field_redundancy_candidates())
        if self.scan.detect_table_redundancy:
            results.extend(self._table_redundancy_candidates())
        return sorted(results, key=lambda item: item.risk_index, reverse=True)[
            : self.scan.max_redundancy_pairs
        ]

    def _field_redundancy_candidates(self) -> list[RedundancyAssessment]:
        columns = [column for table in self.metadata.tables for column in table.columns]
        profile_map = {(item.table, item.column): item for item in self.profile.columns}
        fk_pairs = {
            frozenset((fk.parent_qualified_name, fk.referenced_qualified_name))
            for fk in self.metadata.foreign_keys
        }
        results: list[RedundancyAssessment] = []
        for left, right in combinations(columns, 2):
            if left.schema == right.schema and left.table == right.table:
                continue
            name_similarity = SequenceMatcher(
                None, self._normalize_name(left.name), self._normalize_name(right.name)
            ).ratio()
            definition_similarity = self._token_similarity(left.description, right.description)
            if max(name_similarity, definition_similarity) < 0.72:
                continue
            type_compat = self._type_compatibility(left, right)
            left_profile = profile_map.get((f"{left.schema}.{left.table}", left.name))
            right_profile = profile_map.get((f"{right.schema}.{right.table}", right.name))
            value_overlap = 0.5  # 未抽取原始值时保守保留未知信息。
            conflict = 0.2
            if left_profile and right_profile:
                conflict = min(
                    1.0,
                    abs(left_profile.missing_rate - right_profile.missing_rate)
                    + self._distinct_ratio_difference(left_profile, right_profile),
                )
            context_similarity = SequenceMatcher(
                None,
                self._normalize_name(left.table),
                self._normalize_name(right.table),
            ).ratio()
            related = frozenset(
                (f"{left.schema}.{left.table}", f"{right.schema}.{right.table}")
            ) in fk_pairs
            necessity = 0.70 if related else 0.30
            sync_control = 0.65 if related else 0.20
            impact = 0.80 if re.search(r"(id|code|编码|编号|名称|name)$", left.name, re.I) else 0.50
            assessment = self.redundancy_analyzer.assess_field(
                left_object=left.qualified_name,
                right_object=right.qualified_name,
                features=(
                    name_similarity,
                    definition_similarity,
                    type_compat,
                    value_overlap,
                    0.0,
                    context_similarity,
                ),
                necessity=necessity,
                conflict=conflict,
                update_independence=0.80,
                sync_control=sync_control,
                impact=impact,
                evidence_ids=(f"META:{left.qualified_name}", f"META:{right.qualified_name}"),
            )
            if assessment.similarity >= 0.55:
                results.append(assessment)
        return results

    @staticmethod
    def _distinct_ratio_difference(left, right) -> float:
        if left.distinct_count is None or right.distinct_count is None:
            return 0.0
        left_ratio = left.distinct_count / max(1, left.observed_rows)
        right_ratio = right.distinct_count / max(1, right.observed_rows)
        return abs(left_ratio - right_ratio)

    def _table_redundancy_candidates(self) -> list[RedundancyAssessment]:
        results: list[RedundancyAssessment] = []
        fk_pairs = {
            frozenset((fk.parent_qualified_name, fk.referenced_qualified_name))
            for fk in self.metadata.foreign_keys
        }
        for left, right in combinations(self.metadata.tables, 2):
            left_fields = {self._normalize_name(item.name) for item in left.columns}
            right_fields = {self._normalize_name(item.name) for item in right.columns}
            if not left_fields or not right_fields:
                continue
            field_jaccard = len(left_fields & right_fields) / len(left_fields | right_fields)
            if field_jaccard < 0.55:
                continue
            left_pk = set(left.primary_key.columns if left.primary_key else ())
            right_pk = set(right.primary_key.columns if right.primary_key else ())
            pk_similarity = (
                len(left_pk & right_pk) / len(left_pk | right_pk)
                if left_pk or right_pk
                else 0.0
            )
            name_similarity = SequenceMatcher(
                None, self._normalize_name(left.name), self._normalize_name(right.name)
            ).ratio()
            related = frozenset((left.qualified_name, right.qualified_name)) in fk_pairs
            row_ratio = min(left.row_count, right.row_count) / max(1, max(left.row_count, right.row_count))
            necessity = 0.80 if related else 0.25
            sync_control = 0.70 if related else 0.20
            conflict = 1.0 - row_ratio
            assessment = self.redundancy_analyzer.assess_table(
                left_object=left.qualified_name,
                right_object=right.qualified_name,
                features=(
                    field_jaccard,
                    pk_similarity,
                    0.50,
                    name_similarity,
                    0.75 if related else 0.10,
                    0.50,
                ),
                necessity=necessity,
                conflict=conflict,
                update_independence=0.80,
                sync_control=sync_control,
                impact=0.70,
                evidence_ids=(f"META:{left.qualified_name}", f"META:{right.qualified_name}"),
            )
            if assessment.similarity >= 0.55:
                results.append(assessment)
        return results

    def build_bottom_line_triggers(self) -> list[BottomLineTrigger]:
        triggers: list[BottomLineTrigger] = []
        critical = set(self.rules.critical_tables)
        for table_name in critical:
            table = self.table_map.get(table_name)
            if table and table.primary_key is None:
                triggers.append(
                    BottomLineTrigger(
                        rule_id=f"BL-NO-PK-{table_name}",
                        description=f"关键业务表{table_name}缺少主键。",
                        cap=50.0,
                        severity_level=1,
                        target_object=table_name,
                        evidence_ids=(f"META:{table_name}",),
                    )
                )
        for item in self.profile.required_columns:
            if item.bottom_line and item.missing_count > 0:
                triggers.append(
                    BottomLineTrigger(
                        rule_id=f"BL-REQUIRED-{item.table}-{item.column}",
                        description=f"底线必填字段{item.table}.{item.column}存在缺失。",
                        cap=50.0,
                        severity_level=1,
                        target_object=f"{item.table}.{item.column}",
                        evidence_ids=("SQL-DQ1-REQUIRED",),
                    )
                )
        for item in self.profile.business_keys:
            threshold = item.bottom_line_threshold
            if threshold is not None and item.duplicate_rate > threshold:
                triggers.append(
                    BottomLineTrigger(
                        rule_id=f"BL-UNIQUE-{item.table}-{'-'.join(item.columns)}",
                        description=(
                            f"业务键{item.table}({','.join(item.columns)})重复率"
                            f"{item.duplicate_rate:.4%}超过阈值{threshold:.4%}。"
                        ),
                        cap=50.0,
                        severity_level=1,
                        target_object=item.table,
                        evidence_ids=("SQL-DQ4-BUSINESS-KEY",),
                    )
                )
        for item in self.profile.relationship_controls:
            control_failed = item.control_score < item.minimum_control_score
            orphan_failed = item.orphan_rate > item.maximum_orphan_rate
            if item.criticality not in {"high", "critical"}:
                continue
            if not (control_failed or orphan_failed):
                continue
            cap = item.bottom_line_cap
            if cap is None:
                cap = 50.0 if item.criticality == "critical" else 70.0
            reasons = []
            if control_failed:
                reasons.append(
                    f"控制有效度{item.control_score:.2%}低于阈值{item.minimum_control_score:.2%}"
                )
            if orphan_failed:
                reasons.append(
                    f"孤儿率{item.orphan_rate:.4%}超过阈值{item.maximum_orphan_rate:.4%}"
                )
            triggers.append(
                BottomLineTrigger(
                    rule_id=f"BL-RELATIONSHIP-CONTROL-{item.relationship_id}",
                    description=(
                        f"关键业务关系{item.relationship_id}的关系完整性控制不足："
                        + "；".join(reasons)
                        + "。"
                    ),
                    cap=cap,
                    severity_level=1 if item.criticality == "critical" else 2,
                    target_object=item.child_table,
                    evidence_ids=(
                        "SQL-SG3-RELATIONSHIP-CONTROL",
                        "SQL-DQ6-RELATIONSHIP-CONTROL",
                    ),
                )
            )
        # legacy logical_foreign_keys仅在未配置U1.2关系控制清单时保留底线兼容。
        if not self.profile.relationship_controls:
            for item in self.profile.logical_foreign_keys:
                threshold = item.bottom_line_threshold
                if threshold is not None and item.orphan_rate > threshold:
                    triggers.append(
                        BottomLineTrigger(
                            rule_id=f"BL-LOGICAL-FK-{item.rule_id}",
                            description=(
                                f"逻辑关系{item.rule_id}孤儿率{item.orphan_rate:.4%}"
                                f"超过阈值{threshold:.4%}。"
                            ),
                            cap=50.0,
                            severity_level=1,
                            target_object=item.child_table,
                            evidence_ids=("SQL-DQ6-LOGICAL-FK",),
                        )
                    )
        for item in self.profile.master_data_consistency:
            threshold = item.bottom_line_threshold
            if threshold is not None and item.issue_rate > threshold:
                triggers.append(
                    BottomLineTrigger(
                        rule_id=f"BL-MASTER-{item.rule_id}",
                        description=(
                            f"主数据规则{item.rule_id}问题率{item.issue_rate:.4%}"
                            f"超过阈值{threshold:.4%}。"
                        ),
                        cap=50.0,
                        severity_level=1,
                        target_object=item.related_table,
                        evidence_ids=("SQL-SG7-MASTER-CONSISTENCY",),
                    )
                )
        for item in self.profile.custom_rules:
            if item.invalid_count <= 0 or item.bottom_line_cap is None:
                continue
            triggers.append(
                BottomLineTrigger(
                    rule_id=f"BL-CUSTOM-{item.rule_id}",
                    description=f"底线业务规则{item.rule_id}发现{item.invalid_count}条违规。",
                    cap=item.bottom_line_cap,
                    penalty=item.bottom_line_penalty,
                    severity_level=1,
                    target_object=item.table,
                    evidence_ids=(f"RULE:{item.rule_id}",),
                )
            )
        return triggers

    @staticmethod
    def build_coupling_calibrations() -> list[CouplingCalibrationInput]:
        """提供基于数据库机制知识的默认规范耦合关系。

        默认关系只有规范来源，可信度设为0.75；正式研究可叠加德尔菲专家值和
        历史治理数据值进行三源校准。
        """

        mapping = {
            "SG1": {"DQ1": 0.55, "DQ2": 0.50, "DQ3": 0.85},
            "SG2": {"DQ2": 0.45, "DQ5": 0.45},
            "SG3": {"DQ1": 0.80, "DQ2": 0.70, "DQ4": 0.95, "DQ6": 0.95},
            "SG4": {"DQ5": 0.70, "DQ6": 0.90, "DQ8": 0.55},
            "SG5": {"DQ4": 0.45, "DQ5": 0.80},
            "SG6": {"DQ4": 0.55, "DQ5": 0.75},
            "SG7": {"DQ2": 0.60, "DQ4": 0.95, "DQ5": 0.95, "DQ6": 0.50},
            "SG8": {"DQ1": 0.35, "DQ3": 0.55, "DQ7": 0.85, "DQ8": 0.95},
        }
        results: list[CouplingCalibrationInput] = []
        for sg_id, dq_items in mapping.items():
            for dq_id, strength in dq_items.items():
                results.append(
                    CouplingCalibrationInput(
                        dq_indicator_id=dq_id,
                        sg_indicator_id=sg_id,
                        normative_strength=strength,
                        normative_confidence=0.75,
                        evidence_ids=(f"MECHANISM:{sg_id}->{dq_id}",),
                    )
                )
        return results

    def build_governance_templates(
        self, triggers: list[BottomLineTrigger]
    ) -> list[GovernanceTemplate]:
        templates = [
            self._sg_template("SG1", "字段与数据元定义", "字段标准与数据元定义不完整", (
                "完善字段中文含义、数据类型、长度、精度和值域定义",
                "统一字段命名规则并建立数据元目录",
                "清理无业务必要性的MAX大字段",
            ), ("数据标准管理员", "DBA", "业务数据所有者")),
            self._sg_template("SG2", "业务表模型", "表职责、粒度或结构边界不清晰", (
                "明确表职责和记录粒度",
                "评审宽表、堆表及反规范化设计的业务必要性",
                "形成表模型说明和结构评审记录",
            ), ("数据架构师", "DBA", "系统建设单位")),
            self._sg_template("SG3", "键与关系控制", "主键、唯一约束或关系完整性控制不足", (
                "补充主键、业务唯一约束和必要检查约束",
                "恢复被禁用或不可信的约束并验证历史数据",
                "对未建立物理外键的关系登记并验证应用、ETL或审计替代控制",
            ), ("DBA", "系统开发人员", "业务数据所有者")),
            self._sg_template("SG4", "表间关系与血缘", "预期关系语义、责任或受控例外证据不完整", (
                "补充关系基数、空值、删除更新策略和责任主体",
                "为无物理外键设计建立审批、性能证据、复核期限和持续校验",
                "维护数据血缘和接口映射关系",
            ), ("数据架构师", "DBA", "接口负责人")),
            self._sg_template("SG5", "字段冗余", "同义字段或重复属性缺少统一来源和同步控制", (
                "复核高风险字段冗余候选",
                "确定权威字段并合并或停止独立维护重复字段",
                "对合理冗余建立同步与一致性校验",
            ), ("数据标准管理员", "DBA", "业务数据所有者")),
            self._sg_template("SG6", "表冗余", "功能或结构重叠表缺少生命周期和权威边界", (
                "复核高风险相似表及历史、临时、备份表用途",
                "合并无必要的重复业务表或制定退出计划",
                "对保留的快照、归档和交换表标注来源与生命周期",
            ), ("数据架构师", "DBA", "系统运维人员")),
            self._sg_template("SG7", "主数据权威来源", "主数据对象存在多源维护或权威来源不明确", (
                "明确主数据权威表和统一标识",
                "治理历史重复主数据并建立新增审批流程",
                "业务表统一引用主数据标识而非独立维护公共属性",
            ), ("主数据管理员", "业务数据所有者", "DBA")),
            self._sg_template("SG8", "结构生命周期与互操作", "结构变更、审计、说明和共享标准控制不足", (
                "建立表字段变更审批、版本和退出机制",
                "补充审计字段或系统版本能力",
                "提高标准数据元、代码集和接口必需字段覆盖率",
            ), ("数据治理负责人", "DBA", "接口负责人")),
        ]
        for trigger in triggers:
            templates.append(
                GovernanceTemplate(
                    template_id=f"TPL-{trigger.rule_id}",
                    sg_indicator_id=None,
                    bottom_line_rule_id=trigger.rule_id,
                    target_object=trigger.target_object,
                    root_cause=trigger.description,
                    lifecycle_stage="立即整改与复核",
                    measures=(
                        "核查并冻结相关异常数据的继续扩散",
                        "依据底线规则修复历史问题和数据库控制缺陷",
                        "整改后重新执行全量规则并形成验收记录",
                    ),
                    actors=("业务数据所有者", "DBA", "数据治理负责人"),
                    acceptance_metrics={"底线规则违规数": 0, "复评要求": "解除限级条件"},
                    task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
                    severity=1.0,
                    impact=1.0,
                    urgency=1.0,
                    cost=0.6,
                    dependency=0.0,
                )
            )
        return templates

    @staticmethod
    def _sg_template(
        sg_id: str,
        target: str,
        root: str,
        measures: tuple[str, ...],
        actors: tuple[str, ...],
    ) -> GovernanceTemplate:
        return GovernanceTemplate(
            template_id=f"TPL-{sg_id}",
            sg_indicator_id=sg_id,
            bottom_line_rule_id=None,
            target_object=target,
            root_cause=root,
            lifecycle_stage="设计、建设与运维",
            measures=measures,
            actors=actors,
            acceptance_metrics={"关联指标": "达到项目目标阈值", "复评": "EDQSG分值与可信度提升"},
            task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
            severity=0.8,
            impact=0.8,
            urgency=0.75,
            cost=0.6,
            dependency=0.2,
        )

    @staticmethod
    def default_weights() -> tuple[dict[str, float], dict[str, float]]:
        return (
            {f"DQ{i}": 1.0 / 8.0 for i in range(1, 9)},
            {f"SG{i}": 1.0 / 8.0 for i in range(1, 9)},
        )
