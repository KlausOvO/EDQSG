"""治理任务生成、底线任务优先与任务排序。"""

from collections.abc import Mapping, Sequence

from .models import (
    BottomLineTrigger,
    GovernanceTask,
    GovernanceTemplate,
    IndicatorAssessment,
    RootCauseResult,
)
from .validators import validate_unit_interval


class GovernanceTaskPlanner:
    """将结构根因和底线风险映射为可执行治理任务。"""

    def __init__(self, threshold: float, minimum_cost: float, bottom_line_bonus: float):
        self.threshold = max(0.0, float(threshold))
        self.minimum_cost = max(1e-6, float(minimum_cost))
        self.bottom_line_bonus = max(0.0, float(bottom_line_bonus))

    def priority(self, task: GovernanceTask) -> float:
        for name, value in {
            "severity": task.severity,
            "impact": task.impact,
            "confidence": task.confidence,
            "urgency": task.urgency,
            "dependency": task.dependency,
        }.items():
            validate_unit_interval(value, name)
        if task.cost < 0:
            raise ValueError("治理成本不能为负数。")
        effective_cost = max(task.cost, self.minimum_cost)
        denominator = effective_cost * (1.0 + task.dependency)
        numerator = (
            task.severity
            * task.root_cause_contribution
            * task.impact
            * task.confidence
            * task.urgency
        )
        score = float(numerator / denominator)
        return score + (self.bottom_line_bonus if task.bottom_line else 0.0)

    @staticmethod
    def _from_template(
        task_id: str,
        template: GovernanceTemplate,
        evidence_ids: Sequence[str],
        affected_dq_ids: Sequence[str],
        contribution: float,
        confidence: float,
        bottom_line: bool,
    ) -> GovernanceTask:
        return GovernanceTask(
            task_id=task_id,
            template_id=template.template_id,
            target_object=template.target_object,
            evidence_ids=tuple(sorted(set(evidence_ids))),
            affected_dq_ids=tuple(sorted(set(affected_dq_ids))),
            root_cause=template.root_cause,
            lifecycle_stage=template.lifecycle_stage,
            measures=template.measures,
            actors=template.actors,
            acceptance_metrics=template.acceptance_metrics,
            task_layer=template.task_layer,
            severity=template.severity,
            root_cause_contribution=contribution,
            impact=template.impact,
            confidence=confidence,
            urgency=template.urgency,
            cost=template.cost,
            dependency=template.dependency,
            dependency_task_ids=template.dependency_task_ids,
            bottom_line=bottom_line,
        )

    def build_tasks(
        self,
        root_causes: Sequence[RootCauseResult],
        sg_results: Mapping[str, IndicatorAssessment],
        templates: Sequence[GovernanceTemplate],
        bottom_line_triggers: Sequence[BottomLineTrigger] = (),
    ) -> list[GovernanceTask]:
        sg_templates = {
            item.sg_indicator_id: item for item in templates if item.sg_indicator_id is not None
        }
        bottom_templates = {
            item.bottom_line_rule_id: item
            for item in templates
            if item.bottom_line_rule_id is not None
        }
        tasks: list[GovernanceTask] = []

        for root in root_causes:
            if root.contribution < self.threshold:
                continue
            template = sg_templates.get(root.sg_indicator_id)
            if template is None:
                continue
            sg_result = sg_results[root.sg_indicator_id]
            task = self._from_template(
                task_id=f"TASK-RC-{root.sg_indicator_id}",
                template=template,
                evidence_ids=tuple(sg_result.evidence_ids) + tuple(root.evidence_ids),
                affected_dq_ids=root.affected_dq_ids,
                contribution=root.contribution,
                confidence=min(sg_result.confidence, root.confidence),
                bottom_line=False,
            )
            task.priority = self.priority(task)
            tasks.append(task)

        for trigger in bottom_line_triggers:
            template = bottom_templates.get(trigger.rule_id)
            if template is None:
                continue
            task = self._from_template(
                task_id=f"TASK-BL-{trigger.rule_id}",
                template=template,
                evidence_ids=trigger.evidence_ids,
                affected_dq_ids=(),
                contribution=1.0,
                confidence=1.0,
                bottom_line=True,
            )
            task.priority = self.priority(task)
            tasks.append(task)

        return sorted(tasks, key=lambda item: item.priority, reverse=True)
