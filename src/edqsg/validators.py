"""模型参数校验工具。"""

from collections.abc import Mapping, Sequence
from typing import TypeVar

import numpy as np

T = TypeVar("T")


def validate_score(value: float, name: str = "score") -> float:
    value = float(value)
    if not np.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError(f"{name}必须位于[0,100]，当前值为{value}。")
    return value


def validate_unit_interval(value: float, name: str, tolerance: float = 1e-9) -> float:
    value = float(value)
    if not np.isfinite(value) or not 0.0 <= value <= 1.0 + tolerance:
        raise ValueError(f"{name}必须位于[0,1]，当前值为{value}。")
    return min(value, 1.0)


def normalize_vector(values: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0:
        raise ValueError(f"{name}必须是一维非空向量。")
    if np.any(~np.isfinite(array)) or np.any(array < 0):
        raise ValueError(f"{name}必须由有限非负数构成。")
    total = float(array.sum())
    if total <= 0:
        raise ValueError(f"{name}的元素和必须大于0。")
    return array / total


def validate_weight_mapping(
    weights: Mapping[str, float],
    expected_ids: Sequence[str],
    name: str,
) -> dict[str, float]:
    expected = set(expected_ids)
    actual = set(weights)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{name}的指标ID不匹配，缺失={missing}，多余={extra}。")
    normalized = normalize_vector([weights[item_id] for item_id in expected_ids], name)
    return dict(zip(expected_ids, normalized, strict=True))


def validate_belief_distribution(
    beliefs: Sequence[float],
    unknown: float | None,
    name: str,
    tolerance: float = 1e-9,
) -> tuple[np.ndarray, float]:
    values = np.asarray(beliefs, dtype=float)
    if values.shape != (5,):
        raise ValueError(f"{name}.belief_degrees必须为五维。")
    if np.any(~np.isfinite(values)) or np.any(values < 0) or np.any(values > 1):
        raise ValueError(f"{name}.belief_degrees必须位于[0,1]。")
    known_sum = float(values.sum())
    if known_sum > 1.0 + tolerance:
        raise ValueError(f"{name}的确定等级支持度之和不能超过1。")
    if unknown is None:
        unknown_value = max(0.0, 1.0 - known_sum)
    else:
        unknown_value = validate_unit_interval(unknown, f"{name}.unknown_degree")
        if abs(known_sum + unknown_value - 1.0) > 1e-6:
            raise ValueError(f"{name}的确定等级支持度与未知度之和必须为1。")
    return values, unknown_value


def require_unique(items: Sequence[T], key, name: str) -> None:
    seen = set()
    duplicates = set()
    for item in items:
        item_key = key(item)
        if item_key in seen:
            duplicates.add(item_key)
        seen.add(item_key)
    if duplicates:
        raise ValueError(f"{name}存在重复标识：{sorted(duplicates)}。")
