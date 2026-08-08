"""主客观组合权重与 CRITIC 客观赋权。"""

from collections.abc import Mapping, Sequence

import numpy as np

from .validators import normalize_vector, validate_unit_interval, validate_weight_mapping


def critic_weights(matrix: Sequence[Sequence[float]], indicator_ids: Sequence[str]) -> dict[str, float]:
    """使用 CRITIC 法计算客观权重。

    ``matrix`` 的行表示评价单元，列表示指标。所有指标默认均为效益型；
    成本型指标应在调用前转换为效益型分值。
    """

    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(indicator_ids):
        raise ValueError("CRITIC矩阵列数必须与指标数量一致。")
    if values.shape[0] < 2:
        raise ValueError("CRITIC至少需要两个评价单元。")
    if np.any(~np.isfinite(values)):
        raise ValueError("CRITIC矩阵不能包含NaN或无穷值。")

    min_v = values.min(axis=0)
    max_v = values.max(axis=0)
    spans = max_v - min_v
    normalized = np.zeros_like(values, dtype=float)
    non_constant = spans > 0
    normalized[:, non_constant] = (
        values[:, non_constant] - min_v[non_constant]
    ) / spans[non_constant]
    normalized[:, ~non_constant] = 0.5

    std = normalized.std(axis=0, ddof=1)
    corr = np.corrcoef(normalized, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    conflict = np.sum(1.0 - corr, axis=1)
    information = std * conflict
    if float(information.sum()) <= 1e-12:
        weights = np.ones(len(indicator_ids), dtype=float) / len(indicator_ids)
    else:
        weights = information / information.sum()
    return dict(zip(indicator_ids, (float(x) for x in weights), strict=True))


def combine_weights(
    subjective: Mapping[str, float],
    objective: Mapping[str, float],
    subjective_ratio: float,
) -> dict[str, float]:
    """组合主观权重与客观权重。"""

    ratio = validate_unit_interval(subjective_ratio, "subjective_ratio")
    ids = list(subjective)
    s = validate_weight_mapping(subjective, ids, "主观权重")
    o = validate_weight_mapping(objective, ids, "客观权重")
    combined = {item_id: ratio * s[item_id] + (1.0 - ratio) * o[item_id] for item_id in ids}
    vector = normalize_vector([combined[item_id] for item_id in ids], "组合权重")
    return dict(zip(ids, (float(x) for x in vector), strict=True))
