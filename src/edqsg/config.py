"""EDQSG 模型配置。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EDQSGConfig:
    """模型统一配置。

    所有比例型参数均位于 [0,1]。正式论文实验应记录配置版本，
    不应在得到结果后反向调整参数。
    """

    alpha: float = 0.5
    grade_utilities: tuple[float, float, float, float, float] = (
        100.0,
        85.0,
        70.0,
        50.0,
        20.0,
    )
    # 模型 6.1 节：等级阈值取相邻效用中点，边界语义为
    # 优 >92.5、良 >77.5、中 >60、较差 >35、差 ≤35。
    grade_boundaries: tuple[float, float, float, float] = (92.5, 77.5, 60.0, 35.0)
    # 模型 5.2 节：可靠性五属性缺省等权。
    evidence_eta: tuple[float, float, float, float, float] = (
        0.20,
        0.20,
        0.20,
        0.20,
        0.20,
    )
    # 模型 3.5 节：冲突度取指标内两两证据的 Jousselme 距离最大值，
    # 缺省阈值 θ_conf = 0.25，超过则进入复核清单。
    evidence_conflict_review_threshold: float = 0.25
    evidence_conflict_extreme_threshold: float = 0.98
    # 模型 3.5 节：证据不足复核门槛 θ_review = 0.3。指标未知度达到该值即
    # 进入“证据不足复核”，不作为根因诊断的确认证据，但在满足聚合门槛时
    # 仍可参与域内聚合。
    evidence_insufficient_review_threshold: float = 0.3
    # 模型 3.5 节：聚合门槛 θ_excl = 0.5。未知度超过该值的指标不参与域内
    # 聚合，权重在参与指标集内重新归一。
    aggregation_exclusion_threshold: float = 0.5
    # 模型 7.1 节：三源权重缺省等权 1/3。
    coupling_strength_weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
    coupling_confidence_weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
    # 模型 7.1 节：三源分歧阈值 θ_src=0.2，超限标记“待确认”。
    coupling_source_disagreement_threshold: float = 0.2
    coupling_smoothing_gamma: float = 0.20
    field_similarity_weights: tuple[float, float, float, float, float, float] = (
        0.20,
        0.20,
        0.15,
        0.20,
        0.15,
        0.10,
    )
    table_similarity_weights: tuple[float, float, float, float, float, float] = (
        0.20,
        0.15,
        0.20,
        0.20,
        0.10,
        0.15,
    )
    # 模型 8.1 节：冗余风险权重缺省等权；风险等级 高≥0.7、中≥0.4、低<0.4。
    redundancy_risk_weights: tuple[float, float, float, float] = (
        0.25,
        0.25,
        0.25,
        0.25,
    )
    # (受控合理冗余上限, 低风险上限, 中风险上限)
    redundancy_risk_thresholds: tuple[float, float, float] = (0.30, 0.40, 0.70)
    # 模型 5.2 节：诊断充分性门槛 θ_RC = 0.01，低于该值的根因候选不进入
    # 前 K 排序，仅列为待补证候选。
    root_cause_threshold: float = 0.01
    minimum_cost: float = 0.05
    bottom_line_priority_bonus: float = 1000.0
    robustness_iterations: int = 500
    robustness_perturbation: float = 0.10
    random_seed: int = 20260720
