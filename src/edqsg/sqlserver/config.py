"""SQL Server 自动评价流水线配置。

配置层保存连接参数、扫描范围、业务规则与补充证据，不直接建立数据库连接。
密码建议通过环境变量提供，避免写入配置文件和版本库。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SQLServerConnectionConfig:
    """SQL Server 连接参数。"""

    server: str
    database: str
    authentication: str = "sql"
    username: str | None = None
    password: str | None = None
    password_env: str | None = "EDQSG_DB_PASSWORD"
    port: int = 1433
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: bool = True
    trust_server_certificate: bool = False
    login_timeout: int = 30
    query_timeout: int = 120
    application_name: str = "EDQSG"

    def resolved_password(self) -> str | None:
        if self.password is not None:
            return self.password
        if self.password_env:
            return os.getenv(self.password_env)
        return None

    def validate(self) -> None:
        if not self.server.strip():
            raise ValueError("database.server不能为空。")
        if not self.database.strip():
            raise ValueError("database.database不能为空。")
        if self.port <= 0:
            raise ValueError("database.port必须大于0。")
        if self.authentication not in {"sql", "windows"}:
            raise ValueError("database.authentication只能为sql或windows。")
        if self.authentication == "sql":
            if not self.username:
                raise ValueError("SQL认证必须提供database.username。")
            if self.resolved_password() is None:
                raise ValueError(
                    "SQL认证未获得密码，请设置database.password或password_env对应环境变量。"
                )


@dataclass(frozen=True)
class SQLServerScanConfig:
    """数据库扫描范围与性能参数。"""

    schemas: tuple[str, ...] = ("dbo",)
    include_tables: tuple[str, ...] = ()
    exclude_tables: tuple[str, ...] = ("sysdiagrams",)
    profile_mode: str = "sample"  # metadata / sample / full
    sample_rows: int = 10000
    max_tables: int | None = None
    max_columns_per_table: int | None = None
    detect_field_redundancy: bool = True
    detect_table_redundancy: bool = True
    max_redundancy_pairs: int = 500
    read_uncommitted: bool = False
    audit_column_aliases: tuple[str, ...] = (
        "created_at",
        "create_time",
        "created_time",
        "updated_at",
        "update_time",
        "modified_at",
        "created_by",
        "creator",
        "updated_by",
        "modifier",
        "创建时间",
        "修改时间",
        "创建人",
        "修改人",
    )

    def validate(self) -> None:
        if self.profile_mode not in {"metadata", "sample", "full"}:
            raise ValueError("scan.profile_mode只能为metadata、sample或full。")
        if self.sample_rows <= 0:
            raise ValueError("scan.sample_rows必须大于0。")
        if self.max_tables is not None and self.max_tables <= 0:
            raise ValueError("scan.max_tables必须大于0或为空。")
        if self.max_columns_per_table is not None and self.max_columns_per_table <= 0:
            raise ValueError("scan.max_columns_per_table必须大于0或为空。")
        if self.max_redundancy_pairs <= 0:
            raise ValueError("scan.max_redundancy_pairs必须大于0。")


@dataclass(frozen=True)
class RequiredColumnRule:
    table: str
    column: str
    condition_sql: str | None = None
    description: str = ""
    bottom_line: bool = False


@dataclass(frozen=True)
class BusinessKeyRule:
    table: str
    columns: tuple[str, ...]
    description: str = ""
    bottom_line_threshold: float | None = None


@dataclass(frozen=True)
class FreshnessRule:
    table: str
    column: str
    max_age_days: int
    description: str = ""


@dataclass(frozen=True)
class DomainRule:
    table: str
    column: str
    allowed_values: tuple[Any, ...]
    description: str = ""


@dataclass(frozen=True)
class CustomSQLRule:
    """自定义只读质量规则。"""

    rule_id: str
    indicator_id: str
    table: str
    invalid_condition_sql: str
    description: str
    applicable_condition_sql: str | None = None
    bottom_line_cap: float | None = None
    bottom_line_penalty: float = 0.0


@dataclass(frozen=True)
class LogicalForeignKeyRule:
    """无论是否存在物理外键，都应执行的逻辑关联完整性规则。"""

    rule_id: str
    child_table: str
    child_columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]
    description: str = ""
    bottom_line_threshold: float | None = None




@dataclass(frozen=True)
class RelationshipControlRule:
    """预期业务关系及其完整性控制。

    物理外键只是可选控制方式之一。对于因高并发、批量加载、分布式边界或
    历史系统约束而未建立物理外键的关系，可登记应用校验、受控存储过程、
    ETL门禁、消息校验或定期审计等替代控制，并记录受控例外证据。
    """

    relationship_id: str
    child_table: str
    child_columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]
    description: str = ""
    cardinality: str = "many_to_one"
    child_nullable: bool = True
    delete_policy: str = "unspecified"
    update_policy: str = "unspecified"
    owner: str = ""
    criticality: str = "medium"
    physical_fk_required: bool = False
    enforcement_modes: tuple[str, ...] = ()
    control_coverage: float = 1.0
    control_reliability: float = 1.0
    operating_effectiveness: float = 1.0
    exception_approved: bool = False
    exception_reason: str = ""
    performance_evidence_id: str = ""
    review_due_date: str = ""
    audit_frequency_hours: float | None = None
    maximum_orphan_rate: float = 0.0
    minimum_control_score: float = 0.70
    bottom_line_cap: float | None = None

@dataclass(frozen=True)
class TableModelRule:
    """用于半自动核验表职责、记录粒度与基础规范化条件。

    ``forbidden_multivalue_columns`` 用于声明不应出现在关系表中的逗号分隔、
    JSON列表或其他非原子多值字段。该配置属于业务结构契约，避免仅凭字段名
    猜测而产生大量误报。
    """

    table: str
    grain_columns: tuple[str, ...] = ()
    max_columns: int = 50
    allow_heap: bool = False
    require_description: bool = True
    forbidden_multivalue_columns: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class MasterDataGroup:
    """同一主数据对象的权威来源配置。"""

    entity_name: str
    authoritative_table: str
    related_tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class MasterDataConsistencyRule:
    """权威主数据与业务表复制属性之间的实际一致性检测。"""

    rule_id: str
    entity_name: str
    authoritative_table: str
    related_table: str
    key_pairs: tuple[tuple[str, str], ...]
    attribute_pairs: tuple[tuple[str, str], ...] = ()
    description: str = ""
    bottom_line_threshold: float | None = None


@dataclass(frozen=True)
class LifecycleControlRule:
    """结构生命周期、审计和互操作准备度的显式控制要求。"""

    table: str
    required_audit_columns: tuple[str, ...] = ()
    interoperability_columns: tuple[str, ...] = ()
    require_temporal: bool = False
    require_description: bool = True
    description: str = ""


@dataclass(frozen=True)
class SupplementalEvidenceRule:
    """由流程日志、制度审查或专家判断补充到指标的证据。

    ``evidence_type`` 建议使用 ``process`` 或 ``expert``。可提供
    ``observed_score``，也可提供五等级 ``belief_degrees``；两者至少一个非空。
    """

    evidence_id: str
    indicator_id: str
    evidence_type: str
    source: str
    coverage: float
    authority: float
    timeliness: float
    repeatability: float
    business_fit: float
    observed_score: float | None = None
    belief_degrees: tuple[float, float, float, float, float] | None = None
    unknown_degree: float | None = None
    importance: float = 1.0
    description: str = ""
    collected_at: str = ""
    scope: str = ""
    basis: str = ""


@dataclass(frozen=True)
class SQLServerRuleConfig:
    """需要业务知识才能确定的规则与补充证据。"""

    required_columns: tuple[RequiredColumnRule, ...] = ()
    business_keys: tuple[BusinessKeyRule, ...] = ()
    freshness_rules: tuple[FreshnessRule, ...] = ()
    domain_rules: tuple[DomainRule, ...] = ()
    custom_sql_rules: tuple[CustomSQLRule, ...] = ()
    logical_foreign_keys: tuple[LogicalForeignKeyRule, ...] = ()
    relationship_controls: tuple[RelationshipControlRule, ...] = ()
    table_model_rules: tuple[TableModelRule, ...] = ()
    critical_tables: tuple[str, ...] = ()
    master_data_groups: tuple[MasterDataGroup, ...] = ()
    master_data_consistency_rules: tuple[MasterDataConsistencyRule, ...] = ()
    lifecycle_control_rules: tuple[LifecycleControlRule, ...] = ()
    supplemental_evidence: tuple[SupplementalEvidenceRule, ...] = ()


@dataclass(frozen=True)
class SQLServerVisualizationConfig:
    """统计图与论文图输出配置。"""

    enabled: bool = False
    formats: tuple[str, ...] = ("png", "svg")
    dpi: int = 300
    top_n: int = 15
    generate_dashboard: bool = True
    generate_robustness: bool = False
    robustness_iterations: int = 500
    robustness_perturbation: float = 0.10

    def validate(self) -> None:
        allowed = {"png", "svg", "pdf"}
        if not self.formats or any(fmt.lower() not in allowed for fmt in self.formats):
            raise ValueError("visualization.formats仅支持png、svg或pdf。")
        if self.dpi < 72:
            raise ValueError("visualization.dpi不得低于72。")
        if self.top_n <= 0:
            raise ValueError("visualization.top_n必须大于0。")
        if self.robustness_iterations <= 0:
            raise ValueError("visualization.robustness_iterations必须大于0。")
        if not 0 <= self.robustness_perturbation < 1:
            raise ValueError("visualization.robustness_perturbation必须位于[0,1)。")


@dataclass(frozen=True)
class SQLServerAssessmentConfig:
    """SQL Server 自动评价总配置。"""

    database: SQLServerConnectionConfig
    scan: SQLServerScanConfig = field(default_factory=SQLServerScanConfig)
    rules: SQLServerRuleConfig = field(default_factory=SQLServerRuleConfig)
    dq_weights: dict[str, float] = field(default_factory=dict)
    sg_weights: dict[str, float] = field(default_factory=dict)
    visualization: SQLServerVisualizationConfig = field(default_factory=SQLServerVisualizationConfig)
    output_dir: str = "output"

    def validate(self) -> None:
        self.database.validate()
        self.scan.validate()
        self.visualization.validate()
        valid_dq = {f"DQ{i}" for i in range(1, 9)}
        valid_sg = {f"SG{i}" for i in range(1, 9)}
        valid_indicators = valid_dq | valid_sg
        if self.dq_weights and set(self.dq_weights) != valid_dq:
            raise ValueError("dq_weights必须完整包含DQ1-DQ8。")
        if self.sg_weights and set(self.sg_weights) != valid_sg:
            raise ValueError("sg_weights必须完整包含SG1-SG8。")
        for rule in self.rules.logical_foreign_keys:
            if not rule.child_columns or len(rule.child_columns) != len(rule.parent_columns):
                raise ValueError(f"逻辑外键{rule.rule_id}的子列和父列必须等长且非空。")
        allowed_modes = {
            "application_validation",
            "stored_procedure",
            "etl_gate",
            "message_validation",
            "scheduled_audit",
            "manual_reconciliation",
            "documentation_only",
        }
        allowed_criticality = {"low", "medium", "high", "critical"}
        for rule in self.rules.relationship_controls:
            if not rule.child_columns or len(rule.child_columns) != len(rule.parent_columns):
                raise ValueError(
                    f"关系控制{rule.relationship_id}的子列和父列必须等长且非空。"
                )
            if rule.criticality not in allowed_criticality:
                raise ValueError(
                    f"关系控制{rule.relationship_id}的criticality不合法。"
                )
            unknown_modes = set(rule.enforcement_modes) - allowed_modes
            if unknown_modes:
                raise ValueError(
                    f"关系控制{rule.relationship_id}存在不支持的enforcement_modes: "
                    f"{sorted(unknown_modes)}"
                )
            for name, value in (
                ("control_coverage", rule.control_coverage),
                ("control_reliability", rule.control_reliability),
                ("operating_effectiveness", rule.operating_effectiveness),
                ("maximum_orphan_rate", rule.maximum_orphan_rate),
                ("minimum_control_score", rule.minimum_control_score),
            ):
                if not 0.0 <= value <= 1.0:
                    raise ValueError(
                        f"关系控制{rule.relationship_id}的{name}必须位于[0,1]。"
                    )
            if rule.bottom_line_cap is not None and not 0.0 <= rule.bottom_line_cap <= 100.0:
                raise ValueError(
                    f"关系控制{rule.relationship_id}的bottom_line_cap必须位于[0,100]。"
                )
            if rule.audit_frequency_hours is not None and rule.audit_frequency_hours <= 0:
                raise ValueError(
                    f"关系控制{rule.relationship_id}的audit_frequency_hours必须大于0。"
                )
        for rule in self.rules.table_model_rules:
            if rule.max_columns <= 0:
                raise ValueError("table_model_rules.max_columns必须大于0。")
        for rule in self.rules.master_data_consistency_rules:
            if not rule.key_pairs:
                raise ValueError(f"主数据一致性规则{rule.rule_id}必须配置key_pairs。")
        for rule in self.rules.supplemental_evidence:
            if rule.indicator_id not in valid_indicators:
                raise ValueError("supplemental_evidence.indicator_id必须为DQ1-DQ8或SG1-SG8。")
            if rule.evidence_type not in {"data", "structure", "rule", "process", "expert"}:
                raise ValueError("supplemental_evidence.evidence_type不合法。")
            if rule.observed_score is None and rule.belief_degrees is None:
                raise ValueError("补充证据必须提供observed_score或belief_degrees。")

    @staticmethod
    def _pairs(items: list[Any] | tuple[Any, ...]) -> tuple[tuple[str, str], ...]:
        result: list[tuple[str, str]] = []
        for item in items:
            if isinstance(item, dict):
                left = item.get("left") or item.get("child") or item.get("authoritative")
                right = item.get("right") or item.get("parent") or item.get("related")
                if left is None or right is None:
                    raise ValueError("字段映射对象必须包含left/right或同义键。")
                result.append((str(left), str(right)))
            else:
                if len(item) != 2:
                    raise ValueError("字段映射必须为二元组。")
                result.append((str(item[0]), str(item[1])))
        return tuple(result)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SQLServerAssessmentConfig":
        db = SQLServerConnectionConfig(**data["database"])
        scan_data = dict(data.get("scan", {}))
        for key in ("schemas", "include_tables", "exclude_tables", "audit_column_aliases"):
            if key in scan_data:
                scan_data[key] = tuple(scan_data[key])
        scan = SQLServerScanConfig(**scan_data)

        rules_data = data.get("rules", {})
        supplemental: list[SupplementalEvidenceRule] = []
        for item in rules_data.get("supplemental_evidence", []):
            prepared = dict(item)
            if prepared.get("belief_degrees") is not None:
                prepared["belief_degrees"] = tuple(float(x) for x in prepared["belief_degrees"])
            supplemental.append(SupplementalEvidenceRule(**prepared))

        rules = SQLServerRuleConfig(
            required_columns=tuple(
                RequiredColumnRule(**item) for item in rules_data.get("required_columns", [])
            ),
            business_keys=tuple(
                BusinessKeyRule(**{**item, "columns": tuple(item.get("columns", ()))})
                for item in rules_data.get("business_keys", [])
            ),
            freshness_rules=tuple(
                FreshnessRule(**item) for item in rules_data.get("freshness_rules", [])
            ),
            domain_rules=tuple(
                DomainRule(**{**item, "allowed_values": tuple(item.get("allowed_values", ()))})
                for item in rules_data.get("domain_rules", [])
            ),
            custom_sql_rules=tuple(
                CustomSQLRule(**item) for item in rules_data.get("custom_sql_rules", [])
            ),
            logical_foreign_keys=tuple(
                LogicalForeignKeyRule(
                    **{
                        **item,
                        "child_columns": tuple(item.get("child_columns", ())),
                        "parent_columns": tuple(item.get("parent_columns", ())),
                    }
                )
                for item in rules_data.get("logical_foreign_keys", [])
            ),
            relationship_controls=tuple(
                RelationshipControlRule(
                    **{
                        **item,
                        "child_columns": tuple(item.get("child_columns", ())),
                        "parent_columns": tuple(item.get("parent_columns", ())),
                        "enforcement_modes": tuple(item.get("enforcement_modes", ())),
                    }
                )
                for item in rules_data.get("relationship_controls", [])
            ),
            table_model_rules=tuple(
                TableModelRule(
                    **{
                        **item,
                        "grain_columns": tuple(item.get("grain_columns", ())),
                        "forbidden_multivalue_columns": tuple(
                            item.get("forbidden_multivalue_columns", ())
                        ),
                    }
                )
                for item in rules_data.get("table_model_rules", [])
            ),
            critical_tables=tuple(rules_data.get("critical_tables", ())),
            master_data_groups=tuple(
                MasterDataGroup(**{**item, "related_tables": tuple(item.get("related_tables", ()))})
                for item in rules_data.get("master_data_groups", [])
            ),
            master_data_consistency_rules=tuple(
                MasterDataConsistencyRule(
                    **{
                        **item,
                        "key_pairs": cls._pairs(item.get("key_pairs", ())),
                        "attribute_pairs": cls._pairs(item.get("attribute_pairs", ())),
                    }
                )
                for item in rules_data.get("master_data_consistency_rules", [])
            ),
            lifecycle_control_rules=tuple(
                LifecycleControlRule(
                    **{
                        **item,
                        "required_audit_columns": tuple(item.get("required_audit_columns", ())),
                        "interoperability_columns": tuple(item.get("interoperability_columns", ())),
                    }
                )
                for item in rules_data.get("lifecycle_control_rules", [])
            ),
            supplemental_evidence=tuple(supplemental),
        )
        visualization_data = dict(data.get("visualization", {}))
        if "formats" in visualization_data:
            visualization_data["formats"] = tuple(visualization_data["formats"])
        visualization = SQLServerVisualizationConfig(**visualization_data)
        result = cls(
            database=db,
            scan=scan,
            rules=rules,
            dq_weights={str(k): float(v) for k, v in data.get("dq_weights", {}).items()},
            sg_weights={str(k): float(v) for k, v in data.get("sg_weights", {}).items()},
            visualization=visualization,
            output_dir=str(data.get("output_dir", "output")),
        )
        result.validate()
        return result

    @classmethod
    def from_json(cls, path: str | Path) -> "SQLServerAssessmentConfig":
        with Path(path).open("r", encoding="utf-8") as file:
            return cls.from_mapping(json.load(file))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SQLServerAssessmentConfig":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("读取YAML配置需安装PyYAML：pip install edqsg[yaml]") from exc
        with Path(path).open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        if not isinstance(data, dict):
            raise ValueError("YAML配置顶层必须为对象。")
        return cls.from_mapping(data)

    @classmethod
    def from_file(cls, path: str | Path) -> "SQLServerAssessmentConfig":
        suffix = Path(path).suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return cls.from_yaml(path)
        if suffix == ".json":
            return cls.from_json(path)
        raise ValueError("配置文件仅支持.json、.yaml或.yml。")
