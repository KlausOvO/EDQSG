"""SQL Server自动评价结果导出。"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..models import AssessmentReport, RobustnessReport

from .metadata import DatabaseMetadata
from .profiler import DatabaseProfile


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return value


@dataclass(frozen=True)
class SQLServerPipelineResult:
    """SQL Server采集结果与EDQSG评价报告的组合对象。"""

    assessment: AssessmentReport
    metadata: DatabaseMetadata
    profile: DatabaseProfile
    robustness: RobustnessReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "assessment": self.assessment,
                "database_metadata": self.metadata,
                "database_profile": self.profile,
                "robustness": self.robustness,
            }
        )

    def export_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def export_markdown(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        report = self.assessment
        lines = [
            "# EDQSG SQL Server自动评价报告",
            "",
            f"- 数据库：`{self.metadata.database_name}`",
            f"- 服务器：`{self.metadata.server_name}`",
            f"- 采集时间：{self.metadata.collected_at}",
            f"- 扫描表数：{len(self.metadata.tables)}",
            f"- 剖析模式：{self.profile.mode}",
            "",
            "## 综合评价",
            "",
            f"- 数据质量域 Q：**{report.dq.score:.2f}**",
            f"- 结构治理域 S：**{report.sg.score:.2f}**",
            f"- 初始综合分：**{report.initial_score:.2f}**",
            f"- 最终综合分：**{report.final_score:.2f}**",
            f"- 总体等级：**{report.overall_grade.value}**",
            f"- 双域平衡度：**{report.balance:.3f}**",
            f"- 综合可信度：**{report.overall_confidence:.3f}**",
            "",
            "## 指标结果",
            "",
            "| 指标 | 名称 | 得分 | 可信度 | 未知度 | 需复核 |",
            "|---|---|---:|---:|---:|---|",
        ]
        for item in report.indicator_results:
            lines.append(
                f"| {item.indicator_id} | {item.name} | {item.score:.2f} | "
                f"{item.confidence:.3f} | {item.unknown_degree:.3f} | "
                f"{'是' if item.review_required else '否'} |"
            )
        lines.extend(["", "## 底线风险", ""])
        if report.bottom_line_triggers:
            for trigger in report.bottom_line_triggers:
                lines.append(f"- **{trigger.rule_id}**：{trigger.description}")
        else:
            lines.append("- 未触发底线规则。")
        lines.extend(["", "## 主要结构根因", ""])
        for item in report.root_causes[:10]:
            lines.append(
                f"- `{item.sg_indicator_id}`：贡献度 {item.contribution:.6f}，"
                f"可信度 {item.confidence:.3f}，影响 {', '.join(item.affected_dq_ids) or '无'}"
            )
        lines.extend(["", "## 治理任务", ""])
        for task in report.governance_tasks[:20]:
            lines.append(
                f"### {task.task_id} · {task.target_object}\n\n"
                f"- 优先级：{task.priority:.6f}\n"
                f"- 根因：{task.root_cause}\n"
                f"- 责任主体：{', '.join(task.actors)}\n"
                f"- 措施：{'；'.join(task.measures)}\n"
            )
        lines.extend(["", "## 冗余候选", ""])
        for item in report.redundancy_results[:20]:
            lines.append(
                f"- {item.object_type}：`{item.left_object}` ↔ `{item.right_object}`，"
                f"相似度 {item.similarity:.3f}，风险 {item.risk_index:.3f}（{item.risk_level.value}）"
            )
        if self.robustness is not None:
            lines.extend(["", "## 稳健性分析", ""])
            lines.append(f"- 蒙特卡洛迭代：{self.robustness.iterations}")
            lines.append(f"- 综合分均值：{self.robustness.score_mean:.3f}")
            lines.append(f"- 5%—95%区间：{self.robustness.score_quantiles[0]:.3f}—{self.robustness.score_quantiles[2]:.3f}")
            lines.append(f"- 等级反转率：{self.robustness.grade_flip_rate:.2%}")
            lines.append(f"- 首要根因反转率：{self.robustness.top_root_cause_flip_rate:.2%}")
        lines.extend(["", "## 采集异常与待补证据", ""])
        if self.profile.issues:
            for issue in self.profile.issues:
                lines.append(f"- `{issue.object_name}` / {issue.operation}：{issue.message}")
        else:
            lines.append("- 无采集异常。")
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

    def export_figures(self, output_dir: str | Path, config) -> list:
        """批量生成论文图，并返回图形清单。

        Matplotlib作为可选依赖，仅在调用本方法时加载。
        """

        from ..visualization import PaperFigureGenerator

        generator = PaperFigureGenerator(config)
        return generator.generate_all(self, output_dir, robustness=self.robustness)

    def export_dashboard(self, artifacts: list, path: str | Path) -> Path:
        """导出引用已生成PNG图的静态HTML驾驶舱。"""

        from ..visualization.dashboard import export_dashboard

        return export_dashboard(self, artifacts, path)

    def export_html(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        md_path = output.with_suffix(".tmp.md")
        self.export_markdown(md_path)
        content = md_path.read_text(encoding="utf-8")
        md_path.unlink(missing_ok=True)
        body = "<pre>" + html.escape(content) + "</pre>"
        output.write_text(
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<title>EDQSG SQL Server评价报告</title>"
            "<style>body{font-family:system-ui,'Microsoft YaHei',sans-serif;max-width:1100px;"
            "margin:2rem auto;padding:0 1rem;line-height:1.65}pre{white-space:pre-wrap;"
            "background:#f7f7f8;padding:1.2rem;border-radius:8px}</style></head><body>"
            + body
            + "</body></html>",
            encoding="utf-8",
        )
        return output
