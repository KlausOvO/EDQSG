"""[CORE] EDQSG升级版总模型。
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from .bottom_line import BottomLineEngine
from .config import EDQSGConfig
from .coupling import CouplingAnalyzer, CouplingCalibrator
from .evidence import EvidenceFusionEngine
from .governance import GovernanceTaskPlanner
from .models import (
    AssessmentReport,
    BottomLineTrigger,
    CouplingCalibrationInput,
    CouplingRelation,
    Domain,
    GovernanceTemplate,
    Indicator,
    RedundancyAssessment,
    RobustnessReport,
    SensitivityReport,
)
from .reassessment import ReassessmentEngine
from .robustness import DeterministicSensitivityAnalyzer, MonteCarloAnalyzer
from .scoring import ScoreCalculator
from .validators import require_unique, validate_weight_mapping


class EDQSGModel:
    """证据驱动的数据质量—结构治理评价模型正式计算入口。"""

    def __init__(self, config: EDQSGConfig | None = None):
        self.config = config or EDQSGConfig()
        self.evidence_engine = EvidenceFusionEngine(
            eta=self.config.evidence_eta,
            grade_utilities=self.config.grade_utilities,
            conflict_review_threshold=self.config.evidence_conflict_review_threshold,
            conflict_extreme_threshold=self.config.evidence_conflict_extreme_threshold,
            insufficient_review_threshold=(
                self.config.evidence_insufficient_review_threshold
            ),
        )
        self.coupling_calibrator = CouplingCalibrator(
            self.config.coupling_strength_weights,
            self.config.coupling_confidence_weights,
            self.config.coupling_source_disagreement_threshold,
        )
        self.task_planner = GovernanceTaskPlanner(
            threshold=self.config.root_cause_threshold,
            minimum_cost=self.config.minimum_cost,
            bottom_line_bonus=self.config.bottom_line_priority_bonus,
        )

    def with_alpha(self, alpha: float) -> "EDQSGModel":
        """返回仅修改双域权重alpha的新模型，不改变原对象。"""

        return EDQSGModel(replace(self.config, alpha=alpha))

    def evaluate(
        self,
        indicators: Sequence[Indicator],
        dq_weights: Mapping[str, float],
        sg_weights: Mapping[str, float],
        coupling_relations: Sequence[CouplingRelation] = (),
        coupling_calibrations: Sequence[CouplingCalibrationInput] = (),
        bottom_line_triggers: Sequence[BottomLineTrigger] = (),
        governance_templates: Sequence[GovernanceTemplate] = (),
        redundancy_results: Sequence[RedundancyAssessment] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> AssessmentReport:
        """执行完整评价—诊断—治理流程。"""

        require_unique(indicators, lambda item: item.indicator_id, "指标")
        assessments = [self.evidence_engine.fuse(item) for item in indicators]
        dq_results = [item for item in assessments if item.domain is Domain.DATA_QUALITY]
        sg_results = [item for item in assessments if item.domain is Domain.STRUCTURAL_GOVERNANCE]
        if not dq_results or not sg_results:
            raise ValueError("数据质量域和结构治理域均至少需要一个指标。")

        def aggregate(results, weights, domain_name):
            """模型 3.5、4.1 节：按聚合门槛筛选参与指标，重归一权重并计算证据覆盖率。"""

            all_ids = [item.indicator_id for item in results]
            weights_all = validate_weight_mapping(weights, all_ids, f"{domain_name}权重")
            participating = [
                item
                for item in results
                # 模型 3.5 节：未知度“超过”聚合门槛才不参与，等于门槛仍参与
                if item.unknown_degree <= self.config.aggregation_exclusion_threshold
                and item.review_state != "conflict"
            ]
            participating_ids = [item.indicator_id for item in participating]
            if not participating:
                raise ValueError(
                    f"{domain_name}全部指标因证据不足或冲突复核被排除，"
                    "按模型规则不出具总体等级，请补充证据后重新评价。"
                )
            # 模型 4.1 节：证据覆盖率 = 参与指标原始权重之和（权重已按全部
            # 指标归一化），被排除指标不参与聚合但不会从覆盖率中消失。
            coverage = sum(weights_all[item_id] for item_id in participating_ids)
            part_weights = {item_id: weights_all[item_id] for item_id in participating_ids}
            part_normalized = validate_weight_mapping(
                part_weights, participating_ids, f"{domain_name}参与权重"
            )
            assessment = ScoreCalculator.domain_assessment(
                participating,
                part_normalized,
                domain_name,
                evidence_coverage=coverage,
            )
            excluded = [
                item.indicator_id
                for item in results
                if item.indicator_id not in set(participating_ids)
            ]
            return assessment, coverage, excluded, part_normalized

        dq_assessment, dq_coverage, dq_excluded, dq_weight_map = aggregate(
            dq_results, dq_weights, "数据质量域"
        )
        sg_assessment, sg_coverage, sg_excluded, _ = aggregate(
            sg_results, sg_weights, "结构治理域"
        )
        evidence_coverage = min(dq_coverage, sg_coverage)
        excluded_ids = tuple(sorted(set(dq_excluded) | set(sg_excluded)))
        initial, balance, overall_confidence = ScoreCalculator.combine(
            dq_assessment, sg_assessment, self.config.alpha
        )
        bottom_outcome = BottomLineEngine.apply(initial, bottom_line_triggers)

        calibrated = self.coupling_calibrator.calibrate_many(coupling_calibrations)
        all_relations = list(coupling_relations) + calibrated
        require_unique(
            all_relations,
            lambda item: (item.dq_indicator_id, item.sg_indicator_id),
            "最终耦合关系",
        )
        root_causes = CouplingAnalyzer.analyze(
            dq_results,
            sg_results,
            dq_weight_map,
            all_relations,
            threshold=self.config.root_cause_threshold,
        )
        sg_map = {item.indicator_id: item for item in sg_results}
        tasks = self.task_planner.build_tasks(
            root_causes=root_causes,
            sg_results=sg_map,
            templates=governance_templates,
            bottom_line_triggers=bottom_line_triggers,
        )
        final_grade = ScoreCalculator.grade(
            bottom_outcome.final_score,
            self.config.grade_boundaries,
        )
        review_ids = [item.indicator_id for item in assessments if item.review_required]
        return AssessmentReport(
            dq=dq_assessment,
            sg=sg_assessment,
            initial_score=initial,
            final_score=bottom_outcome.final_score,
            balance=balance,
            overall_confidence=overall_confidence,
            overall_grade=final_grade,
            indicator_results=assessments,
            bottom_line_outcome=bottom_outcome,
            bottom_line_triggers=list(bottom_line_triggers),
            root_causes=root_causes,
            governance_tasks=tasks,
            redundancy_results=list(redundancy_results),
            coupling_relations=list(all_relations),
            review_indicator_ids=review_ids,
            metadata=dict(metadata or {}),
            evidence_coverage=evidence_coverage,
            excluded_indicator_ids=excluded_ids,
        )

    @staticmethod
    def compare(before: AssessmentReport, after: AssessmentReport):
        return ReassessmentEngine.compare(before, after)

    def sensitivity(
        self,
        indicators: Sequence[Indicator],
        dq_weights: Mapping[str, float],
        sg_weights: Mapping[str, float],
        coupling_relations: Sequence[CouplingRelation] = (),
        bottom_line_triggers: Sequence[BottomLineTrigger] = (),
        governance_templates: Sequence[GovernanceTemplate] = (),
        redundancy_results: Sequence[RedundancyAssessment] = (),
        perturbations: Sequence[float] = (0.8, 0.9, 1.1, 1.2),
        top_k: int = 5,
    ) -> SensitivityReport:
        """运行单因素确定性敏感性分析。"""

        analyzer = DeterministicSensitivityAnalyzer()
        return analyzer.run(
            model=self,
            indicators=list(indicators),
            dq_weights=dict(dq_weights),
            sg_weights=dict(sg_weights),
            coupling_relations=list(coupling_relations),
            bottom_line_triggers=list(bottom_line_triggers),
            governance_templates=list(governance_templates),
            redundancy_results=list(redundancy_results),
            perturbations=tuple(float(item) for item in perturbations),
            top_k=top_k,
        )

    def robustness(
        self,
        indicators: Sequence[Indicator],
        dq_weights: Mapping[str, float],
        sg_weights: Mapping[str, float],
        coupling_relations: Sequence[CouplingRelation] = (),
        bottom_line_triggers: Sequence[BottomLineTrigger] = (),
        governance_templates: Sequence[GovernanceTemplate] = (),
        redundancy_results: Sequence[RedundancyAssessment] = (),
        iterations: int | None = None,
        perturbation: float | None = None,
        seed: int | None = None,
        perturb_bottom_line: bool = True,
    ) -> RobustnessReport:
        iterations = iterations or self.config.robustness_iterations
        perturbation = (
            self.config.robustness_perturbation if perturbation is None else perturbation
        )
        if iterations <= 0:
            raise ValueError("iterations必须大于0。")
        if not 0 <= perturbation < 1:
            raise ValueError("perturbation必须位于[0,1)。")
        analyzer = MonteCarloAnalyzer(seed if seed is not None else self.config.random_seed)
        return analyzer.run(
            model=self,
            indicators=list(indicators),
            dq_weights=dict(dq_weights),
            sg_weights=dict(sg_weights),
            coupling_relations=list(coupling_relations),
            bottom_line_triggers=list(bottom_line_triggers),
            governance_templates=list(governance_templates),
            redundancy_results=list(redundancy_results),
            iterations=iterations,
            perturbation=perturbation,
            perturb_bottom_line=perturb_bottom_line,
        )
