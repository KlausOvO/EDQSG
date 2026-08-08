from edqsg import EDQSGConfig, RedundancyAnalyzer, RedundancyRiskLevel


def analyzer():
    cfg = EDQSGConfig()
    return RedundancyAnalyzer(
        cfg.field_similarity_weights,
        cfg.table_similarity_weights,
        cfg.redundancy_risk_weights,
        cfg.redundancy_risk_thresholds,
    )


def test_controlled_redundancy():
    result = analyzer().assess_field(
        left_object="t1.name",
        right_object="t2.name",
        features=[0.9] * 6,
        necessity=0.9,
        conflict=0.05,
        update_independence=0.1,
        sync_control=0.95,
        impact=0.4,
    )
    assert result.risk_level is RedundancyRiskLevel.CONTROLLED


def test_high_risk_redundancy():
    result = analyzer().assess_table(
        left_object="equipment_a",
        right_object="equipment_b",
        features=[0.95] * 6,
        necessity=0.0,
        conflict=1.0,
        update_independence=1.0,
        sync_control=0.0,
        impact=1.0,
    )
    assert result.risk_level is RedundancyRiskLevel.HIGH
    assert 0 <= result.risk_index <= 1
