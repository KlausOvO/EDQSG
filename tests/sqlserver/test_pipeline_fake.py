from __future__ import annotations

from typing import Any

from edqsg.sqlserver.config import SQLServerAssessmentConfig
from edqsg.sqlserver.pipeline import SQLServerAssessmentPipeline


class FakeExecutor:
    """以查询标签返回固定数据，验证SQL Server流水线无需真实数据库即可组装。"""

    def test_connection(self):
        return {
            "database_name": "EquipmentDB",
            "server_name": "TEST-SQL",
            "product_version": "16.0",
            "edition": "Developer",
        }

    def fetch_all(self, sql: str, params=None) -> list[dict[str, Any]]:
        if "EDQSG:TABLES" in sql:
            return [
                {
                    "schema_name": "dbo",
                    "table_name": "Equipment",
                    "description": "器材主数据",
                    "row_count": 100,
                    "temporal_type": 0,
                    "is_memory_optimized": 0,
                },
                {
                    "schema_name": "dbo",
                    "table_name": "StockDetail",
                    "description": "库存明细",
                    "row_count": 200,
                    "temporal_type": 0,
                    "is_memory_optimized": 0,
                },
            ]
        if "EDQSG:COLUMNS" in sql:
            rows = []
            definitions = {
                "Equipment": [
                    (1, "equipment_id", "int", False, "主键"),
                    (2, "equipment_code", "nvarchar", False, "器材编码"),
                    (3, "equipment_name", "nvarchar", True, "器材名称"),
                    (4, "updated_at", "datetime2", True, "修改时间"),
                ],
                "StockDetail": [
                    (1, "detail_id", "int", False, "主键"),
                    (2, "equipment_id", "int", False, "器材标识"),
                    (3, "quantity", "decimal", False, "库存数量"),
                    (4, "updated_at", "datetime2", True, "修改时间"),
                ],
            }
            for table, columns in definitions.items():
                for ordinal, name, dtype, nullable, desc in columns:
                    rows.append(
                        {
                            "schema_name": "dbo",
                            "table_name": table,
                            "column_name": name,
                            "ordinal_position": ordinal,
                            "data_type": dtype,
                            "max_length": 100,
                            "precision": 18,
                            "scale": 2,
                            "is_nullable": nullable,
                            "is_identity": name.endswith("_id") and ordinal == 1,
                            "is_computed": 0,
                            "default_definition": None,
                            "description": desc,
                        }
                    )
            return rows
        if "EDQSG:KEYS" in sql:
            return [
                {
                    "schema_name": "dbo",
                    "table_name": "Equipment",
                    "constraint_name": "PK_Equipment",
                    "constraint_type": "PK",
                    "key_ordinal": 1,
                    "column_name": "equipment_id",
                },
                {
                    "schema_name": "dbo",
                    "table_name": "StockDetail",
                    "constraint_name": "PK_StockDetail",
                    "constraint_type": "PK",
                    "key_ordinal": 1,
                    "column_name": "detail_id",
                },
            ]
        if "EDQSG:INDEXES" in sql:
            return [
                {
                    "schema_name": "dbo",
                    "table_name": "Equipment",
                    "index_name": "PK_Equipment",
                    "type_desc": "CLUSTERED",
                    "is_unique": 1,
                    "is_primary_key": 1,
                    "is_unique_constraint": 0,
                    "is_disabled": 0,
                },
                {
                    "schema_name": "dbo",
                    "table_name": "StockDetail",
                    "index_name": "PK_StockDetail",
                    "type_desc": "CLUSTERED",
                    "is_unique": 1,
                    "is_primary_key": 1,
                    "is_unique_constraint": 0,
                    "is_disabled": 0,
                },
            ]
        if "EDQSG:CHECKS" in sql:
            return []
        if "EDQSG:FOREIGN_KEYS" in sql:
            return [
                {
                    "fk_name": "FK_StockDetail_Equipment",
                    "parent_schema": "dbo",
                    "parent_table": "StockDetail",
                    "parent_column": "equipment_id",
                    "referenced_schema": "dbo",
                    "referenced_table": "Equipment",
                    "referenced_column": "equipment_id",
                    "constraint_column_id": 1,
                    "is_disabled": 0,
                    "is_not_trusted": 0,
                    "delete_action": "NO_ACTION",
                    "update_action": "NO_ACTION",
                }
            ]
        return []

    def fetch_one(self, sql: str, params=None):
        if "EDQSG:SERVER_INFO" in sql:
            return self.test_connection()
        if "EDQSG:COLUMN_PROFILE" in sql:
            if "equipment_name" in sql:
                return {"observed_rows": 100, "null_count": 5, "blank_count": 2, "distinct_count": 90}
            return {"observed_rows": 100, "null_count": 0, "blank_count": 0, "distinct_count": 100}
        if "EDQSG:FOREIGN_KEY_PROFILE" in sql:
            return {"applicable_count": 200, "orphan_count": 2}
        if "EDQSG:LOGICAL_FOREIGN_KEY_RULE" in sql:
            return {"applicable_count": 200, "orphan_count": 5}
        if "EDQSG:MASTER_DATA_CONSISTENCY_RULE" in sql:
            return {"applicable_count": 200, "orphan_count": 2, "mismatch_count": 3}
        if "EDQSG:BUSINESS_KEY_RULE" in sql:
            return {"applicable_count": 100, "duplicate_groups": 2, "duplicate_rows": 2}
        if "EDQSG:FRESHNESS_RULE" in sql:
            return {"applicable_count": 100, "stale_count": 10, "max_value": "2026-07-01"}
        if "EDQSG:CUSTOM_SQL_RULE" in sql:
            return {"applicable_count": 200, "invalid_count": 3}
        if "EDQSG:REQUIRED_COLUMN_RULE" in sql:
            return {"applicable_count": 100, "missing_count": 7}
        if "EDQSG:DOMAIN_RULE" in sql:
            return {"applicable_count": 100, "invalid_count": 1}
        return None

    def scalar(self, sql: str, params=None):
        return None


def test_full_pipeline_with_fake_executor(tmp_path):
    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "fake",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {"schemas": ["dbo"], "profile_mode": "sample", "sample_rows": 100},
            "rules": {
                "critical_tables": ["dbo.Equipment"],
                "required_columns": [
                    {
                        "table": "dbo.Equipment",
                        "column": "equipment_name",
                        "description": "名称必填",
                    }
                ],
                "business_keys": [
                    {
                        "table": "dbo.Equipment",
                        "columns": ["equipment_code"],
                        "bottom_line_threshold": 0.01,
                    }
                ],
                "freshness_rules": [
                    {"table": "dbo.Equipment", "column": "updated_at", "max_age_days": 365}
                ],
                "domain_rules": [
                    {
                        "table": "dbo.Equipment",
                        "column": "equipment_code",
                        "allowed_values": ["A", "B"],
                    }
                ],
                "custom_sql_rules": [
                    {
                        "rule_id": "R-QTY",
                        "indicator_id": "DQ2",
                        "table": "dbo.StockDetail",
                        "invalid_condition_sql": "quantity < 0",
                        "description": "库存数量不得为负",
                    }
                ],
                "master_data_groups": [
                    {
                        "entity_name": "器材",
                        "authoritative_table": "dbo.Equipment",
                        "related_tables": ["dbo.StockDetail"],
                    }
                ],
            },
        }
    )
    result = SQLServerAssessmentPipeline(cfg, executor=FakeExecutor()).run()
    assert len(result.metadata.tables) == 2
    assert len(result.assessment.indicator_results) == 16
    assert result.assessment.final_score <= result.assessment.initial_score
    assert any(trigger.rule_id.startswith("BL-UNIQUE") for trigger in result.assessment.bottom_line_triggers)
    assert result.assessment.governance_tasks
    output = result.export_json(tmp_path / "report.json")
    assert output.exists()


def test_pipeline_exports_paper_figures_and_dashboard(tmp_path):
    """验证下一版可自动输出论文图、图形清单和静态驾驶舱。"""

    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "fake",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {
                "schemas": ["dbo"],
                "profile_mode": "sample",
                "sample_rows": 100,
                "detect_field_redundancy": True,
                "detect_table_redundancy": True,
            },
            "rules": {
                "critical_tables": ["dbo.Equipment"],
                "required_columns": [
                    {"table": "dbo.Equipment", "column": "equipment_name"}
                ],
                "business_keys": [
                    {
                        "table": "dbo.Equipment",
                        "columns": ["equipment_code"],
                        "bottom_line_threshold": 0.01,
                    }
                ],
                "custom_sql_rules": [
                    {
                        "rule_id": "R-QTY",
                        "indicator_id": "DQ2",
                        "table": "dbo.StockDetail",
                        "invalid_condition_sql": "quantity < 0",
                        "description": "库存数量不得为负",
                    }
                ],
            },
            "visualization": {
                "enabled": True,
                "formats": ["png"],
                "dpi": 100,
                "top_n": 10,
                "generate_dashboard": True,
                "generate_robustness": False,
            },
            "output_dir": str(tmp_path),
        }
    )
    pipeline = SQLServerAssessmentPipeline(cfg, executor=FakeExecutor())
    result = pipeline.run_and_export(tmp_path)
    assert result.assessment.coupling_relations
    assert (tmp_path / "figures" / "fig01_indicator_scores.png").exists()
    assert (tmp_path / "figures" / "fig02_score_confidence.png").exists()
    assert (tmp_path / "figures" / "fig03_evidence_composition.png").exists()
    assert (tmp_path / "figures" / "fig04_qs_coupling_heatmap.png").exists()
    assert (tmp_path / "figures" / "figure_manifest.json").exists()
    assert (tmp_path / "edqsg_dashboard.html").exists()


def test_extended_evidence_and_logical_relationships_are_used():
    from edqsg.models import EvidenceType

    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "fake",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {"schemas": ["dbo"], "profile_mode": "sample", "sample_rows": 100},
            "rules": {
                "business_keys": [
                    {"table": "dbo.Equipment", "columns": ["equipment_id"]}
                ],
                "logical_foreign_keys": [
                    {
                        "rule_id": "LFK-STOCK-EQUIPMENT",
                        "child_table": "dbo.StockDetail",
                        "child_columns": ["equipment_id"],
                        "parent_table": "dbo.Equipment",
                        "parent_columns": ["equipment_id"],
                        "bottom_line_threshold": 0.01,
                    }
                ],
                "table_model_rules": [
                    {
                        "table": "dbo.Equipment",
                        "grain_columns": ["equipment_id"],
                        "max_columns": 20,
                    },
                    {
                        "table": "dbo.StockDetail",
                        "grain_columns": ["detail_id"],
                        "max_columns": 20,
                    },
                ],
                "master_data_groups": [
                    {
                        "entity_name": "器材",
                        "authoritative_table": "dbo.Equipment",
                        "related_tables": ["dbo.StockDetail"],
                    }
                ],
                "master_data_consistency_rules": [
                    {
                        "rule_id": "MD-EQUIPMENT",
                        "entity_name": "器材",
                        "authoritative_table": "dbo.Equipment",
                        "related_table": "dbo.StockDetail",
                        "key_pairs": [["equipment_id", "equipment_id"]],
                        "bottom_line_threshold": 0.01,
                    }
                ],
                "lifecycle_control_rules": [
                    {
                        "table": "dbo.Equipment",
                        "required_audit_columns": ["updated_at"],
                        "interoperability_columns": ["equipment_code"],
                    }
                ],
                "supplemental_evidence": [
                    {
                        "evidence_id": "PROC-DQ7-01",
                        "indicator_id": "DQ7",
                        "evidence_type": "process",
                        "source": "同步作业日志",
                        "coverage": 0.9,
                        "authority": 0.9,
                        "timeliness": 0.95,
                        "repeatability": 0.95,
                        "business_fit": 1.0,
                        "observed_score": 88,
                    },
                    {
                        "evidence_id": "EXP-SG2-01",
                        "indicator_id": "SG2",
                        "evidence_type": "expert",
                        "source": "模型评审组",
                        "coverage": 0.8,
                        "authority": 0.95,
                        "timeliness": 0.9,
                        "repeatability": 0.8,
                        "business_fit": 1.0,
                        "belief_degrees": [0.1, 0.6, 0.2, 0.05, 0.0],
                        "unknown_degree": 0.05,
                    },
                ],
            },
        }
    )
    result = SQLServerAssessmentPipeline(cfg, executor=FakeExecutor()).run()
    assert len(result.profile.logical_foreign_keys) == 1
    assert len(result.profile.master_data_consistency) == 1
    dq7 = next(item for item in result.assessment.indicator_results if item.indicator_id == "DQ7")
    sg2 = next(item for item in result.assessment.indicator_results if item.indicator_id == "SG2")
    assert any(item.evidence_type is EvidenceType.PROCESS for item in dq7.evidence_results)
    assert any(item.evidence_type is EvidenceType.EXPERT for item in sg2.evidence_results)
    assert any(item.rule_id.startswith("BL-LOGICAL-FK") for item in result.assessment.bottom_line_triggers)
    assert any(item.rule_id.startswith("BL-MASTER") for item in result.assessment.bottom_line_triggers)


class NoPhysicalForeignKeyExecutor(FakeExecutor):
    def fetch_all(self, sql: str, params=None):
        if "EDQSG:FOREIGN_KEYS" in sql:
            return []
        return super().fetch_all(sql, params)

    def fetch_one(self, sql: str, params=None):
        if "EDQSG:RELATIONSHIP_CONTROL_RULE" in sql:
            return {"applicable_count": 200, "orphan_count": 0}
        return super().fetch_one(sql, params)


def _relationship_control_config(*, controlled: bool) -> SQLServerAssessmentConfig:
    return SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "fake",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {"schemas": ["dbo"], "profile_mode": "sample", "sample_rows": 100},
            "rules": {
                "relationship_controls": [
                    {
                        "relationship_id": "REL-STOCK-EQUIPMENT",
                        "child_table": "dbo.StockDetail",
                        "child_columns": ["equipment_id"],
                        "parent_table": "dbo.Equipment",
                        "parent_columns": ["equipment_id"],
                        "description": "库存明细必须引用有效器材",
                        "cardinality": "many_to_one",
                        "delete_policy": "restrict",
                        "update_policy": "cascade_in_application",
                        "owner": "库存系统组",
                        "criticality": "critical",
                        "physical_fk_required": False,
                        "enforcement_modes": (
                            ["application_validation", "scheduled_audit"]
                            if controlled
                            else ["documentation_only"]
                        ),
                        "control_coverage": 0.99 if controlled else 0.50,
                        "control_reliability": 0.98 if controlled else 0.50,
                        "operating_effectiveness": 0.99 if controlled else 0.50,
                        "exception_approved": controlled,
                        "exception_reason": (
                            "高并发写入性能评估后的受控例外" if controlled else ""
                        ),
                        "performance_evidence_id": "PERF-001" if controlled else "",
                        "review_due_date": "2027-07-01" if controlled else "",
                        "audit_frequency_hours": 1 if controlled else None,
                        "maximum_orphan_rate": 0.0,
                        "minimum_control_score": 0.75,
                        "bottom_line_cap": 50,
                    }
                ]
            },
        }
    )


def test_controlled_relationship_without_physical_fk_is_not_automatically_penalized():
    cfg = _relationship_control_config(controlled=True)
    result = SQLServerAssessmentPipeline(
        cfg, executor=NoPhysicalForeignKeyExecutor()
    ).run()
    profile = result.profile.relationship_controls[0]
    assert profile.physical_fk_present is False
    assert profile.control_score > 0.85
    assert profile.semantic_score > 0.95
    assert not any(
        item.rule_id.startswith("BL-RELATIONSHIP-CONTROL")
        for item in result.assessment.bottom_line_triggers
    )


def test_uncontrolled_relationship_without_physical_fk_triggers_control_bottom_line():
    cfg = _relationship_control_config(controlled=False)
    result = SQLServerAssessmentPipeline(
        cfg, executor=NoPhysicalForeignKeyExecutor()
    ).run()
    profile = result.profile.relationship_controls[0]
    assert profile.control_score < 0.10
    assert any(
        item.rule_id == "BL-RELATIONSHIP-CONTROL-REL-STOCK-EQUIPMENT"
        for item in result.assessment.bottom_line_triggers
    )


def test_trusted_physical_fk_is_recognized_as_strong_control():
    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "fake",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {"schemas": ["dbo"], "profile_mode": "sample", "sample_rows": 100},
            "rules": {
                "relationship_controls": [
                    {
                        "relationship_id": "REL-STOCK-EQUIPMENT",
                        "child_table": "dbo.StockDetail",
                        "child_columns": ["equipment_id"],
                        "parent_table": "dbo.Equipment",
                        "parent_columns": ["equipment_id"],
                        "description": "库存明细必须引用有效器材",
                        "cardinality": "many_to_one",
                        "delete_policy": "restrict",
                        "update_policy": "no_action",
                        "owner": "DBA",
                        "criticality": "critical",
                        "physical_fk_required": True,
                        "enforcement_modes": [],
                        "maximum_orphan_rate": 0.05,
                        "minimum_control_score": 0.90,
                    }
                ]
            },
        }
    )
    result = SQLServerAssessmentPipeline(cfg, executor=FakeExecutor()).run()
    profile = result.profile.relationship_controls[0]
    assert profile.physical_fk_trusted is True
    assert profile.control_score == 1.0
