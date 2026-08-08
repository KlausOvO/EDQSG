"""审稿修订同步测试：两类复核、聚合门槛、证据覆盖率、根因参与条件。"""

import pytest

from edqsg import Domain, EDQSGModel, Evidence, EvidenceType, Indicator


def ev(eid, beliefs, reliability=1.0):
    return Evidence(
        evidence_id=eid,
        evidence_type=EvidenceType.DATA,
        source="sync-test",
        coverage=reliability,
        authority=reliability,
        timeliness=reliability,
        repeatability=reliability,
        business_fit=reliability,
        belief_degrees=beliefs,
    )


def test_insufficient_evidence_review_state():
    """未知度 0.4 ≥ θ_review(0.3) 时进入证据不足复核，但参与域内聚合。"""

    model = EDQSGModel()
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "准确性", Domain.DATA_QUALITY, (ev("E1", (1, 0, 0, 0, 0), 0.6),)),
            Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E2", (1, 0, 0, 0, 0)),)),
        ],
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
    )
    dq1 = report.indicator_results[0]
    assert dq1.unknown_degree == pytest.approx(0.4)
    assert dq1.review_state == "insufficient_evidence"
    assert dq1.review_required is True
    # 证据不足复核仍参与域内聚合，覆盖率保持 1。
    assert report.dq.evidence_coverage == pytest.approx(1.0)
    assert "DQ1" not in report.excluded_indicator_ids


def test_conflict_review_is_excluded_from_aggregation():
    """冲突复核不参与域内聚合；全部指标被排除时不出具总体等级。"""

    model = EDQSGModel()
    item = Indicator(
        "DQ1",
        "准确性",
        Domain.DATA_QUALITY,
        (
            ev("E1", (1, 0, 0, 0, 0)),
            ev("E2", (0, 0, 0, 0, 1)),
        ),
    )
    with pytest.raises(ValueError, match="全部指标因证据不足或冲突复核被排除"):
        model.evaluate(
            indicators=[
                item,
                Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E3", (1, 0, 0, 0, 0)),)),
            ],
            dq_weights={"DQ1": 1},
            sg_weights={"SG1": 1},
        )


def test_aggregation_exclusion_and_evidence_coverage():
    """未知度超 θ_excl 的指标被排除，权重重归一，覆盖率反映原始权重。"""

    model = EDQSGModel()
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "准确性", Domain.DATA_QUALITY, (ev("E1", (1, 0, 0, 0, 0), 0.4),)),
            Indicator("DQ2", "完整性", Domain.DATA_QUALITY, (ev("E2", (1, 0, 0, 0, 0)),)),
            Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E3", (1, 0, 0, 0, 0)),)),
        ],
        dq_weights={"DQ1": 0.5, "DQ2": 0.5},
        sg_weights={"SG1": 1},
    )
    assert "DQ1" in report.excluded_indicator_ids
    assert report.dq.evidence_coverage == pytest.approx(0.5)
    assert report.evidence_coverage == pytest.approx(0.5)
    # 仅 DQ2 参与，权重重归一为 1，域得分等于 DQ2 得分。
    assert report.dq.score == pytest.approx(100.0)


def test_root_cause_excludes_insufficient_evidence():
    """证据不足复核指标不进入根因计算（式(12)参与条件）。"""

    from edqsg import CouplingCalibrationInput

    model = EDQSGModel()
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "准确性", Domain.DATA_QUALITY, (ev("E1", (0, 0, 0, 0, 1), 0.55),)),
            Indicator("DQ2", "完整性", Domain.DATA_QUALITY, (ev("E2", (0, 0, 0, 0, 1)),)),
            Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E3", (0, 0, 0, 1, 0)),)),
        ],
        dq_weights={"DQ1": 0.5, "DQ2": 0.5},
        sg_weights={"SG1": 1},
        coupling_calibrations=[
            CouplingCalibrationInput("DQ1", "SG1", normative_strength=0.8, normative_confidence=0.75),
            CouplingCalibrationInput("DQ2", "SG1", normative_strength=0.8, normative_confidence=0.75),
        ],
    )
    root = report.root_causes[0]
    assert root.affected_dq_ids == ("DQ2",)
    # RC = (1−0.5)×[0.8×0.75×0.5×0.8×1.0]，DQ1 被复核排除不计入。
    assert root.contribution == pytest.approx(0.5 * 0.8 * 0.75 * 0.5 * 0.8)


def test_root_cause_below_threshold_flagged():
    """RC 低于 θ_RC=0.01 时标记 below_threshold，不生成治理任务。"""

    from edqsg import CouplingCalibrationInput, GovernanceTemplate, TaskLayer

    model = EDQSGModel()
    template = GovernanceTemplate(
        template_id="TPL-SG1",
        sg_indicator_id="SG1",
        bottom_line_rule_id=None,
        target_object="键与约束",
        root_cause="缺少约束",
        lifecycle_stage="设计",
        measures=("增加约束",),
        actors=("DBA",),
        acceptance_metrics={"约束覆盖率": 1.0},
        task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
        severity=0.8,
        impact=0.9,
        urgency=0.8,
        cost=0.4,
    )
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "准确性", Domain.DATA_QUALITY, (ev("E1", (1, 0, 0, 0, 0), 0.99),)),
            Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E2", (0, 0, 0, 0, 1), 0.99),)),
        ],
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
        coupling_calibrations=[
            CouplingCalibrationInput("DQ1", "SG1", normative_strength=1.0, normative_confidence=1.0),
        ],
        governance_templates=[template],
    )
    root = report.root_causes[0]
    assert root.below_threshold is True
    assert not report.governance_tasks
