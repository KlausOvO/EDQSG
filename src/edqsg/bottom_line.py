"""非补偿性底线约束。"""

from collections.abc import Sequence

import numpy as np

from .models import BottomLineOutcome, BottomLineTrigger
from .validators import validate_score


class BottomLineEngine:
    """仅对已被真实检测触发的规则实施限级或惩罚。"""

    @staticmethod
    def apply(initial_score: float, triggers: Sequence[BottomLineTrigger]) -> BottomLineOutcome:
        initial_score = validate_score(initial_score, "initial_score")
        if not triggers:
            return BottomLineOutcome(
                initial_score=initial_score,
                final_score=initial_score,
                applied_cap=100.0,
                total_penalty=0.0,
                triggered_rule_ids=(),
            )

        caps: list[float] = []
        penalty = 0.0
        rule_ids: list[str] = []
        for trigger in triggers:
            caps.append(validate_score(trigger.cap, f"{trigger.rule_id}.cap"))
            if trigger.penalty < 0:
                raise ValueError(f"{trigger.rule_id}.penalty不能为负数。")
            penalty += float(trigger.penalty)
            rule_ids.append(trigger.rule_id)
        cap = min(caps)
        # 模型 6.3 节：P = 5 × min(n_P, 4)，单次评价最多扣 20 分。
        penalty = min(penalty, 20.0)
        final_score = float(np.clip(min(initial_score, cap) - penalty, 0.0, 100.0))
        return BottomLineOutcome(
            initial_score=initial_score,
            final_score=final_score,
            applied_cap=float(cap),
            total_penalty=float(penalty),
            triggered_rule_ids=tuple(rule_ids),
        )
