import pytest

from edqsg.weights import combine_weights, critic_weights


def test_critic_returns_normalized_weights():
    result = critic_weights(
        [[60, 80], [70, 75], [90, 65], [85, 70]],
        ["I1", "I2"],
    )
    assert sum(result.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in result.values())


def test_combine_weights():
    result = combine_weights(
        {"I1": 0.8, "I2": 0.2},
        {"I1": 0.4, "I2": 0.6},
        0.5,
    )
    assert result["I1"] == pytest.approx(0.6)
    assert result["I2"] == pytest.approx(0.4)
