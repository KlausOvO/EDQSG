"""SQL Server 数据剖析与质量规则执行。

默认在数据库端执行聚合SQL，不将整表拉取到Python。``sample``模式使用TOP样本，
适用于初评；正式论文结论建议对关键表使用``full``模式并记录扫描快照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .adapter import (
    QueryExecutor,
    qualified_name,
    quote_identifier,
    split_qualified_name,
    validate_sql_condition,
)
from .config import (
    BusinessKeyRule,
    CustomSQLRule,
    DomainRule,
    FreshnessRule,
    LogicalForeignKeyRule,
    MasterDataConsistencyRule,
    RelationshipControlRule,
    RequiredColumnRule,
    SQLServerRuleConfig,
    SQLServerScanConfig,
)
from .metadata import ColumnMetadata, DatabaseMetadata, ForeignKeyMetadata, TableMetadata


CHARACTER_TYPES = {"char", "nchar", "varchar", "nvarchar", "text", "ntext"}
DISTINCT_UNSUPPORTED_TYPES = {
    "text",
    "ntext",
    "image",
    "xml",
    "geography",
    "geometry",
    "hierarchyid",
}
DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"}

RELATIONSHIP_CONTROL_MODE_STRENGTH = {
    "application_validation": 0.82,
    "stored_procedure": 0.88,
    "etl_gate": 0.82,
    "message_validation": 0.78,
    "scheduled_audit": 0.60,
    "manual_reconciliation": 0.35,
    "documentation_only": 0.15,
}

CRITICALITY_WEIGHT = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
    "critical": 2.0,
}


@dataclass(frozen=True)
class ColumnProfile:
    table: str
    column: str
    data_type: str
    total_rows: int
    observed_rows: int
    null_count: int
    blank_count: int
    distinct_count: int | None
    profile_mode: str

    @property
    def missing_count(self) -> int:
        return self.null_count + self.blank_count

    @property
    def missing_rate(self) -> float:
        return 0.0 if self.observed_rows <= 0 else self.missing_count / self.observed_rows

    @property
    def coverage(self) -> float:
        if self.total_rows <= 0:
            return 1.0
        return min(1.0, self.observed_rows / self.total_rows)


@dataclass(frozen=True)
class ForeignKeyProfile:
    foreign_key_name: str
    parent_table: str
    referenced_table: str
    applicable_count: int
    orphan_count: int

    @property
    def orphan_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.orphan_count / self.applicable_count




@dataclass(frozen=True)
class LogicalForeignKeyProfile:
    rule_id: str
    child_table: str
    parent_table: str
    child_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]
    applicable_count: int
    orphan_count: int
    description: str
    bottom_line_threshold: float | None

    @property
    def orphan_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.orphan_count / self.applicable_count


@dataclass(frozen=True)
class RelationshipControlProfile:
    relationship_id: str
    child_table: str
    parent_table: str
    child_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]
    physical_fk_name: str | None
    physical_fk_present: bool
    physical_fk_trusted: bool
    enforcement_modes: tuple[str, ...]
    mechanism_strength: float
    control_score: float
    semantic_score: float
    exception_governance_score: float
    applicable_count: int
    orphan_count: int
    maximum_orphan_rate: float
    minimum_control_score: float
    bottom_line_cap: float | None
    criticality: str
    description: str

    @property
    def orphan_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.orphan_count / self.applicable_count

    @property
    def criticality_weight(self) -> float:
        return CRITICALITY_WEIGHT.get(self.criticality, 1.0)


@dataclass(frozen=True)
class MasterDataConsistencyProfile:
    rule_id: str
    entity_name: str
    authoritative_table: str
    related_table: str
    applicable_count: int
    orphan_count: int
    mismatch_count: int
    description: str
    bottom_line_threshold: float | None

    @property
    def issue_count(self) -> int:
        return self.orphan_count + self.mismatch_count

    @property
    def issue_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.issue_count / self.applicable_count


@dataclass(frozen=True)
class RequiredColumnProfile:
    table: str
    column: str
    applicable_count: int
    missing_count: int
    description: str
    bottom_line: bool

    @property
    def missing_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.missing_count / self.applicable_count


@dataclass(frozen=True)
class BusinessKeyProfile:
    table: str
    columns: tuple[str, ...]
    applicable_count: int
    duplicate_groups: int
    duplicate_rows: int
    description: str
    bottom_line_threshold: float | None

    @property
    def duplicate_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.duplicate_rows / self.applicable_count


@dataclass(frozen=True)
class FreshnessProfile:
    table: str
    column: str
    applicable_count: int
    stale_count: int
    max_value: Any
    max_age_days: int
    description: str

    @property
    def stale_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.stale_count / self.applicable_count


@dataclass(frozen=True)
class DomainProfile:
    table: str
    column: str
    applicable_count: int
    invalid_count: int
    description: str

    @property
    def invalid_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.invalid_count / self.applicable_count


@dataclass(frozen=True)
class CustomRuleProfile:
    rule_id: str
    indicator_id: str
    table: str
    applicable_count: int
    invalid_count: int
    description: str
    bottom_line_cap: float | None
    bottom_line_penalty: float

    @property
    def invalid_rate(self) -> float:
        return 0.0 if self.applicable_count <= 0 else self.invalid_count / self.applicable_count


@dataclass(frozen=True)
class ProfilingIssue:
    object_name: str
    operation: str
    message: str


@dataclass
class DatabaseProfile:
    collected_at: str
    mode: str
    columns: list[ColumnProfile] = field(default_factory=list)
    foreign_keys: list[ForeignKeyProfile] = field(default_factory=list)
    logical_foreign_keys: list[LogicalForeignKeyProfile] = field(default_factory=list)
    relationship_controls: list[RelationshipControlProfile] = field(default_factory=list)
    master_data_consistency: list[MasterDataConsistencyProfile] = field(default_factory=list)
    required_columns: list[RequiredColumnProfile] = field(default_factory=list)
    business_keys: list[BusinessKeyProfile] = field(default_factory=list)
    freshness: list[FreshnessProfile] = field(default_factory=list)
    domains: list[DomainProfile] = field(default_factory=list)
    custom_rules: list[CustomRuleProfile] = field(default_factory=list)
    issues: list[ProfilingIssue] = field(default_factory=list)


class SQLServerProfiler:
    """基于元数据和业务规则执行SQL Server质量剖析。"""

    def __init__(
        self,
        executor: QueryExecutor,
        metadata: DatabaseMetadata,
        scan: SQLServerScanConfig,
        rules: SQLServerRuleConfig,
    ):
        self.executor = executor
        self.metadata = metadata
        self.scan = scan
        self.rules = rules
        self.tables = metadata.table_map()

    def profile(self) -> DatabaseProfile:
        result = DatabaseProfile(
            collected_at=datetime.now(timezone.utc).isoformat(),
            mode=self.scan.profile_mode,
        )
        if self.scan.profile_mode != "metadata":
            self._profile_columns(result)
            self._profile_foreign_keys(result)
            self._profile_logical_foreign_keys(result)
            self._profile_relationship_controls(result)
            self._profile_master_data_consistency(result)
            self._profile_required_columns(result)
            self._profile_business_keys(result)
            self._profile_freshness(result)
            self._profile_domains(result)
            self._profile_custom_rules(result)
        return result

    def _source_sql(self, table: TableMetadata, selected_columns: list[str]) -> str:
        table_name = qualified_name(table.schema, table.name)
        if self.scan.profile_mode == "full":
            return f"{table_name} AS src"
        projected = ", ".join(quote_identifier(column) for column in selected_columns)
        return (
            f"(SELECT TOP ({int(self.scan.sample_rows)}) {projected} "
            f"FROM {table_name}) AS src"
        )

    def _safe(self, result: DatabaseProfile, object_name: str, operation: str, func):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - 需要将单对象错误写入报告而非中止全库
            result.issues.append(
                ProfilingIssue(
                    object_name=object_name,
                    operation=operation,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
            return None

    def _profile_columns(self, result: DatabaseProfile) -> None:
        for table in self.metadata.tables:
            for column in table.columns:
                object_name = column.qualified_name
                profile = self._safe(
                    result,
                    object_name,
                    "column_profile",
                    lambda c=column, t=table: self._column_profile(t, c),
                )
                if profile is not None:
                    result.columns.append(profile)

    def _column_profile(self, table: TableMetadata, column: ColumnMetadata) -> ColumnProfile:
        quoted = quote_identifier(column.name)
        source = self._source_sql(table, [column.name])
        blank_expr = "0"
        if column.data_type.lower() in CHARACTER_TYPES:
            blank_expr = (
                f"SUM(CASE WHEN {quoted} IS NOT NULL "
                f"AND LTRIM(RTRIM(CONVERT(nvarchar(max), {quoted}))) = N'' "
                "THEN 1 ELSE 0 END)"
            )
        distinct_expr = "NULL"
        if column.data_type.lower() not in DISTINCT_UNSUPPORTED_TYPES:
            distinct_expr = f"COUNT_BIG(DISTINCT {quoted})"
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:COLUMN_PROFILE
            SELECT
                COUNT_BIG(*) AS observed_rows,
                SUM(CASE WHEN {quoted} IS NULL THEN 1 ELSE 0 END) AS null_count,
                {blank_expr} AS blank_count,
                {distinct_expr} AS distinct_count
            FROM {source}
            """
        ) or {}
        return ColumnProfile(
            table=table.qualified_name,
            column=column.name,
            data_type=column.data_type,
            total_rows=table.row_count,
            observed_rows=int(row.get("observed_rows") or 0),
            null_count=int(row.get("null_count") or 0),
            blank_count=int(row.get("blank_count") or 0),
            distinct_count=(
                None if row.get("distinct_count") is None else int(row["distinct_count"])
            ),
            profile_mode=self.scan.profile_mode,
        )

    def _profile_foreign_keys(self, result: DatabaseProfile) -> None:
        for fk in self.metadata.foreign_keys:
            profile = self._safe(
                result,
                fk.name,
                "foreign_key_profile",
                lambda item=fk: self._foreign_key_profile(item),
            )
            if profile is not None:
                result.foreign_keys.append(profile)

    def _foreign_key_profile(self, fk: ForeignKeyMetadata) -> ForeignKeyProfile:
        child = qualified_name(fk.parent_schema, fk.parent_table)
        parent = qualified_name(fk.referenced_schema, fk.referenced_table)
        joins = " AND ".join(
            f"c.{quote_identifier(left)} = p.{quote_identifier(right)}"
            for left, right in zip(fk.parent_columns, fk.referenced_columns, strict=True)
        )
        applicable = " AND ".join(
            f"c.{quote_identifier(column)} IS NOT NULL" for column in fk.parent_columns
        )
        first_parent = quote_identifier(fk.referenced_columns[0])
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:FOREIGN_KEY_PROFILE
            SELECT
                COUNT_BIG(*) AS applicable_count,
                SUM(CASE WHEN p.{first_parent} IS NULL THEN 1 ELSE 0 END) AS orphan_count
            FROM {child} AS c
            LEFT JOIN {parent} AS p ON {joins}
            WHERE {applicable}
            """
        ) or {}
        return ForeignKeyProfile(
            foreign_key_name=fk.name,
            parent_table=fk.parent_qualified_name,
            referenced_table=fk.referenced_qualified_name,
            applicable_count=int(row.get("applicable_count") or 0),
            orphan_count=int(row.get("orphan_count") or 0),
        )


    def _profile_logical_foreign_keys(self, result: DatabaseProfile) -> None:
        for rule in self.rules.logical_foreign_keys:
            profile = self._safe(
                result,
                rule.rule_id,
                "logical_foreign_key_rule",
                lambda item=rule: self._logical_foreign_key_profile(item),
            )
            if profile is not None:
                result.logical_foreign_keys.append(profile)

    def _logical_foreign_key_profile(
        self, rule: LogicalForeignKeyRule
    ) -> LogicalForeignKeyProfile:
        child = self._resolve_table(rule.child_table)
        parent = self._resolve_table(rule.parent_table)
        if not rule.child_columns or len(rule.child_columns) != len(rule.parent_columns):
            raise ValueError("逻辑外键子列和父列必须等长且非空。")
        for column in rule.child_columns:
            self._column_exists(child, column)
        for column in rule.parent_columns:
            self._column_exists(parent, column)
        joins = " AND ".join(
            f"c.{quote_identifier(left)} = p.{quote_identifier(right)}"
            for left, right in zip(rule.child_columns, rule.parent_columns, strict=True)
        )
        applicable = " AND ".join(
            f"c.{quote_identifier(column)} IS NOT NULL" for column in rule.child_columns
        )
        first_parent = quote_identifier(rule.parent_columns[0])
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:LOGICAL_FOREIGN_KEY_RULE
            SELECT
                COUNT_BIG(*) AS applicable_count,
                SUM(CASE WHEN p.{first_parent} IS NULL THEN 1 ELSE 0 END) AS orphan_count
            FROM {qualified_name(child.schema, child.name)} AS c
            LEFT JOIN {qualified_name(parent.schema, parent.name)} AS p ON {joins}
            WHERE {applicable}
            """
        ) or {}
        return LogicalForeignKeyProfile(
            rule_id=rule.rule_id,
            child_table=child.qualified_name,
            parent_table=parent.qualified_name,
            child_columns=rule.child_columns,
            parent_columns=rule.parent_columns,
            applicable_count=int(row.get("applicable_count") or 0),
            orphan_count=int(row.get("orphan_count") or 0),
            description=rule.description,
            bottom_line_threshold=rule.bottom_line_threshold,
        )

    def _profile_relationship_controls(self, result: DatabaseProfile) -> None:
        for rule in self.rules.relationship_controls:
            profile = self._safe(
                result,
                rule.relationship_id,
                "relationship_control_rule",
                lambda item=rule: self._relationship_control_profile(item),
            )
            if profile is not None:
                result.relationship_controls.append(profile)

    @staticmethod
    def _name_eq(left: str, right: str) -> bool:
        return left.strip().lower() == right.strip().lower()

    def _matching_physical_fk(
        self, rule: RelationshipControlRule
    ) -> ForeignKeyMetadata | None:
        for fk in self.metadata.foreign_keys:
            if not self._name_eq(fk.parent_qualified_name, rule.child_table):
                continue
            if not self._name_eq(fk.referenced_qualified_name, rule.parent_table):
                continue
            if tuple(item.lower() for item in fk.parent_columns) != tuple(
                item.lower() for item in rule.child_columns
            ):
                continue
            if tuple(item.lower() for item in fk.referenced_columns) != tuple(
                item.lower() for item in rule.parent_columns
            ):
                continue
            return fk
        return None

    @staticmethod
    def _scheduled_audit_strength(hours: float | None) -> float:
        if hours is None:
            return RELATIONSHIP_CONTROL_MODE_STRENGTH["scheduled_audit"]
        if hours <= 1:
            return 0.72
        if hours <= 24:
            return 0.62
        if hours <= 168:
            return 0.48
        return 0.35

    def _relationship_control_profile(
        self, rule: RelationshipControlRule
    ) -> RelationshipControlProfile:
        child = self._resolve_table(rule.child_table)
        parent = self._resolve_table(rule.parent_table)
        if not rule.child_columns or len(rule.child_columns) != len(rule.parent_columns):
            raise ValueError("关系控制子列和父列必须等长且非空。")
        for column in rule.child_columns:
            self._column_exists(child, column)
        for column in rule.parent_columns:
            self._column_exists(parent, column)

        fk = self._matching_physical_fk(rule)
        fk_present = fk is not None
        fk_trusted = bool(fk and not fk.is_disabled and not fk.is_not_trusted)

        strengths: list[float] = []
        if fk_trusted:
            strengths.append(1.0)
        elif fk_present:
            strengths.append(0.30)
        for mode in rule.enforcement_modes:
            if mode == "scheduled_audit":
                strengths.append(self._scheduled_audit_strength(rule.audit_frequency_hours))
            else:
                strengths.append(RELATIONSHIP_CONTROL_MODE_STRENGTH.get(mode, 0.0))
        mechanism_strength = 0.0
        for value in strengths:
            mechanism_strength = 1.0 - (1.0 - mechanism_strength) * (1.0 - value)
        if rule.physical_fk_required and not fk_trusted:
            mechanism_strength = min(mechanism_strength, 0.40)
        control_score = (
            mechanism_strength
            * rule.control_coverage
            * rule.control_reliability
            * rule.operating_effectiveness
        )

        semantic_checks = [
            bool(rule.description.strip()),
            rule.cardinality != "unspecified",
            rule.delete_policy != "unspecified",
            rule.update_policy != "unspecified",
            bool(rule.owner.strip()),
        ]
        semantic_score = 0.20 + 0.16 * sum(semantic_checks)

        if fk_trusted:
            exception_governance_score = 1.0
        else:
            exception_checks = [
                rule.exception_approved,
                bool(rule.exception_reason.strip()),
                bool(rule.performance_evidence_id.strip()),
                bool(rule.owner.strip()),
                bool(rule.review_due_date.strip()),
            ]
            exception_governance_score = sum(exception_checks) / len(exception_checks)
        semantic_score = min(1.0, 0.75 * semantic_score + 0.25 * exception_governance_score)

        joins = " AND ".join(
            f"c.{quote_identifier(left)} = p.{quote_identifier(right)}"
            for left, right in zip(rule.child_columns, rule.parent_columns, strict=True)
        )
        applicable = " AND ".join(
            f"c.{quote_identifier(column)} IS NOT NULL" for column in rule.child_columns
        )
        first_parent = quote_identifier(rule.parent_columns[0])
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:RELATIONSHIP_CONTROL_RULE
            SELECT
                COUNT_BIG(*) AS applicable_count,
                SUM(CASE WHEN p.{first_parent} IS NULL THEN 1 ELSE 0 END) AS orphan_count
            FROM {qualified_name(child.schema, child.name)} AS c
            LEFT JOIN {qualified_name(parent.schema, parent.name)} AS p ON {joins}
            WHERE {applicable}
            """
        ) or {}
        return RelationshipControlProfile(
            relationship_id=rule.relationship_id,
            child_table=child.qualified_name,
            parent_table=parent.qualified_name,
            child_columns=rule.child_columns,
            parent_columns=rule.parent_columns,
            physical_fk_name=None if fk is None else fk.name,
            physical_fk_present=fk_present,
            physical_fk_trusted=fk_trusted,
            enforcement_modes=rule.enforcement_modes,
            mechanism_strength=mechanism_strength,
            control_score=control_score,
            semantic_score=semantic_score,
            exception_governance_score=exception_governance_score,
            applicable_count=int(row.get("applicable_count") or 0),
            orphan_count=int(row.get("orphan_count") or 0),
            maximum_orphan_rate=rule.maximum_orphan_rate,
            minimum_control_score=rule.minimum_control_score,
            bottom_line_cap=rule.bottom_line_cap,
            criticality=rule.criticality,
            description=rule.description,
        )

    def _profile_master_data_consistency(self, result: DatabaseProfile) -> None:
        for rule in self.rules.master_data_consistency_rules:
            profile = self._safe(
                result,
                rule.rule_id,
                "master_data_consistency_rule",
                lambda item=rule: self._master_data_consistency_profile(item),
            )
            if profile is not None:
                result.master_data_consistency.append(profile)

    def _master_data_consistency_profile(
        self, rule: MasterDataConsistencyRule
    ) -> MasterDataConsistencyProfile:
        authority = self._resolve_table(rule.authoritative_table)
        related = self._resolve_table(rule.related_table)
        for authority_col, related_col in rule.key_pairs + rule.attribute_pairs:
            self._column_exists(authority, authority_col)
            self._column_exists(related, related_col)
        joins = " AND ".join(
            f"r.{quote_identifier(related_col)} = a.{quote_identifier(authority_col)}"
            for authority_col, related_col in rule.key_pairs
        )
        applicable = " AND ".join(
            f"r.{quote_identifier(related_col)} IS NOT NULL"
            for _, related_col in rule.key_pairs
        )
        first_authority = quote_identifier(rule.key_pairs[0][0])
        mismatch_terms = []
        for authority_col, related_col in rule.attribute_pairs:
            a = f"a.{quote_identifier(authority_col)}"
            r = f"r.{quote_identifier(related_col)}"
            mismatch_terms.append(
                f"({a} <> {r} OR ({a} IS NULL AND {r} IS NOT NULL) "
                f"OR ({a} IS NOT NULL AND {r} IS NULL))"
            )
        mismatch = " OR ".join(mismatch_terms) if mismatch_terms else "1=0"
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:MASTER_DATA_CONSISTENCY_RULE
            SELECT
                COUNT_BIG(*) AS applicable_count,
                SUM(CASE WHEN a.{first_authority} IS NULL THEN 1 ELSE 0 END) AS orphan_count,
                SUM(CASE WHEN a.{first_authority} IS NOT NULL AND ({mismatch})
                         THEN 1 ELSE 0 END) AS mismatch_count
            FROM {qualified_name(related.schema, related.name)} AS r
            LEFT JOIN {qualified_name(authority.schema, authority.name)} AS a ON {joins}
            WHERE {applicable}
            """
        ) or {}
        return MasterDataConsistencyProfile(
            rule_id=rule.rule_id,
            entity_name=rule.entity_name,
            authoritative_table=authority.qualified_name,
            related_table=related.qualified_name,
            applicable_count=int(row.get("applicable_count") or 0),
            orphan_count=int(row.get("orphan_count") or 0),
            mismatch_count=int(row.get("mismatch_count") or 0),
            description=rule.description,
            bottom_line_threshold=rule.bottom_line_threshold,
        )

    def _resolve_table(self, table_name: str) -> TableMetadata:
        schema, table = split_qualified_name(table_name)
        key = f"{schema}.{table}"
        if key not in self.tables:
            raise ValueError(f"配置引用了未扫描表：{key}。")
        return self.tables[key]

    @staticmethod
    def _column_exists(table: TableMetadata, column: str) -> None:
        if column not in {item.name for item in table.columns}:
            raise ValueError(f"表{table.qualified_name}不存在字段{column}。")

    def _profile_required_columns(self, result: DatabaseProfile) -> None:
        for rule in self.rules.required_columns:
            profile = self._safe(
                result,
                f"{rule.table}.{rule.column}",
                "required_column_rule",
                lambda item=rule: self._required_column_profile(item),
            )
            if profile is not None:
                result.required_columns.append(profile)

    def _required_column_profile(self, rule: RequiredColumnRule) -> RequiredColumnProfile:
        table = self._resolve_table(rule.table)
        self._column_exists(table, rule.column)
        column_meta = next(item for item in table.columns if item.name == rule.column)
        quoted = quote_identifier(rule.column)
        blank = ""
        if column_meta.data_type.lower() in CHARACTER_TYPES:
            blank = f" OR LTRIM(RTRIM(CONVERT(nvarchar(max), {quoted}))) = N''"
        condition = "1=1"
        if rule.condition_sql:
            condition = validate_sql_condition(rule.condition_sql, "condition_sql")
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:REQUIRED_COLUMN_RULE
            SELECT
                SUM(CASE WHEN ({condition}) THEN 1 ELSE 0 END) AS applicable_count,
                SUM(CASE WHEN ({condition}) AND ({quoted} IS NULL{blank}) THEN 1 ELSE 0 END)
                    AS missing_count
            FROM {qualified_name(table.schema, table.name)}
            """
        ) or {}
        return RequiredColumnProfile(
            table=table.qualified_name,
            column=rule.column,
            applicable_count=int(row.get("applicable_count") or 0),
            missing_count=int(row.get("missing_count") or 0),
            description=rule.description,
            bottom_line=rule.bottom_line,
        )

    def _profile_business_keys(self, result: DatabaseProfile) -> None:
        for rule in self.rules.business_keys:
            profile = self._safe(
                result,
                f"{rule.table}:{','.join(rule.columns)}",
                "business_key_rule",
                lambda item=rule: self._business_key_profile(item),
            )
            if profile is not None:
                result.business_keys.append(profile)

    def _business_key_profile(self, rule: BusinessKeyRule) -> BusinessKeyProfile:
        if not rule.columns:
            raise ValueError("业务键columns不能为空。")
        table = self._resolve_table(rule.table)
        for column in rule.columns:
            self._column_exists(table, column)
        columns = ", ".join(quote_identifier(item) for item in rule.columns)
        applicable = " AND ".join(
            f"{quote_identifier(item)} IS NOT NULL" for item in rule.columns
        )
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:BUSINESS_KEY_RULE
            WITH grouped AS (
                SELECT {columns}, COUNT_BIG(*) AS item_count
                FROM {qualified_name(table.schema, table.name)}
                WHERE {applicable}
                GROUP BY {columns}
            )
            SELECT
                COALESCE(SUM(item_count), 0) AS applicable_count,
                COALESCE(SUM(CASE WHEN item_count > 1 THEN 1 ELSE 0 END), 0)
                    AS duplicate_groups,
                COALESCE(SUM(CASE WHEN item_count > 1 THEN item_count - 1 ELSE 0 END), 0)
                    AS duplicate_rows
            FROM grouped
            """
        ) or {}
        return BusinessKeyProfile(
            table=table.qualified_name,
            columns=rule.columns,
            applicable_count=int(row.get("applicable_count") or 0),
            duplicate_groups=int(row.get("duplicate_groups") or 0),
            duplicate_rows=int(row.get("duplicate_rows") or 0),
            description=rule.description,
            bottom_line_threshold=rule.bottom_line_threshold,
        )

    def _profile_freshness(self, result: DatabaseProfile) -> None:
        for rule in self.rules.freshness_rules:
            profile = self._safe(
                result,
                f"{rule.table}.{rule.column}",
                "freshness_rule",
                lambda item=rule: self._freshness_profile(item),
            )
            if profile is not None:
                result.freshness.append(profile)

    def _freshness_profile(self, rule: FreshnessRule) -> FreshnessProfile:
        table = self._resolve_table(rule.table)
        self._column_exists(table, rule.column)
        column_meta = next(item for item in table.columns if item.name == rule.column)
        if column_meta.data_type.lower() not in DATE_TYPES:
            raise ValueError("时效性规则字段必须为SQL Server日期时间类型。")
        quoted = quote_identifier(rule.column)
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:FRESHNESS_RULE
            SELECT
                SUM(CASE WHEN {quoted} IS NOT NULL THEN 1 ELSE 0 END) AS applicable_count,
                SUM(CASE WHEN {quoted} < DATEADD(day, -:max_age_days, SYSUTCDATETIME())
                         THEN 1 ELSE 0 END) AS stale_count,
                MAX({quoted}) AS max_value
            FROM {qualified_name(table.schema, table.name)}
            """,
            {"max_age_days": int(rule.max_age_days)},
        ) or {}
        return FreshnessProfile(
            table=table.qualified_name,
            column=rule.column,
            applicable_count=int(row.get("applicable_count") or 0),
            stale_count=int(row.get("stale_count") or 0),
            max_value=row.get("max_value"),
            max_age_days=rule.max_age_days,
            description=rule.description,
        )

    def _profile_domains(self, result: DatabaseProfile) -> None:
        for rule in self.rules.domain_rules:
            profile = self._safe(
                result,
                f"{rule.table}.{rule.column}",
                "domain_rule",
                lambda item=rule: self._domain_profile(item),
            )
            if profile is not None:
                result.domains.append(profile)

    def _domain_profile(self, rule: DomainRule) -> DomainProfile:
        if not rule.allowed_values:
            raise ValueError("allowed_values不能为空。")
        table = self._resolve_table(rule.table)
        self._column_exists(table, rule.column)
        quoted = quote_identifier(rule.column)
        params = {f"value_{i}": value for i, value in enumerate(rule.allowed_values)}
        placeholders = ", ".join(f":value_{i}" for i in range(len(rule.allowed_values)))
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:DOMAIN_RULE
            SELECT
                SUM(CASE WHEN {quoted} IS NOT NULL THEN 1 ELSE 0 END) AS applicable_count,
                SUM(CASE WHEN {quoted} IS NOT NULL AND {quoted} NOT IN ({placeholders})
                         THEN 1 ELSE 0 END) AS invalid_count
            FROM {qualified_name(table.schema, table.name)}
            """,
            params,
        ) or {}
        return DomainProfile(
            table=table.qualified_name,
            column=rule.column,
            applicable_count=int(row.get("applicable_count") or 0),
            invalid_count=int(row.get("invalid_count") or 0),
            description=rule.description,
        )

    def _profile_custom_rules(self, result: DatabaseProfile) -> None:
        for rule in self.rules.custom_sql_rules:
            profile = self._safe(
                result,
                rule.rule_id,
                "custom_sql_rule",
                lambda item=rule: self._custom_rule_profile(item),
            )
            if profile is not None:
                result.custom_rules.append(profile)

    def _custom_rule_profile(self, rule: CustomSQLRule) -> CustomRuleProfile:
        if rule.indicator_id not in {f"DQ{i}" for i in range(1, 9)}:
            raise ValueError("自定义SQL规则indicator_id必须为DQ1-DQ8。")
        table = self._resolve_table(rule.table)
        invalid = validate_sql_condition(rule.invalid_condition_sql, "invalid_condition_sql")
        applicable = "1=1"
        if rule.applicable_condition_sql:
            applicable = validate_sql_condition(
                rule.applicable_condition_sql, "applicable_condition_sql"
            )
        row = self.executor.fetch_one(
            f"""
            -- EDQSG:CUSTOM_SQL_RULE
            SELECT
                SUM(CASE WHEN ({applicable}) THEN 1 ELSE 0 END) AS applicable_count,
                SUM(CASE WHEN ({applicable}) AND ({invalid}) THEN 1 ELSE 0 END)
                    AS invalid_count
            FROM {qualified_name(table.schema, table.name)}
            """
        ) or {}
        return CustomRuleProfile(
            rule_id=rule.rule_id,
            indicator_id=rule.indicator_id,
            table=table.qualified_name,
            applicable_count=int(row.get("applicable_count") or 0),
            invalid_count=int(row.get("invalid_count") or 0),
            description=rule.description,
            bottom_line_cap=rule.bottom_line_cap,
            bottom_line_penalty=rule.bottom_line_penalty,
        )
