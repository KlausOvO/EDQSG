"""EDQSG 领域数据结构。

本模块只定义不可变或可序列化的数据对象，不包含计算逻辑。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Domain(str, Enum):
    """评价域。"""

    DATA_QUALITY = "DQ"
    STRUCTURAL_GOVERNANCE = "SG"


class EvidenceType(str, Enum):
    """EDQSG 五类证据。"""

    DATA = "data"
    STRUCTURE = "structure"
    RULE = "rule"
    PROCESS = "process"
    EXPERT = "expert"


class Grade(str, Enum):
    """评价等级，顺序与模型效用值一一对应。"""

    EXCELLENT = "优"
    GOOD = "良"
    MEDIUM = "中"
    POOR = "较差"
    BAD = "差"


class RedundancyRiskLevel(str, Enum):
    """冗余风险等级。"""

    CONTROLLED = "受控合理冗余"
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"


class TaskLayer(str, Enum):
    """治理任务层级。"""

    DATA_REPAIR = "数据修复"
    STRUCTURE_GOVERNANCE = "结构治理"
    MECHANISM_GOVERNANCE = "机制治理"


@dataclass(frozen=True)
class Evidence:
    """单条可追溯评价证据。

    ``belief_degrees`` 对应五个确定等级（优、良、中、较差、差）的支持度，
    元素和不得超过 1；剩余部分由 ``unknown_degree`` 表示。若未显式给出
    ``belief_degrees``，可使用 ``observed_score`` 自动转换为相邻等级的线性
    支持分布，主要用于兼容数值型检测结果。
    """

    evidence_id: str
    evidence_type: EvidenceType
    source: str
    coverage: float
    authority: float
    timeliness: float
    repeatability: float
    business_fit: float
    # 模型 3.4 节：规则可观测度 C_rule（当前规则集对可能缺陷类型的覆盖能力），
    # 与 coverage（样本覆盖度 C_sample）共同决定初始未知度 β_U^0 = 1 − C_sample·C_rule。
    rule_observability: float = 1.0
    # 样本覆盖度 C_sample：该证据实际检查的评价对象占评价对象总量的比例；
    # 与可靠性属性 coverage（证据完整性，见 3.3 节）概念不同，二者不重复折扣。
    sample_coverage: float = 1.0
    belief_degrees: tuple[float, float, float, float, float] | None = None
    unknown_degree: float | None = None
    observed_score: float | None = None
    importance: float = 1.0
    description: str = ""
    collected_at: str = ""
    scope: str = ""
    basis: str = ""


@dataclass(frozen=True)
class Indicator:
    """待评价指标。"""

    indicator_id: str
    name: str
    domain: Domain
    evidences: tuple[Evidence, ...] = ()
    base_score: float | None = None
    description: str = ""


@dataclass(frozen=True)
class EvidenceAssessment:
    """单条证据经过可靠性折扣后的计算结果。

    ``evidence_type`` 被保留到结果对象中，供论文图展示不同证据来源的
    贡献结构；这不会改变原有证据融合算法。
    """

    evidence_id: str
    evidence_type: EvidenceType
    reliability: float
    effective_reliability: float
    discounted_beliefs: tuple[float, float, float, float, float]
    discounted_unknown: float


@dataclass(frozen=True)
class IndicatorAssessment:
    """多源证据融合后的指标结果。"""

    indicator_id: str
    name: str
    domain: Domain
    score: float
    confidence: float
    belief_degrees: tuple[float, float, float, float, float]
    unknown_degree: float
    conflict_degree: float
    evidence_ids: tuple[str, ...]
    review_required: bool = False
    review_reason: str = ""
    evidence_results: tuple[EvidenceAssessment, ...] = ()
    # 模型 3.5 节：复核状态。取值：
    #   "none"                  —— 无需复核；
    #   "insufficient_evidence" —— 证据不足复核（未知度超过 θ_review）；
    #   "conflict"              —— 冲突复核（证据冲突超过 θ_conf 或极端冲突）。
    # 两类复核均不作为根因诊断的确认证据；证据不足复核在满足聚合门槛时
    # 仍可参与域内聚合，冲突复核不参与聚合。
    review_state: str = "none"


@dataclass(frozen=True)
class CouplingCalibrationInput:
    """Q-S 耦合关系三源校准输入。

    三类强度和可信度均可为空；校准器只对实际提供的来源重新归一化权重。
    """

    dq_indicator_id: str
    sg_indicator_id: str
    normative_strength: float | None = None
    expert_strength: float | None = None
    data_strength: float | None = None
    normative_confidence: float | None = None
    expert_confidence: float | None = None
    data_confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CouplingRelation:
    """经三源校准后的结构治理—数据质量耦合关系。"""

    dq_indicator_id: str
    sg_indicator_id: str
    strength: float
    confidence: float
    evidence_ids: tuple[str, ...] = ()
    source_strengths: tuple[tuple[str, float], ...] = ()
    source_confidences: tuple[tuple[str, float], ...] = ()
    # 模型 7.1 节：三源分歧超过 θ_src 时标记“待确认”，不参与根因计算。
    pending: bool = False


@dataclass(frozen=True)
class BottomLineTrigger:
    """已被真实证据触发的非补偿性底线规则。"""

    rule_id: str
    description: str
    cap: float = 100.0
    penalty: float = 0.0
    severity_level: int = 0
    target_object: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BottomLineOutcome:
    """底线约束执行结果。"""

    initial_score: float
    final_score: float
    applied_cap: float
    total_penalty: float
    triggered_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class RootCauseResult:
    """结构治理根因贡献度。"""

    sg_indicator_id: str
    contribution: float
    confidence: float
    affected_dq_ids: tuple[str, ...]
    affected_contributions: tuple[tuple[str, float], ...] = ()
    evidence_ids: tuple[str, ...] = ()
    # 模型式(13)：归一化贡献占比 ρ_j = RC_j / ΣRC_k。
    normalized_contribution: float | None = None
    # 模型 7.2 节：c_j^S < 0.5 时为低可信候选，不进入前 K 排序。
    low_confidence: bool = False
    # 模型 5.2 节：RC_j 低于诊断充分性门槛 θ_RC 时标记，不进入前 K 排序，
    # 仅列为待补证候选。
    below_threshold: bool = False


@dataclass(frozen=True)
class GovernanceTemplate:
    """从结构根因或底线风险到治理任务的知识模板。"""

    template_id: str
    sg_indicator_id: str | None
    bottom_line_rule_id: str | None
    target_object: str
    root_cause: str
    lifecycle_stage: str
    measures: tuple[str, ...]
    actors: tuple[str, ...]
    acceptance_metrics: dict[str, Any]
    task_layer: TaskLayer
    severity: float
    impact: float
    urgency: float
    cost: float
    dependency: float = 0.0
    dependency_task_ids: tuple[str, ...] = ()


@dataclass
class GovernanceTask:
    """可派发、可跟踪、可验收的治理任务。"""

    task_id: str
    template_id: str
    target_object: str
    evidence_ids: tuple[str, ...]
    affected_dq_ids: tuple[str, ...]
    root_cause: str
    lifecycle_stage: str
    measures: tuple[str, ...]
    actors: tuple[str, ...]
    acceptance_metrics: dict[str, Any]
    task_layer: TaskLayer
    severity: float
    root_cause_contribution: float
    impact: float
    confidence: float
    urgency: float
    cost: float
    dependency: float
    dependency_task_ids: tuple[str, ...] = ()
    bottom_line: bool = False
    priority: float = 0.0


@dataclass(frozen=True)
class RedundancyAssessment:
    """字段或表冗余分析结果。"""

    object_type: str
    left_object: str
    right_object: str
    similarity: float
    necessity: float
    conflict: float
    update_independence: float
    sync_control: float
    impact: float
    risk_index: float
    risk_level: RedundancyRiskLevel
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainAssessment:
    """单个评价域的汇总。"""

    score: float
    confidence: float
    belief_degrees: tuple[float, float, float, float, float]
    unknown_degree: float
    conflict_degree: float
    # 模型 4.1 节：域内证据覆盖率 ω_cov，即参与指标原始权重之和（按全部
    # 指标归一化的权重计算），反映整个评价体系的证据覆盖程度。
    evidence_coverage: float = 1.0


@dataclass(frozen=True)
class ReassessmentResult:
    """治理前后复评差异。"""

    dq_change: float
    sg_change: float
    final_score_change: float
    confidence_change: float
    resolved_bottom_lines: tuple[str, ...]
    new_bottom_lines: tuple[str, ...]
    root_cause_rank_change: tuple[tuple[str, int | None, int | None], ...]


@dataclass(frozen=True)
class SensitivityCase:
    """单因素确定性敏感性分析的一次扰动结果。"""

    parameter: str
    factor: float
    final_score: float
    score_change: float
    overall_grade: Grade
    grade_flipped: bool
    top_root_cause: str | None
    root_top_k_overlap: float
    top_task: str | None
    task_top_k_overlap: float


@dataclass(frozen=True)
class SensitivityReport:
    """±10%/±20%等单因素确定性敏感性分析报告。"""

    baseline_score: float
    perturbations: tuple[float, ...]
    top_k: int
    cases: tuple[SensitivityCase, ...]
    max_abs_score_change: float
    grade_flip_rate: float
    min_root_top_k_overlap: float
    min_task_top_k_overlap: float


@dataclass(frozen=True)
class RobustnessReport:
    """敏感性与蒙特卡洛稳健性结果。

    除摘要统计外保留抽样分数和关键对象出现概率，便于生成论文中的
    分布图与排名稳定性图。为控制文件体积，正式大规模运行可在导出后
    删除 ``score_samples``。
    """

    iterations: int
    perturbation: float
    baseline_score: float
    score_mean: float
    score_std: float
    score_quantiles: tuple[float, float, float]
    grade_flip_rate: float
    top_root_cause_flip_rate: float
    top_task_flip_rate: float
    top_redundancy_flip_rate: float
    score_samples: tuple[float, ...] = ()
    top_root_cause_probabilities: tuple[tuple[str, float], ...] = ()
    top_task_probabilities: tuple[tuple[str, float], ...] = ()
    top_redundancy_probabilities: tuple[tuple[str, float], ...] = ()


@dataclass
class AssessmentReport:
    """EDQSG 完整评价报告。"""

    dq: DomainAssessment
    sg: DomainAssessment
    initial_score: float
    final_score: float
    balance: float
    overall_confidence: float
    overall_grade: Grade
    indicator_results: list[IndicatorAssessment]
    bottom_line_outcome: BottomLineOutcome
    bottom_line_triggers: list[BottomLineTrigger] = field(default_factory=list)
    root_causes: list[RootCauseResult] = field(default_factory=list)
    governance_tasks: list[GovernanceTask] = field(default_factory=list)
    redundancy_results: list[RedundancyAssessment] = field(default_factory=list)
    coupling_relations: list[CouplingRelation] = field(default_factory=list)
    review_indicator_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # 模型 4.1 节：总体证据覆盖率 = min(ω_cov^Q, ω_cov^S)。
    evidence_coverage: float = 1.0
    # 模型 4.1 节：被聚合门槛排除的指标标识（证据不足或冲突复核）。
    excluded_indicator_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 友好的字典。"""

        return asdict(self)
