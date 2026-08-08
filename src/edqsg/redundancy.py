"""字段冗余与表冗余候选识别及风险评价。"""

from collections.abc import Sequence

import numpy as np

from .models import RedundancyAssessment, RedundancyRiskLevel
from .validators import normalize_vector, validate_unit_interval


class RedundancyAnalyzer:
    """将“相似”与“有害冗余”分开评价。"""

    FIELD_FEATURES = (
        "名称相似度",
        "定义语义相似度",
        "类型兼容度",
        "值重合度",
        "函数依赖程度",
        "业务上下文相似度",
    )
    TABLE_FEATURES = (
        "字段集合相似度",
        "主键对象相似度",
        "记录内容重合度",
        "业务功能重合度",
        "血缘关系相似度",
        "调用程序与使用模式重合度",
    )

    def __init__(
        self,
        field_similarity_weights: Sequence[float],
        table_similarity_weights: Sequence[float],
        risk_weights: Sequence[float],
        risk_thresholds: Sequence[float],
    ):
        self.field_weights = normalize_vector(field_similarity_weights, "字段相似度权重")
        self.table_weights = normalize_vector(table_similarity_weights, "表相似度权重")
        self.risk_weights = normalize_vector(risk_weights, "冗余风险权重")
        if len(self.field_weights) != 6 or len(self.table_weights) != 6:
            raise ValueError("字段和表相似度权重必须为六维。")
        if len(self.risk_weights) != 4:
            raise ValueError("冗余风险权重必须为四维。")
        thresholds = tuple(float(x) for x in risk_thresholds)
        if len(thresholds) != 3 or not (0 <= thresholds[0] < thresholds[1] < thresholds[2] <= 1):
            raise ValueError("冗余风险阈值必须为[低,中,高]三维严格递增数。")
        self.risk_thresholds = thresholds

    def _similarity(self, features: Sequence[float], object_type: str) -> tuple[float, tuple[str, ...]]:
        values = np.asarray(features, dtype=float)
        if values.shape != (6,):
            raise ValueError("冗余相似度特征必须为六维。")
        for index, value in enumerate(values):
            validate_unit_interval(value, f"similarity_feature[{index}]")
        if object_type == "field":
            weights, names = self.field_weights, self.FIELD_FEATURES
        elif object_type == "table":
            weights, names = self.table_weights, self.TABLE_FEATURES
        else:
            raise ValueError("object_type只能为'field'或'table'。")
        return float(np.dot(weights, values)), names

    def _risk_level(self, risk: float, necessity: float, sync_control: float) -> RedundancyRiskLevel:
        controlled_max, low_max, medium_max = self.risk_thresholds
        if necessity >= 0.75 and sync_control >= 0.75 and risk < controlled_max:
            return RedundancyRiskLevel.CONTROLLED
        if risk < low_max:
            return RedundancyRiskLevel.LOW
        if risk < medium_max:
            return RedundancyRiskLevel.MEDIUM
        return RedundancyRiskLevel.HIGH

    def assess(
        self,
        object_type: str,
        left_object: str,
        right_object: str,
        features: Sequence[float],
        necessity: float,
        conflict: float,
        update_independence: float,
        sync_control: float,
        impact: float,
        evidence_ids: Sequence[str] = (),
    ) -> RedundancyAssessment:
        similarity, feature_names = self._similarity(features, object_type)
        necessity = validate_unit_interval(necessity, "necessity")
        conflict = validate_unit_interval(conflict, "conflict")
        update_independence = validate_unit_interval(update_independence, "update_independence")
        sync_control = validate_unit_interval(sync_control, "sync_control")
        impact = validate_unit_interval(impact, "impact")
        risk_term = float(
            np.dot(
                self.risk_weights,
                [conflict, update_independence, 1.0 - sync_control, impact],
            )
        )
        risk_index = float(similarity * (1.0 - necessity) * risk_term)
        return RedundancyAssessment(
            object_type=object_type,
            left_object=left_object,
            right_object=right_object,
            similarity=similarity,
            necessity=necessity,
            conflict=conflict,
            update_independence=update_independence,
            sync_control=sync_control,
            impact=impact,
            risk_index=risk_index,
            risk_level=self._risk_level(risk_index, necessity, sync_control),
            feature_names=feature_names,
            feature_values=tuple(float(x) for x in features),
            evidence_ids=tuple(evidence_ids),
        )

    def assess_field(self, **kwargs) -> RedundancyAssessment:
        return self.assess(object_type="field", **kwargs)

    def assess_table(self, **kwargs) -> RedundancyAssessment:
        return self.assess(object_type="table", **kwargs)
