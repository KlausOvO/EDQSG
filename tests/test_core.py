import math

import pytest

from edqsg import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    Domain,
    EDQSGModel,
    Evidence,
    EvidenceType,
    GovernanceTemplate,
    Indicator,
    TaskLayer,
)


def ev(eid, score):
    return Evidence(
        evidence_id=eid,
        evidence_type=EvidenceType.DATA,
        source="unit-test",
        coverage=1,
        authority=1,
        timeliness=1,
        repeatability=1,
        business_fit=1,
        observed_score=score,
    )


def template():
    return GovernanceTemplate(
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


def test_full_model_without_bottom_line():
    model = EDQSGModel()
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "唯一性", Domain.DATA_QUALITY, (ev("E1", 80),)),
            Indicator("SG1", "键与约束", Domain.STRUCTURAL_GOVERNANCE, (ev("E2", 60),)),
        ],
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
        coupling_calibrations=[
            CouplingCalibrationInput(
                "DQ1", "SG1",
                normative_strength=0.9,
                expert_strength=0.8,
                data_strength=0.7,
                normative_confidence=0.9,
                expert_confidence=0.8,
                data_confidence=0.7,
            )
        ],
        governance_templates=[template()],
    )
    assert report.initial_score == pytest.approx(math.sqrt(80 * 60))
    assert report.final_score == report.initial_score
    # 式(8)：双域协同度 = (min(Q,S)/100)·(1−|Q−S|/100)
    assert report.balance == pytest.approx(0.6 * (1.0 - 20.0 / 100.0))
    # 式(12)：RC 不再整体乘以 c_j^S；式(13)：归一化占比之和为 1。
    assert report.root_causes[0].contribution == pytest.approx(
        0.4 * 0.8 * 0.8 * 1.0 * 0.2
    )
    assert report.root_causes[0].normalized_contribution == pytest.approx(1.0)
    assert report.governance_tasks


def test_grade_boundaries_follow_paper():
    from edqsg.scoring import ScoreCalculator
    from edqsg.models import Grade

    boundaries = (92.5, 77.5, 60.0, 35.0)
    # 模型 6.1 节：优 (92.5,100]、良 (77.5,92.5]、中 (60,77.5]、
    # 较差 (35,60]、差 ≤35。
    assert ScoreCalculator.grade(100.0, boundaries) is Grade.EXCELLENT
    assert ScoreCalculator.grade(92.5, boundaries) is Grade.GOOD
    assert ScoreCalculator.grade(77.5, boundaries) is Grade.MEDIUM
    assert ScoreCalculator.grade(60.0, boundaries) is Grade.POOR
    assert ScoreCalculator.grade(60.1, boundaries) is Grade.MEDIUM
    assert ScoreCalculator.grade(35.0, boundaries) is Grade.BAD
    assert ScoreCalculator.grade(35.1, boundaries) is Grade.POOR


def test_bottom_line_task_is_prioritized():
    model = EDQSGModel()
    bottom_template = GovernanceTemplate(
        template_id="TPL-BL1",
        sg_indicator_id=None,
        bottom_line_rule_id="BL1",
        target_object="核心器材编码",
        root_cause="核心标识不可用",
        lifecycle_stage="创建",
        measures=("修复核心标识",),
        actors=("主数据管理员",),
        acceptance_metrics={"唯一标识覆盖率": 1.0},
        task_layer=TaskLayer.DATA_REPAIR,
        severity=1,
        impact=1,
        urgency=1,
        cost=0.5,
    )
    report = model.evaluate(
        indicators=[
            Indicator("DQ1", "唯一性", Domain.DATA_QUALITY, (ev("E1", 80),)),
            Indicator("SG1", "键与约束", Domain.STRUCTURAL_GOVERNANCE, (ev("E2", 60),)),
        ],
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
        bottom_line_triggers=[BottomLineTrigger("BL1", "核心标识缺失", cap=50)],
        governance_templates=[bottom_template],
    )
    assert report.final_score == 50
    assert report.governance_tasks[0].bottom_line is True
