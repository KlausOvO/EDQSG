import pytest

from edqsg import Domain, EDQSGConfig, Evidence, EvidenceType, Indicator
from edqsg.evidence import EvidenceFusionEngine


def engine():
    cfg = EDQSGConfig()
    return EvidenceFusionEngine(
        cfg.evidence_eta,
        cfg.grade_utilities,
        cfg.evidence_conflict_review_threshold,
        cfg.evidence_conflict_extreme_threshold,
    )


def evidence(eid, beliefs, importance=1.0, reliability=1.0):
    return Evidence(
        evidence_id=eid,
        evidence_type=EvidenceType.DATA,
        source="test",
        coverage=reliability,
        authority=reliability,
        timeliness=reliability,
        repeatability=reliability,
        business_fit=reliability,
        belief_degrees=beliefs,
        importance=importance,
    )


def test_single_certain_evidence():
    result = engine().fuse(
        Indicator("DQ1", "完整性", Domain.DATA_QUALITY, (evidence("E1", (1, 0, 0, 0, 0)),))
    )
    assert result.score == pytest.approx(100.0)
    assert result.confidence == pytest.approx(1.0)
    assert result.unknown_degree == pytest.approx(0.0)


def test_low_reliability_moves_mass_to_unknown():
    result = engine().fuse(
        Indicator("DQ1", "完整性", Domain.DATA_QUALITY, (evidence("E1", (1, 0, 0, 0, 0), reliability=0.5),))
    )
    assert result.unknown_degree == pytest.approx(0.5)
    # 式(3)：分数只在已知证据条件下计算，已知证据全部指向“优”，
    # 未知度不压低分数（原实现 score=Σβ·u，会把证据不足误判为质量差）。
    assert result.score == pytest.approx(100.0)
    assert result.confidence == pytest.approx(0.5)


def test_extreme_conflict_is_flagged_for_review():
    item = Indicator(
        "DQ1",
        "完整性",
        Domain.DATA_QUALITY,
        (
            evidence("E1", (1, 0, 0, 0, 0)),
            evidence("E2", (0, 0, 0, 0, 1)),
        ),
    )
    result = engine().fuse(item)
    assert result.review_required is True
    assert result.conflict_degree == pytest.approx(1.0)
    assert result.unknown_degree == pytest.approx(1.0)


def test_score_is_converted_to_adjacent_grade_beliefs():
    beliefs = engine().score_to_beliefs(77.5)
    assert beliefs == pytest.approx((0, 0.5, 0.5, 0, 0))
