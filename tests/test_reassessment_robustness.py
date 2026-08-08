from dataclasses import replace

from edqsg import Domain, EDQSGModel, Evidence, EvidenceType, Indicator


def ev(eid, score):
    return Evidence(
        evidence_id=eid,
        evidence_type=EvidenceType.DATA,
        source="test",
        coverage=0.9,
        authority=0.9,
        timeliness=0.9,
        repeatability=0.9,
        business_fit=0.9,
        observed_score=score,
    )


def inputs(dq_score, sg_score):
    return [
        Indicator("DQ1", "完整性", Domain.DATA_QUALITY, (ev("E1", dq_score),)),
        Indicator("SG1", "字段设计", Domain.STRUCTURAL_GOVERNANCE, (ev("E2", sg_score),)),
    ]


def test_reassessment_uses_new_evidence():
    model = EDQSGModel()
    before = model.evaluate(inputs(60, 50), {"DQ1": 1}, {"SG1": 1})
    after = model.evaluate(inputs(80, 75), {"DQ1": 1}, {"SG1": 1})
    result = model.compare(before, after)
    assert result.dq_change > 0
    assert result.sg_change > 0
    assert result.final_score_change > 0


def test_monte_carlo_is_bounded_and_reproducible():
    model = EDQSGModel()
    kwargs = dict(
        indicators=inputs(75, 65),
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
        iterations=20,
        perturbation=0.1,
        seed=7,
    )
    r1 = model.robustness(**kwargs)
    r2 = model.robustness(**kwargs)
    assert r1 == r2
    assert 0 <= r1.score_quantiles[0] <= r1.score_quantiles[2] <= 100
    assert 0 <= r1.grade_flip_rate <= 1


def test_deterministic_sensitivity_reports_one_factor_cases():
    model = EDQSGModel()
    report = model.sensitivity(
        indicators=inputs(75, 65),
        dq_weights={"DQ1": 1},
        sg_weights={"SG1": 1},
        perturbations=(0.8, 1.2),
        top_k=3,
    )
    assert report.baseline_score >= 0
    assert report.perturbations == (0.8, 1.2)
    assert any(item.parameter == "domain_alpha" for item in report.cases)
    assert any(item.parameter == "evidence_reliability:DQ1" for item in report.cases)
    assert 0 <= report.grade_flip_rate <= 1
    assert report.max_abs_score_change >= 0
