"""敏感性与蒙特卡洛稳健性分析。"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from .models import (
    CouplingRelation,
    Evidence,
    Indicator,
    RedundancyRiskLevel,
    RobustnessReport,
    SensitivityCase,
    SensitivityReport,
)

if TYPE_CHECKING:
    from .core import EDQSGModel


class MonteCarloAnalyzer:
    """对权重、证据可靠性、耦合强度和alpha进行同步扰动。"""

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)

    def _factor(self, perturbation: float) -> float:
        return float(self.rng.uniform(1.0 - perturbation, 1.0 + perturbation))

    @staticmethod
    def _normalize_mapping(values: dict[str, float]) -> dict[str, float]:
        total = sum(values.values())
        return {key: value / total for key, value in values.items()}


    @staticmethod
    def _redundancy_level(
        risk: float, necessity: float, sync_control: float, thresholds: tuple[float, float, float]
    ) -> RedundancyRiskLevel:
        controlled_max, low_max, medium_max = thresholds
        if necessity >= 0.75 and sync_control >= 0.75 and risk < controlled_max:
            return RedundancyRiskLevel.CONTROLLED
        if risk < low_max:
            return RedundancyRiskLevel.LOW
        if risk < medium_max:
            return RedundancyRiskLevel.MEDIUM
        return RedundancyRiskLevel.HIGH

    def _perturb_evidence(self, evidence: Evidence, perturbation: float) -> Evidence:
        def p(value: float) -> float:
            return float(np.clip(value * self._factor(perturbation), 0.0, 1.0))

        return replace(
            evidence,
            coverage=p(evidence.coverage),
            authority=p(evidence.authority),
            timeliness=p(evidence.timeliness),
            repeatability=p(evidence.repeatability),
            business_fit=p(evidence.business_fit),
        )

    def run(
        self,
        model: "EDQSGModel",
        indicators: list[Indicator],
        dq_weights: dict[str, float],
        sg_weights: dict[str, float],
        coupling_relations: list[CouplingRelation],
        bottom_line_triggers,
        governance_templates,
        redundancy_results,
        iterations: int,
        perturbation: float,
        perturb_bottom_line: bool = True,
    ) -> RobustnessReport:
        baseline = model.evaluate(
            indicators=indicators,
            dq_weights=dq_weights,
            sg_weights=sg_weights,
            coupling_relations=coupling_relations,
            bottom_line_triggers=bottom_line_triggers,
            governance_templates=governance_templates,
            redundancy_results=redundancy_results,
        )
        baseline_grade = baseline.overall_grade
        baseline_root = (
            _ranked_roots(baseline)[0].sg_indicator_id if _ranked_roots(baseline) else None
        )
        baseline_task = baseline.governance_tasks[0].task_id if baseline.governance_tasks else None
        baseline_redundancy = (
            max(baseline.redundancy_results, key=lambda item: item.risk_index).left_object
            + "::"
            + max(baseline.redundancy_results, key=lambda item: item.risk_index).right_object
            if baseline.redundancy_results
            else None
        )

        scores: list[float] = []
        root_counter: Counter[str] = Counter()
        task_counter: Counter[str] = Counter()
        redundancy_counter: Counter[str] = Counter()
        grade_flips = root_flips = task_flips = redundancy_flips = 0
        for _ in range(iterations):
            perturbed_indicators = [
                replace(
                    item,
                    evidences=tuple(
                        self._perturb_evidence(evidence, perturbation)
                        for evidence in item.evidences
                    ),
                )
                for item in indicators
            ]
            dq = self._normalize_mapping(
                {key: max(1e-12, value * self._factor(perturbation)) for key, value in dq_weights.items()}
            )
            sg = self._normalize_mapping(
                {key: max(1e-12, value * self._factor(perturbation)) for key, value in sg_weights.items()}
            )
            relations = [
                replace(
                    relation,
                    strength=float(np.clip(relation.strength * self._factor(perturbation), 0, 1)),
                    confidence=float(np.clip(relation.confidence * self._factor(perturbation), 0, 1)),
                )
                for relation in coupling_relations
            ]
            if perturb_bottom_line:
                # 底线限级值属政策参数；扰动时用于考察限级边界敏感性。
                triggers = [
                    replace(
                        trigger,
                        cap=float(np.clip(trigger.cap * self._factor(perturbation), 0, 100)),
                        penalty=max(0.0, trigger.penalty * self._factor(perturbation)),
                    )
                    for trigger in bottom_line_triggers
                ]
            else:
                # 模型参数扰动时固定底线限级值，避免政策边界混入模型稳健性评估。
                triggers = list(bottom_line_triggers)
            redundancies = []
            for item in redundancy_results:
                necessity = float(np.clip(item.necessity * self._factor(perturbation), 0, 1))
                risk_index = float(np.clip(item.risk_index * self._factor(perturbation), 0, 1))
                sync_control = float(np.clip(item.sync_control * self._factor(perturbation), 0, 1))
                redundancies.append(
                    replace(
                        item,
                        necessity=necessity,
                        sync_control=sync_control,
                        risk_index=risk_index,
                        risk_level=self._redundancy_level(
                            risk_index,
                            necessity,
                            sync_control,
                            model.config.redundancy_risk_thresholds,
                        ),
                    )
                )
            alpha = float(np.clip(model.config.alpha * self._factor(perturbation), 0, 1))
            perturbed_model = model.with_alpha(alpha)
            try:
                report = perturbed_model.evaluate(
                    indicators=perturbed_indicators,
                    dq_weights=dq,
                    sg_weights=sg,
                    coupling_relations=relations,
                    bottom_line_triggers=triggers,
                    governance_templates=governance_templates,
                    redundancy_results=redundancies,
                )
            except ValueError:
                # 证据可靠性扰动导致全部指标被排除时，模型按设计不出具总体等级，
                # 该迭代计入等级与根因反转，但不进入分数分布统计。
                grade_flips += 1
                root_flips += 1
                task_flips += 1
                redundancy_flips += 1
                continue
            scores.append(report.final_score)
            grade_flips += int(report.overall_grade is not baseline_grade)
            root = _ranked_roots(report)[0].sg_indicator_id if _ranked_roots(report) else None
            task = report.governance_tasks[0].task_id if report.governance_tasks else None
            redundancy = (
                max(report.redundancy_results, key=lambda item: item.risk_index).left_object
                + "::"
                + max(report.redundancy_results, key=lambda item: item.risk_index).right_object
                if report.redundancy_results
                else None
            )
            root_flips += int(root != baseline_root)
            task_flips += int(task != baseline_task)
            redundancy_flips += int(redundancy != baseline_redundancy)
            if root is not None:
                root_counter[root] += 1
            if task is not None:
                task_counter[task] += 1
            if redundancy is not None:
                redundancy_counter[redundancy] += 1

        array = np.asarray(scores, dtype=float)
        q05, q50, q95 = np.quantile(array, [0.05, 0.50, 0.95])
        return RobustnessReport(
            iterations=iterations,
            perturbation=perturbation,
            baseline_score=baseline.final_score,
            score_mean=float(array.mean()),
            score_std=float(array.std(ddof=1)) if iterations > 1 else 0.0,
            score_quantiles=(float(q05), float(q50), float(q95)),
            grade_flip_rate=grade_flips / iterations,
            top_root_cause_flip_rate=root_flips / iterations,
            top_task_flip_rate=task_flips / iterations,
            top_redundancy_flip_rate=redundancy_flips / iterations,
            score_samples=tuple(float(value) for value in scores),
            top_root_cause_probabilities=tuple(
                (key, count / iterations) for key, count in root_counter.most_common()
            ),
            top_task_probabilities=tuple(
                (key, count / iterations) for key, count in task_counter.most_common()
            ),
            top_redundancy_probabilities=tuple(
                (key, count / iterations) for key, count in redundancy_counter.most_common()
            ),
        )


def _ranked_roots(report):
    """模型 5.2 节：低于诊断充分性门槛或低可信的候选不进入前 K 排序。"""

    return tuple(
        item
        for item in report.root_causes
        if not item.below_threshold and not item.low_confidence
    )


class DeterministicSensitivityAnalyzer:
    """单因素确定性敏感性分析。

    该分析与蒙特卡洛互补：每次只扰动一个参数或参数组，使论文可以明确
    回答“哪个参数导致了分数、等级、根因前K名或治理任务前K名变化”。
    """

    @staticmethod
    def _normalize_mapping(values: dict[str, float]) -> dict[str, float]:
        total = sum(values.values())
        if total <= 0:
            raise ValueError("权重扰动后总和必须大于0。")
        return {key: value / total for key, value in values.items()}

    @staticmethod
    def _top_roots(report, top_k: int) -> tuple[str, ...]:
        return tuple(item.sg_indicator_id for item in _ranked_roots(report)[:top_k])

    @staticmethod
    def _top_tasks(report, top_k: int) -> tuple[str, ...]:
        return tuple(item.task_id for item in report.governance_tasks[:top_k])

    @staticmethod
    def _overlap(left: tuple[str, ...], right: tuple[str, ...], top_k: int) -> float:
        if not left and not right:
            return 1.0
        denominator = max(1, min(top_k, max(len(left), len(right))))
        return len(set(left) & set(right)) / denominator

    @staticmethod
    def _clip01(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))

    def run(
        self,
        model: "EDQSGModel",
        indicators: list[Indicator],
        dq_weights: dict[str, float],
        sg_weights: dict[str, float],
        coupling_relations: list[CouplingRelation],
        bottom_line_triggers,
        governance_templates,
        redundancy_results,
        perturbations: tuple[float, ...],
        top_k: int,
    ) -> SensitivityReport:
        if not perturbations or any(factor <= 0 for factor in perturbations):
            raise ValueError("perturbations必须为非空正数序列。")
        if top_k <= 0:
            raise ValueError("top_k必须大于0。")

        baseline = model.evaluate(
            indicators=indicators,
            dq_weights=dq_weights,
            sg_weights=sg_weights,
            coupling_relations=coupling_relations,
            bottom_line_triggers=bottom_line_triggers,
            governance_templates=governance_templates,
            redundancy_results=redundancy_results,
        )
        baseline_roots = self._top_roots(baseline, top_k)
        baseline_tasks = self._top_tasks(baseline, top_k)
        cases: list[SensitivityCase] = []

        def evaluate_case(
            parameter: str,
            factor: float,
            *,
            local_model=None,
            local_indicators=None,
            local_dq=None,
            local_sg=None,
            local_relations=None,
            local_triggers=None,
            local_redundancies=None,
        ) -> None:
            try:
                report = (local_model or model).evaluate(
                    indicators=local_indicators or indicators,
                    dq_weights=local_dq or dq_weights,
                    sg_weights=local_sg or sg_weights,
                    coupling_relations=local_relations or coupling_relations,
                    bottom_line_triggers=local_triggers or bottom_line_triggers,
                    governance_templates=governance_templates,
                    redundancy_results=local_redundancies or redundancy_results,
                )
            except ValueError:
                # 证据可靠性下降导致指标全部被排除时，模型按设计不出具总体等级，
                # 记为“等级反转（转无等级）”，不中断敏感性分析。
                cases.append(
                    SensitivityCase(
                        parameter=parameter,
                        factor=factor,
                        final_score=baseline.final_score,
                        score_change=0.0,
                        overall_grade=baseline.overall_grade,
                        grade_flipped=True,
                        top_root_cause=None,
                        root_top_k_overlap=0.0,
                        top_task=None,
                        task_top_k_overlap=0.0,
                    )
                )
                return
            roots = self._top_roots(report, top_k)
            tasks = self._top_tasks(report, top_k)
            cases.append(
                SensitivityCase(
                    parameter=parameter,
                    factor=factor,
                    final_score=report.final_score,
                    score_change=report.final_score - baseline.final_score,
                    overall_grade=report.overall_grade,
                    grade_flipped=report.overall_grade != baseline.overall_grade,
                    top_root_cause=roots[0] if roots else None,
                    root_top_k_overlap=self._overlap(baseline_roots, roots, top_k),
                    top_task=tasks[0] if tasks else None,
                    task_top_k_overlap=self._overlap(baseline_tasks, tasks, top_k),
                )
            )

        for factor in perturbations:
            for key in dq_weights:
                values = dict(dq_weights)
                values[key] = max(1e-12, values[key] * factor)
                evaluate_case(
                    f"dq_weight:{key}", factor,
                    local_dq=self._normalize_mapping(values),
                )
            for key in sg_weights:
                values = dict(sg_weights)
                values[key] = max(1e-12, values[key] * factor)
                evaluate_case(
                    f"sg_weight:{key}", factor,
                    local_sg=self._normalize_mapping(values),
                )

            evaluate_case(
                "domain_alpha",
                factor,
                local_model=model.with_alpha(self._clip01(model.config.alpha * factor)),
            )

            for indicator in indicators:
                changed = []
                for item in indicators:
                    if item.indicator_id != indicator.indicator_id:
                        changed.append(item)
                        continue
                    evidences = tuple(
                        replace(
                            evidence,
                            coverage=self._clip01(evidence.coverage * factor),
                            authority=self._clip01(evidence.authority * factor),
                            timeliness=self._clip01(evidence.timeliness * factor),
                            repeatability=self._clip01(evidence.repeatability * factor),
                            business_fit=self._clip01(evidence.business_fit * factor),
                        )
                        for evidence in item.evidences
                    )
                    changed.append(replace(item, evidences=evidences))
                evaluate_case(
                    f"evidence_reliability:{indicator.indicator_id}",
                    factor,
                    local_indicators=changed,
                )

            for idx, relation in enumerate(coupling_relations):
                changed_strength = list(coupling_relations)
                changed_strength[idx] = replace(
                    relation,
                    strength=self._clip01(relation.strength * factor),
                )
                evaluate_case(
                    f"coupling_strength:{relation.sg_indicator_id}->{relation.dq_indicator_id}",
                    factor,
                    local_relations=changed_strength,
                )
                changed_confidence = list(coupling_relations)
                changed_confidence[idx] = replace(
                    relation,
                    confidence=self._clip01(relation.confidence * factor),
                )
                evaluate_case(
                    f"coupling_confidence:{relation.sg_indicator_id}->{relation.dq_indicator_id}",
                    factor,
                    local_relations=changed_confidence,
                )

            for idx, trigger in enumerate(bottom_line_triggers):
                changed = list(bottom_line_triggers)
                changed[idx] = replace(
                    trigger,
                    cap=float(np.clip(trigger.cap * factor, 0.0, 100.0)),
                    penalty=max(0.0, trigger.penalty * factor),
                )
                evaluate_case(
                    f"bottom_line:{trigger.rule_id}",
                    factor,
                    local_triggers=changed,
                )

            for idx, item in enumerate(redundancy_results):
                changed = list(redundancy_results)
                necessity = self._clip01(item.necessity * factor)
                sync_control = self._clip01(item.sync_control * factor)
                risk_index = self._clip01(item.risk_index * factor)
                changed[idx] = replace(
                    item,
                    necessity=necessity,
                    sync_control=sync_control,
                    risk_index=risk_index,
                    risk_level=MonteCarloAnalyzer._redundancy_level(
                        risk_index,
                        necessity,
                        sync_control,
                        model.config.redundancy_risk_thresholds,
                    ),
                )
                evaluate_case(
                    f"redundancy:{item.left_object}::{item.right_object}",
                    factor,
                    local_redundancies=changed,
                )

        max_change = max((abs(item.score_change) for item in cases), default=0.0)
        return SensitivityReport(
            baseline_score=baseline.final_score,
            perturbations=tuple(perturbations),
            top_k=top_k,
            cases=tuple(cases),
            max_abs_score_change=max_change,
            grade_flip_rate=(
                sum(item.grade_flipped for item in cases) / len(cases) if cases else 0.0
            ),
            min_root_top_k_overlap=min(
                (item.root_top_k_overlap for item in cases), default=1.0
            ),
            min_task_top_k_overlap=min(
                (item.task_top_k_overlap for item in cases), default=1.0
            ),
        )
