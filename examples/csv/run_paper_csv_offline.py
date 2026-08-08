"""离线评价 + 论文结果导出入口。

用法（项目根目录下）：
    python examples/csv/run_paper_csv_offline.py
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from edqsg.csvsource.runner import run_paper_results  # noqa: E402


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    summary = run_paper_results(
        os.path.join(base, "config_offline.json"),
        os.path.join(base, "output_paper"),
    )
    print("最终得分:", summary["final_score"], "| 等级:", summary["overall_grade"])
    print("基线对比等级变化:", summary["baseline"]["grade_changed"])
    print("敏感性等级反转率:", summary["sensitivity"]["grade_flip_rate"])


if __name__ == "__main__":
    main()
