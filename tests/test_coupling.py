import pytest

from edqsg import CouplingCalibrationInput, EDQSGConfig
from edqsg.coupling import CouplingCalibrator


def test_three_source_calibration():
    cfg = EDQSGConfig()
    calibrator = CouplingCalibrator(
        cfg.coupling_strength_weights,
        cfg.coupling_confidence_weights,
    )
    relation = calibrator.calibrate(
        CouplingCalibrationInput(
            dq_indicator_id="DQ1",
            sg_indicator_id="SG1",
            normative_strength=0.8,
            expert_strength=0.6,
            data_strength=0.4,
            normative_confidence=0.9,
            expert_confidence=0.8,
            data_confidence=0.7,
        )
    )
    # 模型 7.1 节：三源权重缺省等权 1/3。
    assert relation.strength == pytest.approx(0.6)
    assert relation.confidence == pytest.approx(0.8)
    # 模型 7.1 节：三源极差 0.4 > θ_src(0.2)，标记“待确认”。
    assert relation.pending is True


def test_missing_source_is_reweighted():
    calibrator = CouplingCalibrator((0.35, 0.35, 0.30), (0.35, 0.35, 0.30))
    relation = calibrator.calibrate(
        CouplingCalibrationInput(
            "DQ1",
            "SG1",
            normative_strength=0.8,
            expert_strength=0.6,
            normative_confidence=0.9,
            expert_confidence=0.7,
        )
    )
    assert relation.strength == pytest.approx(0.7)
    assert relation.confidence == pytest.approx(0.8)
    # 两源极差 0.2 未超过 θ_src=0.2，不标记“待确认”。
    assert relation.pending is False


def test_smooth_update():
    assert CouplingCalibrator.smooth_update(0.4, 0.8, 0.25) == pytest.approx(0.5)
