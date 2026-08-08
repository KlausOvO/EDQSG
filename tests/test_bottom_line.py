import pytest

from edqsg.bottom_line import BottomLineEngine
from edqsg.models import BottomLineTrigger


def test_no_trigger_does_not_limit_score():
    result = BottomLineEngine.apply(100.0, [])
    assert result.final_score == 100.0
    assert result.applied_cap == 100.0


def test_trigger_applies_strictest_cap_and_penalty():
    result = BottomLineEngine.apply(
        88.0,
        [
            BottomLineTrigger("BL1", "一级", cap=50, penalty=0),
            BottomLineTrigger("BL2", "重大惩罚", cap=100, penalty=5),
        ],
    )
    assert result.final_score == pytest.approx(45.0)
    assert result.applied_cap == 50.0
    assert result.total_penalty == 5.0


def test_total_penalty_is_capped_at_20():
    # 模型 6.3 节：P = 5 × min(n_P, 4)，单次评价最多扣 20 分。
    result = BottomLineEngine.apply(
        88.0,
        [
            BottomLineTrigger("BL1", "扣分1", cap=100, penalty=10),
            BottomLineTrigger("BL2", "扣分2", cap=100, penalty=10),
            BottomLineTrigger("BL3", "扣分3", cap=100, penalty=10),
        ],
    )
    assert result.final_score == pytest.approx(68.0)
    assert result.total_penalty == pytest.approx(20.0)
