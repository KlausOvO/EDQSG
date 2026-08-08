"""离线 CSV 评价入口。

用法（项目根目录下）：
    python examples/csv/run_csv_offline.py
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from edqsg.csvsource import run_assessment  # noqa: E402


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    data = run_assessment(
        os.path.join(base, "config_offline.json"),
        os.path.join(base, "output"),
    )
    print("最终得分:", round(data["final_score"], 2))
    print("总体等级:", data["overall_grade"])
    print("底线触发:", [t["rule_id"] for t in data["bottom_line_triggers"]])
    ranked = [
        r
        for r in data["root_causes"]
        if not r.get("below_threshold") and not r.get("low_confidence")
    ]
    print(
        "根因前3:",
        [(r["sg_indicator_id"], round(r["contribution"], 4)) for r in ranked[:3]]
        or "无（全部根因候选低于诊断充分性门槛）",
    )
    print("治理任务:", [t["task_id"] for t in data["governance_tasks"]])


if __name__ == "__main__":
    main()
