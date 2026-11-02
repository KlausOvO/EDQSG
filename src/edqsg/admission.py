"""R03-X1-B1 experimental formal-grade admission layer.

This is an OPTIONAL, explicit-policy API; it does not change legacy evaluate() or
historical benchmark tables. The policy must be documented by the evaluator;
no specific indicator (including DQ1) is universally critical.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import TYPE_CHECKING

from .models import AssessmentReport, Domain, Indicator, IndicatorAssessment

if TYPE_CHECKING:
    from .core import EDQSGModel


@dataclass(frozen=True)
class CriticalRuleRequirement:
    """A risk/control rule and all indicators needed to judge its evidence."""

    rule_id: str
    indicator_ids: tuple[str, ...]


@dataclass(frozen=True)
class FormalAdmissionPolicy:
    """Explicitly reviewed, scenario-specific rule-to-indicator register.

    Declare either one or more `critical_rules`, or explicitly assert that
    the current *scope* has no relevant critical rule. The assertion is not
    inferred from the data; the register requires human/business review.
    """

    policy_id: str
    scope: str
    basis: str
    critical_rules: tuple[CriticalRuleRequirement, ...] = ()
    no_relevant_critical_rules: bool = False


@dataclass(frozen=True)
class AdmissionIssue:
    code: str
    indicator_id: str | None
    rule_id: str | None
    explanation: str


@dataclass(frozen=True)
class FormalAdmissionDecision:
    """A withheld decision exposes NO official overall grade."""

    issued: bool
    policy_id: str
    status: str
    issues: tuple[AdmissionIssue, ...]
    indicator_results: tuple[IndicatorAssessment, ...]
    review_indicator_ids: tuple[str, ...]
    excluded_indicator_ids: tuple[str, ...]
    report: AssessmentReport | None = None

    def __post_init__(self):
        if self.issued != (self.report is not None):
            raise ValueError("正式评级准入状态与报告必须一致")


def _validate_policy(policy: FormalAdmissionPolicy, indicators: Sequence[Indicator]) -> None:
    if not isinstance(policy, FormalAdmissionPolicy):
        raise TypeError("正式评级必须提供FormalAdmissionPolicy")
    if not (policy.policy_id.strip() and policy.scope.strip() and policy.basis.strip()):
        raise ValueError("策略编号、适用范围和依据均不能为空")
    if bool(policy.critical_rules) == policy.no_relevant_critical_rules:
        raise ValueError("须登记关键规则，或明确声明适用范围内无关键规则（二者只能选一）")
    ids = [item.indicator_id for item in indicators]
    if len(set(ids)) != len(ids):
        raise ValueError("指标标识重复")
    rule_ids = [rule.rule_id for rule in policy.critical_rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("关键规则标识重复")
    for rule in policy.critical_rules:
        if not rule.rule_id.strip() or not rule.indicator_ids:
            raise ValueError("每条关键规则必须具有规则标识及关联指标")
        if len(set(rule.indicator_ids)) != len(rule.indicator_ids):
            raise ValueError(f"规则{rule.rule_id}含重复关联指标")
        unknown_ids = set(rule.indicator_ids).difference(ids)
        if unknown_ids:
            raise ValueError(f"规则{rule.rule_id}引用未提交指标: {sorted(unknown_ids)}")


def evaluate_formal(
    model: EDQSGModel,
    indicators: Sequence[Indicator],
    dq_weights,
    sg_weights,
    *,
    admission_policy: FormalAdmissionPolicy,
    **evaluate_options,
) -> FormalAdmissionDecision:
    """Decide admission before calling legacy scoring, keeping unknown separate.

    θ_review uses the existing indicator review_state (unknown >= θ_review).
    If a registered critical indicator is in conflict, it is withheld as well.
    Noncritical review is retained in the report and does not itself block.
    """
    items = tuple(indicators)
    _validate_policy(admission_policy, items)
    fused = tuple(model.evidence_engine.fuse(item) for item in items)
    issues: list[AdmissionIssue] = []
    all_ids = {item.indicator_id for item in fused}
    if not any(item.domain is Domain.DATA_QUALITY for item in fused):
        issues.append(AdmissionIssue("DQ_DOMAIN_MISSING", None, None, "缺少Q域指标"))
    if not any(item.domain is Domain.STRUCTURAL_GOVERNANCE for item in fused):
        issues.append(AdmissionIssue("SG_DOMAIN_MISSING", None, None, "缺少S域指标"))
    excluded = tuple(sorted(
        item.indicator_id for item in fused
        if item.unknown_degree > model.config.aggregation_exclusion_threshold
        or item.review_state == "conflict"
    ))
    for domain, code in ((Domain.DATA_QUALITY, "DQ_DOMAIN_EXCLUDED"),
                         (Domain.STRUCTURAL_GOVERNANCE, "SG_DOMAIN_EXCLUDED")):
        group = [item for item in fused if item.domain is domain]
        if group and all(item.indicator_id in excluded for item in group):
            issues.append(AdmissionIssue(code, None, None, f"{domain.value}域无可参与聚合指标"))
    by_id = {item.indicator_id: item for item in fused}
    for rule in admission_policy.critical_rules:
        for critical_id in rule.indicator_ids:
            item = by_id[critical_id]
            if item.review_state == "insufficient_evidence":
                issues.append(AdmissionIssue(
                    "CRITICAL_EVIDENCE_INSUFFICIENT", critical_id, rule.rule_id,
                    f"关键指标{critical_id}未知度{item.unknown_degree:.6f}达到复核门槛",
                ))
            elif item.review_state == "conflict":
                issues.append(AdmissionIssue(
                    "CRITICAL_EVIDENCE_CONFLICT", critical_id, rule.rule_id,
                    f"关键指标{critical_id}证据冲突，需先复核",
                ))
    reviews = tuple(sorted(item.indicator_id for item in fused if item.review_required))
    if issues:
        return FormalAdmissionDecision(False, admission_policy.policy_id,
                                       "withheld", tuple(issues), fused, reviews,
                                       excluded, report=None)
    report = model.evaluate(items, dq_weights, sg_weights, **evaluate_options)
    return FormalAdmissionDecision(True, admission_policy.policy_id,
                                   "issued", (), fused, reviews, excluded, report=report)
