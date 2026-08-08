"""[CORE] 可靠性折扣与证据推理。

实现说明：
1. 单条证据先依据覆盖度、权威性、时效性、可重复性和业务适配性计算可靠性；
2. 证据重要性与可靠性相乘形成有效可靠性；
3. 低可靠性质量转入未知状态；
4. 多项证据使用递归 Dempster-Shafer/ER 组合；
5. 高冲突证据不会被静默平均，而会标记为需要复核。
"""

import math
from collections.abc import Sequence

import numpy as np

from .models import Evidence, EvidenceAssessment, Indicator, IndicatorAssessment
from .validators import (
    normalize_vector,
    validate_belief_distribution,
    validate_score,
    validate_unit_interval,
)


class EvidenceFusionEngine:
    """将多源证据融合为等级置信分布、得分与可信度。"""

    def __init__(
        self,
        eta: Sequence[float],
        grade_utilities: Sequence[float],
        conflict_review_threshold: float = 0.55,
        conflict_extreme_threshold: float = 0.98,
        insufficient_review_threshold: float = 0.3,
    ):
        self.eta = normalize_vector(eta, "证据可靠性权重eta")
        if len(self.eta) != 5:
            raise ValueError("证据可靠性权重eta必须为五维。")
        utilities = np.asarray(grade_utilities, dtype=float)
        if utilities.shape != (5,) or np.any(~np.isfinite(utilities)):
            raise ValueError("等级效用值必须为五维有限数。")
        if not np.all(np.diff(utilities) < 0):
            raise ValueError("等级效用值必须按优到差严格递减。")
        self.utilities = utilities
        self.conflict_review_threshold = validate_unit_interval(
            conflict_review_threshold, "conflict_review_threshold"
        )
        self.conflict_extreme_threshold = validate_unit_interval(
            conflict_extreme_threshold, "conflict_extreme_threshold"
        )
        if self.conflict_extreme_threshold <= self.conflict_review_threshold:
            raise ValueError("极端冲突阈值必须大于复核冲突阈值。")
        self.insufficient_review_threshold = validate_unit_interval(
            insufficient_review_threshold, "insufficient_review_threshold"
        )

    def reliability(self, evidence: Evidence) -> float:
        """计算单条证据可靠性 r_ie。"""

        features = np.array(
            [
                validate_unit_interval(evidence.coverage, "coverage"),
                validate_unit_interval(evidence.authority, "authority"),
                validate_unit_interval(evidence.timeliness, "timeliness"),
                validate_unit_interval(evidence.repeatability, "repeatability"),
                validate_unit_interval(evidence.business_fit, "business_fit"),
            ],
            dtype=float,
        )
        return float(np.dot(self.eta, features))

    def score_to_beliefs(self, score: float) -> tuple[float, float, float, float, float]:
        """将数值分数线性映射为相邻等级的支持分布。"""

        value = validate_score(score)
        utilities = self.utilities
        result = np.zeros(5, dtype=float)
        if value >= utilities[0]:
            result[0] = 1.0
        elif value <= utilities[-1]:
            result[-1] = 1.0
        else:
            for index in range(4):
                high, low = utilities[index], utilities[index + 1]
                if high >= value >= low:
                    span = high - low
                    result[index] = (value - low) / span
                    result[index + 1] = (high - value) / span
                    break
        return tuple(float(x) for x in result)

    def _raw_distribution(self, evidence: Evidence) -> tuple[np.ndarray, float]:
        if evidence.belief_degrees is not None:
            return validate_belief_distribution(
                evidence.belief_degrees,
                evidence.unknown_degree,
                evidence.evidence_id,
            )
        if evidence.observed_score is None:
            raise ValueError(
                f"证据{evidence.evidence_id}必须提供belief_degrees或observed_score。"
            )
        beliefs = np.asarray(self.score_to_beliefs(evidence.observed_score), dtype=float)
        if evidence.unknown_degree is not None:
            unknown = validate_unit_interval(
                evidence.unknown_degree, f"{evidence.evidence_id}.unknown_degree"
            )
        else:
            # 模型 3.4 节：初始未知度 β_U^0 = 1 − C_sample·C_rule，
            # 样本覆盖（数据都扫描了）与规则可观测度（缺陷都能被检测）分开度量；
            # C_sample 与可靠性属性中的 coverage（证据完整性）概念不同，不重复折扣。
            sample_coverage = validate_unit_interval(
                evidence.sample_coverage, f"{evidence.evidence_id}.sample_coverage"
            )
            rule_obs = validate_unit_interval(
                evidence.rule_observability, f"{evidence.evidence_id}.rule_observability"
            )
            unknown = 1.0 - sample_coverage * rule_obs
        if unknown > 0:
            beliefs = beliefs * (1.0 - unknown)
        return beliefs, unknown

    def discount(self, evidence: Evidence) -> EvidenceAssessment:
        """执行可靠性折扣，将低可靠性质量转入未知状态。"""

        reliability = self.reliability(evidence)
        # 模型式(2)：折扣系数取证据可靠性 r_e（论文口径不含 importance）。
        effective = reliability
        beliefs, unknown = self._raw_distribution(evidence)
        discounted = effective * beliefs
        discounted_unknown = 1.0 - float(discounted.sum())
        # 原始未知度已包含在1-sum(discounted)中，保持总质量为1。
        return EvidenceAssessment(
            evidence_id=evidence.evidence_id,
            evidence_type=evidence.evidence_type,
            reliability=reliability,
            effective_reliability=effective,
            discounted_beliefs=tuple(float(x) for x in discounted),
            discounted_unknown=float(discounted_unknown),
        )

    @staticmethod
    def _conflict(m1: np.ndarray, m2: np.ndarray) -> float:
        diagonal = float(np.dot(m1, m2))
        return float(max(0.0, m1.sum() * m2.sum() - diagonal))

    @staticmethod
    def _jousselme_distance(
        beliefs1: np.ndarray,
        unknown1: float,
        beliefs2: np.ndarray,
        unknown2: float,
    ) -> float:
        """式(4)：两个证据体（五个等级+未知）之间的 Jousselme 距离。

        识别框架取五个等级单点与全集Θ，焦元相似矩阵 D(A,B)=|A∩B|/|A∪B|：
        D(单点, 单点)=1（相同）或0（不同），D(单点, Θ)=1/5，D(Θ, Θ)=1，
        代入 d=√(0.5·(m1−m2)ᵀ·D·(m1−m2)) 得到闭式解，交叉项系数为 2/5。
        """

        delta = np.asarray(beliefs1, dtype=float) - np.asarray(beliefs2, dtype=float)
        delta_unknown = float(unknown1 - unknown2)
        squared = 0.5 * (
            float(np.dot(delta, delta))
            + (2.0 / 5.0) * delta_unknown * float(delta.sum())
            + delta_unknown * delta_unknown
        )
        return float(math.sqrt(max(0.0, squared)))

    def _combine_two(
        self,
        beliefs1: np.ndarray,
        unknown1: float,
        beliefs2: np.ndarray,
        unknown2: float,
    ) -> tuple[np.ndarray, float, float, bool]:
        """组合两项折扣证据，返回信念、未知、冲突及极端冲突标记。"""

        ds_conflict = self._conflict(beliefs1, beliefs2)
        j_distance = self._jousselme_distance(beliefs1, unknown1, beliefs2, unknown2)
        extreme = ds_conflict >= self.conflict_extreme_threshold
        if extreme:
            # 高冲突时采用保守线性池，并将冲突质量转入未知，避免1-K接近0。
            pooled = 0.5 * (beliefs1 + beliefs2) * (1.0 - ds_conflict)
            unknown = max(0.0, 1.0 - float(pooled.sum()))
            return pooled, unknown, j_distance, True

        denominator = 1.0 - ds_conflict
        combined = (
            beliefs1 * beliefs2
            + beliefs1 * unknown2
            + unknown1 * beliefs2
        ) / denominator
        unknown = (unknown1 * unknown2) / denominator
        # 数值误差修正。
        total = float(combined.sum() + unknown)
        if total <= 0:
            return np.zeros(5), 1.0, j_distance, False
        combined /= total
        unknown /= total
        return combined, float(unknown), j_distance, False

    def fuse(self, indicator: Indicator) -> IndicatorAssessment:
        """融合单项指标的全部证据。"""

        if indicator.base_score is not None:
            validate_score(indicator.base_score, f"{indicator.indicator_id}.base_score")

        if not indicator.evidences:
            if indicator.base_score is None:
                raise ValueError(f"指标{indicator.indicator_id}既无证据也无base_score。")
            return IndicatorAssessment(
                indicator_id=indicator.indicator_id,
                name=indicator.name,
                domain=indicator.domain,
                score=float(indicator.base_score),
                confidence=0.0,
                belief_degrees=(0.0, 0.0, 0.0, 0.0, 0.0),
                unknown_degree=1.0,
                conflict_degree=0.0,
                evidence_ids=(),
                review_required=True,
                review_reason="仅有基础分值，缺少可追溯证据。",
                evidence_results=(),
                review_state="insufficient_evidence",
            )

        discounted = [self.discount(item) for item in indicator.evidences]
        beliefs = np.asarray(discounted[0].discounted_beliefs, dtype=float)
        unknown = discounted[0].discounted_unknown
        conflicts: list[float] = []
        extreme = False
        for item in discounted[1:]:
            beliefs, unknown, conflict, is_extreme = self._combine_two(
                beliefs,
                unknown,
                np.asarray(item.discounted_beliefs, dtype=float),
                item.discounted_unknown,
            )
            conflicts.append(conflict)
            extreme = extreme or is_extreme

        conflict_degree = float(max(conflicts)) if conflicts else 0.0
        # 式(3)：分数只在已知证据条件下计算，未知度不压低分数。
        known = 1.0 - float(unknown)
        score = float(np.dot(beliefs, self.utilities))
        if known > 1e-12:
            score /= known
        else:
            score = 0.0
        # 模型 6.1 节：指标可信度 c_i = 1 − β_U，冲突单独输出。
        confidence = float(1.0 - unknown)
        conflict_review = extreme or conflict_degree >= self.conflict_review_threshold
        insufficient_review = unknown >= self.insufficient_review_threshold
        if conflict_review:
            review_state = "conflict"
        elif insufficient_review:
            review_state = "insufficient_evidence"
        else:
            review_state = "none"
        review_required = review_state != "none"
        if extreme:
            reason = "存在极端证据冲突，已采用保守组合，需人工复核。"
        elif conflict_review:
            reason = "证据冲突超过复核阈值，需核查口径、时间窗口和业务语义。"
        elif insufficient_review:
            reason = "指标未知度超过证据不足复核门槛，需补充证据。"
        else:
            reason = ""

        return IndicatorAssessment(
            indicator_id=indicator.indicator_id,
            name=indicator.name,
            domain=indicator.domain,
            score=score,
            confidence=confidence,
            belief_degrees=tuple(float(x) for x in beliefs),
            unknown_degree=float(unknown),
            conflict_degree=conflict_degree,
            evidence_ids=tuple(item.evidence_id for item in indicator.evidences),
            review_required=review_required,
            review_reason=reason,
            evidence_results=tuple(discounted),
            review_state=review_state,
        )
