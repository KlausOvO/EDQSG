"""[CORE] Q-S耦合校准与根因贡献度。
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

import numpy as np

from .models import (
    CouplingCalibrationInput,
    CouplingRelation,
    IndicatorAssessment,
    RootCauseResult,
)
from .validators import normalize_vector, require_unique, validate_unit_interval


class CouplingCalibrator:
    """融合规范机制、专家判断和历史数据，形成耦合强度与可信度。"""

    SOURCE_NAMES = ("normative", "expert", "data")

    def __init__(
        self,
        strength_weights: Sequence[float],
        confidence_weights: Sequence[float],
        disagreement_threshold: float = 0.2,
    ):
        self.strength_weights = normalize_vector(strength_weights, "耦合强度三源权重")
        self.confidence_weights = normalize_vector(confidence_weights, "耦合可信度三源权重")
        if len(self.strength_weights) != 3 or len(self.confidence_weights) != 3:
            raise ValueError("耦合三源权重必须为三维。")
        self.disagreement_threshold = validate_unit_interval(
            disagreement_threshold, "耦合三源分歧阈值θ_src"
        )

    @staticmethod
    def _available_weighted_average(
        values: Sequence[float | None],
        weights: np.ndarray,
        name: str,
    ) -> tuple[float, tuple[tuple[str, float], ...]]:
        available_values: list[float] = []
        available_weights: list[float] = []
        items: list[tuple[str, float]] = []
        for source, value, weight in zip(CouplingCalibrator.SOURCE_NAMES, values, weights, strict=True):
            if value is None:
                continue
            checked = validate_unit_interval(value, f"{name}.{source}")
            available_values.append(checked)
            available_weights.append(float(weight))
            items.append((source, checked))
        if not available_values:
            raise ValueError(f"{name}至少需要一个来源。")
        normalized = normalize_vector(available_weights, f"{name}可用来源权重")
        return float(np.dot(normalized, available_values)), tuple(items)

    def calibrate(self, item: CouplingCalibrationInput) -> CouplingRelation:
        strength, source_strengths = self._available_weighted_average(
            [item.normative_strength, item.expert_strength, item.data_strength],
            self.strength_weights,
            "coupling_strength",
        )
        # 模型 7.1 节：三源分歧（极差）超过 θ_src 时标记“待确认”。
        available_strengths = [
            value
            for value in (item.normative_strength, item.expert_strength, item.data_strength)
            if value is not None
        ]
        # 加 1e-9 容差，避免 0.9−0.7=0.20000000000000007 这类浮点边界误判。
        pending = bool(available_strengths) and (
            max(available_strengths) - min(available_strengths)
            > self.disagreement_threshold + 1e-9
        )
        confidence_values = [
            item.normative_confidence,
            item.expert_confidence,
            item.data_confidence,
        ]
        # 若某来源提供强度但未提供可信度，采用保守默认值0.5；未提供强度的来源不参与。
        strength_values = [item.normative_strength, item.expert_strength, item.data_strength]
        adjusted_confidences = [
            None if strength is None else (0.5 if conf is None else conf)
            for strength, conf in zip(strength_values, confidence_values, strict=True)
        ]
        confidence, source_confidences = self._available_weighted_average(
            adjusted_confidences,
            self.confidence_weights,
            "coupling_confidence",
        )
        return CouplingRelation(
            dq_indicator_id=item.dq_indicator_id,
            sg_indicator_id=item.sg_indicator_id,
            strength=strength,
            confidence=confidence,
            evidence_ids=item.evidence_ids,
            source_strengths=source_strengths,
            source_confidences=source_confidences,
            pending=pending,
        )

    def calibrate_many(
        self, items: Sequence[CouplingCalibrationInput]
    ) -> list[CouplingRelation]:
        require_unique(
            items,
            lambda item: (item.dq_indicator_id, item.sg_indicator_id),
            "耦合校准输入",
        )
        return [self.calibrate(item) for item in items]

    @staticmethod
    def smooth_update(old_strength: float, observed_strength: float, gamma: float) -> float:
        old = validate_unit_interval(old_strength, "old_strength")
        observed = validate_unit_interval(observed_strength, "observed_strength")
        rate = validate_unit_interval(gamma, "gamma")
        return float((1.0 - rate) * old + rate * observed)


class CouplingAnalyzer:
    """根据结构缺陷和质量缺陷计算根因贡献度。"""

    @staticmethod
    def analyze(
        dq: Sequence[IndicatorAssessment],
        sg: Sequence[IndicatorAssessment],
        dq_weights: Mapping[str, float],
        relations: Sequence[CouplingRelation],
        threshold: float = 0.0,
    ) -> list[RootCauseResult]:
        dq_map = {item.indicator_id: item for item in dq}
        sg_map = {item.indicator_id: item for item in sg}
        require_unique(
            relations,
            lambda item: (item.dq_indicator_id, item.sg_indicator_id),
            "耦合关系",
        )

        grouped: dict[str, list[CouplingRelation]] = {}
        for relation in relations:
            if relation.dq_indicator_id not in dq_map:
                raise ValueError(f"未知数据质量指标：{relation.dq_indicator_id}。")
            if relation.sg_indicator_id not in sg_map:
                raise ValueError(f"未知结构治理指标：{relation.sg_indicator_id}。")
            validate_unit_interval(relation.strength, "coupling.strength")
            validate_unit_interval(relation.confidence, "coupling.confidence")
            grouped.setdefault(relation.sg_indicator_id, []).append(relation)

        results: list[RootCauseResult] = []
        for sg_id, sg_item in sg_map.items():
            total = 0.0
            affected: list[str] = []
            details: list[tuple[str, float]] = []
            evidence_ids: set[str] = set(sg_item.evidence_ids)
            relation_confidences: list[float] = []
            for relation in grouped.get(sg_id, []):
                # 机制先行（模型 7.1 节）：候选关系必须具有规范机制来源。
                source_names = {name for name, _ in relation.source_strengths}
                if "normative" not in source_names:
                    continue
                # 三源分歧超阈值的关系标记“待确认”，不参与根因计算。
                if relation.pending:
                    continue
                # 参与门槛（模型 7.2 节）：c_ij ≥ 0.6 且 c_i^Q ≥ 0.5。
                if relation.confidence < 0.6:
                    continue
                dq_item = dq_map[relation.dq_indicator_id]
                if dq_item.confidence < 0.5:
                    continue
                # 模型 3.5 节：证据不足复核与冲突复核均不作为根因诊断的
                # 确认证据，不参与式(12)计算。
                if dq_item.review_state in ("insufficient_evidence", "conflict"):
                    continue
                # 模型 3.5/7.2 节：结构侧指标进入证据不足复核时同样不作为正式
                # 根因排名的依据（标注为待确认根因），不参与式(12)计算。
                if sg_item.review_state in ("insufficient_evidence", "conflict"):
                    break
                # 模型式(12)：单项贡献 = a_ij·c_ij·w_i^Q·D_i，
                # D_i = (1−s_i^Q/100)·c_i^Q。
                part = (
                    relation.strength
                    * relation.confidence
                    * dq_weights[relation.dq_indicator_id]
                    * (1.0 - dq_item.score / 100.0)
                    * dq_item.confidence
                )
                total += part
                affected.append(relation.dq_indicator_id)
                details.append((relation.dq_indicator_id, float(part)))
                evidence_ids.update(relation.evidence_ids)
                relation_confidences.append(relation.confidence)

            # 模型式(12)：RC_j = (1−s_j^S/100)·Σ[a·c·w·D]，
            # 不再整体乘以 c_j^S（避免三重可信度连乘）。
            contribution = (
                (1.0 - sg_item.score / 100.0)
                * total
            )
            # 模型 7.2 节：c_j^S < 0.5 或结构侧进入复核时视为证据不足，标记低可信候选。
            low_confidence = (
                sg_item.confidence < 0.5 or sg_item.review_state != "none"
            )
            relation_conf = float(np.mean(relation_confidences)) if relation_confidences else 0.0
            root_confidence = float(sg_item.confidence * relation_conf)
            results.append(
                RootCauseResult(
                    sg_indicator_id=sg_id,
                    contribution=float(contribution),
                    confidence=root_confidence,
                    affected_dq_ids=tuple(sorted(set(affected))),
                    affected_contributions=tuple(sorted(details, key=lambda x: x[1], reverse=True)),
                    evidence_ids=tuple(sorted(evidence_ids)),
                    low_confidence=low_confidence,
                    below_threshold=float(contribution) < float(threshold),
                )
            )

        # 模型式(13)：归一化贡献占比 ρ_j = RC_j / ΣRC_k。
        total_contribution = sum(item.contribution for item in results)
        if total_contribution > 0:
            results = [
                replace(
                    item,
                    normalized_contribution=item.contribution / total_contribution,
                )
                for item in results
            ]
        # 低可信候选与低于诊断充分性门槛的候选不进入前 K 排序，排在正常结果之后。
        return sorted(
            results,
            key=lambda item: (item.low_confidence or item.below_threshold, -item.contribution),
        )
