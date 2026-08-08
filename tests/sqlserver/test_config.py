from edqsg.sqlserver.config import SQLServerAssessmentConfig


def test_config_from_mapping():
    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "localhost",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "scan": {"schemas": ["dbo"], "profile_mode": "sample", "sample_rows": 100},
            "rules": {
                "business_keys": [
                    {
                        "table": "dbo.Equipment",
                        "columns": ["equipment_code"],
                        "bottom_line_threshold": 0.01,
                    }
                ]
            },
        }
    )
    assert cfg.database.database == "EquipmentDB"
    assert cfg.scan.schemas == ("dbo",)
    assert cfg.rules.business_keys[0].columns == ("equipment_code",)


def test_visualization_configuration_is_parsed_and_validated():
    config = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "localhost",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "visualization": {
                "enabled": True,
                "formats": ["png", "svg"],
                "dpi": 300,
                "top_n": 12,
                "generate_robustness": True,
                "robustness_iterations": 50,
                "robustness_perturbation": 0.15,
            },
        }
    )
    assert config.visualization.formats == ("png", "svg")
    assert config.visualization.generate_robustness is True
    assert config.visualization.robustness_iterations == 50


def test_extended_rules_are_parsed():
    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "localhost",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "rules": {
                "logical_foreign_keys": [
                    {
                        "rule_id": "LFK-STOCK-PART",
                        "child_table": "dbo.StockDetail",
                        "child_columns": ["equipment_id"],
                        "parent_table": "dbo.Equipment",
                        "parent_columns": ["equipment_id"],
                    }
                ],
                "table_model_rules": [
                    {
                        "table": "dbo.Equipment",
                        "grain_columns": ["equipment_id"],
                        "max_columns": 20,
                        "forbidden_multivalue_columns": ["applicable_codes"],
                    }
                ],
                "master_data_consistency_rules": [
                    {
                        "rule_id": "MD-EQUIPMENT",
                        "entity_name": "器材",
                        "authoritative_table": "dbo.Equipment",
                        "related_table": "dbo.StockDetail",
                        "key_pairs": [["equipment_id", "equipment_id"]],
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
                    }
                ],
            },
        }
    )
    assert cfg.rules.logical_foreign_keys[0].child_columns == ("equipment_id",)
    assert cfg.rules.table_model_rules[0].forbidden_multivalue_columns == (
        "applicable_codes",
    )
    assert cfg.rules.master_data_consistency_rules[0].key_pairs == (
        ("equipment_id", "equipment_id"),
    )
    assert cfg.rules.supplemental_evidence[0].evidence_type == "process"


def test_relationship_controls_are_parsed_and_validated():
    cfg = SQLServerAssessmentConfig.from_mapping(
        {
            "database": {
                "server": "localhost",
                "database": "EquipmentDB",
                "authentication": "sql",
                "username": "reader",
                "password": "secret",
            },
            "rules": {
                "relationship_controls": [
                    {
                        "relationship_id": "REL-STOCK-EQUIPMENT",
                        "child_table": "dbo.StockDetail",
                        "child_columns": ["equipment_id"],
                        "parent_table": "dbo.Equipment",
                        "parent_columns": ["equipment_id"],
                        "cardinality": "many_to_one",
                        "delete_policy": "restrict",
                        "update_policy": "cascade_in_application",
                        "owner": "库存系统组",
                        "criticality": "critical",
                        "physical_fk_required": False,
                        "enforcement_modes": [
                            "application_validation",
                            "scheduled_audit",
                        ],
                        "control_coverage": 0.99,
                        "control_reliability": 0.98,
                        "operating_effectiveness": 0.99,
                        "exception_approved": True,
                        "exception_reason": "高并发写入性能评估后的受控例外",
                        "performance_evidence_id": "PERF-001",
                        "review_due_date": "2027-07-01",
                        "audit_frequency_hours": 1,
                        "maximum_orphan_rate": 0.0,
                        "minimum_control_score": 0.75,
                    }
                ]
            },
        }
    )
    rule = cfg.rules.relationship_controls[0]
    assert rule.child_columns == ("equipment_id",)
    assert rule.enforcement_modes == (
        "application_validation",
        "scheduled_audit",
    )
    assert rule.exception_approved is True
