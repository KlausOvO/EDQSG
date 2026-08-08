"""双域评价、综合评价、可信度和平衡度计算。"""

import math
from collections.abc import Mapping, Sequence

import numpy as np

from .models import DomainAssessment, Grade, IndicatorAssessment
from .validators import validate_unit_interval, validate_weight_mapping


class ScoreCalculator:
    """EDQSG 双域与综合评价计算器。"""

    @staticmethod
    def domain_assessment(
        indicators: Sequence[IndicatorAssessment],
        weights: Mapping[str, float],
        name: str,
        evidence_coverage: float = 1.0,
    ) -> DomainAssessment:
        if not indicators:
            raise ValueError(f"{name}至少需要一个指标。")
        ids = [item.indicator_id for item in indicators]
        normalized = validate_weight_mapping(weights, ids, f"{name}权重")
        score = sum(normalized[item.indicator_id] * item.score for item in indicators)
        confidence = sum(
            normalized[item.indicator_id] * item.confidence for item in indicators
        )
        beliefs = np.zeros(5, dtype=float)
        unknown = 0.0
        conflict = 0.0
        for item in indicators:
            weight = normalized[item.indicator_id]
            beliefs += weight * np.asarray(item.belief_degrees, dtype=float)
            unknown += weight * item.unknown_degree
            conflict += weight * item.conflict_degree
        return DomainAssessment(
            score=float(score),
            confidence=float(confidence),
            belief_degrees=tuple(float(x) for x in beliefs),
            unknown_degree=float(unknown),
            conflict_degree=float(conflict),
            evidence_coverage=validate_unit_interval(evidence_coverage, "证据覆盖率"),
        )

    @staticmethod
    def combine(
        dq: DomainAssessment,
        sg: DomainAssessment,
        alpha: float,
    ) -> tuple[float, float, float]:
        alpha = validate_unit_interval(alpha, "alpha")
        initial = float((dq.score**alpha) * (sg.score ** (1.0 - alpha)))
        # 式(8)：双域协同度同时反映健康水平与对称程度，
        # 两域同低或一高一低时均趋近 0。
        balance = float(
            (min(dq.score, sg.score) / 100.0)
            * (1.0 - abs(dq.score - sg.score) / 100.0)
        )
        # 模型式(6)：综合可信度 c^G = (c^Q·c^S)^{1/2}。
        overall_confidence = float(
            math.sqrt(max(0.0, dq.confidence) * max(0.0, sg.confidence))
        )
        return initial, balance, overall_confidence

    @staticmethod
    def grade(score: float, boundaries: Sequence[float]) -> Grade:
        if len(boundaries) != 4:
            raise ValueError("等级边界必须为四维。")
        b1, b2, b3, b4 = (float(x) for x in boundaries)
        if not (100 >= b1 > b2 > b3 > b4 >= 0):
            raise ValueError("等级边界必须严格递减且位于[0,100]。")
        # 模型 6.1 节：优 (92.5,100]、良 (77.5,92.5]、中 (60,77.5]、
        # 较差 (35,60]、差 ≤35，因此边界采用严格大于。
        if score > b1:
            return Grade.EXCELLENT
        if score > b2:
            return Grade.GOOD
        if score > b3:
            return Grade.MEDIUM
        if score > b4:
            return Grade.POOR
        return Grade.BAD
