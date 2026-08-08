"""治理前后复评比较。"""

from .models import AssessmentReport, ReassessmentResult


class ReassessmentEngine:
    """比较两次真实评价结果，不使用固定比例人为提分。"""

    @staticmethod
    def suggest_coupling_updates(
        before: AssessmentReport,
        after: AssessmentReport,
        improvement_gap: float = 0.5,
    ) -> dict[tuple[str, str], float]:
        """模型 10.3 节：依据治理复评结果给出 Q-S 耦合可信度修正建议。

        返回 {(sg, dq): delta}：delta 为正表示上调（治理有效，步长 +0.05，
        累计不超过 +0.2），为负表示下调（治理无效，步长 −0.1，累计不超过 −0.3）。
        """

        before_roots = {item.sg_indicator_id: item for item in before.root_causes}
        before_dq = {item.indicator_id: item for item in before.indicator_results}
        after_dq = {item.indicator_id: item for item in after.indicator_results}
        updates: dict[tuple[str, str], float] = {}
        for sg_id, root in before_roots.items():
            for dq_id in root.affected_dq_ids:
                if dq_id not in before_dq or dq_id not in after_dq:
                    continue
                change = after_dq[dq_id].score - before_dq[dq_id].score
                delta = 0.05 if change >= improvement_gap else -0.1
                updates[(sg_id, dq_id)] = delta
        return updates

    @staticmethod
    def compare(before: AssessmentReport, after: AssessmentReport) -> ReassessmentResult:
        before_rules = set(before.bottom_line_outcome.triggered_rule_ids)
        after_rules = set(after.bottom_line_outcome.triggered_rule_ids)
        before_rank = {
            item.sg_indicator_id: index + 1 for index, item in enumerate(before.root_causes)
        }
        after_rank = {
            item.sg_indicator_id: index + 1 for index, item in enumerate(after.root_causes)
        }
        ids = sorted(set(before_rank) | set(after_rank))
        rank_change = tuple(
            (item_id, before_rank.get(item_id), after_rank.get(item_id)) for item_id in ids
        )
        return ReassessmentResult(
            dq_change=float(after.dq.score - before.dq.score),
            sg_change=float(after.sg.score - before.sg.score),
            final_score_change=float(after.final_score - before.final_score),
            confidence_change=float(after.overall_confidence - before.overall_confidence),
            resolved_bottom_lines=tuple(sorted(before_rules - after_rules)),
            new_bottom_lines=tuple(sorted(after_rules - before_rules)),
            root_cause_rank_change=rank_change,
        )
