"""EDQSG静态HTML可视化驾驶舱。"""

from __future__ import annotations

import html
from pathlib import Path

from .paper import FigureArtifact


def export_dashboard(result, artifacts: list[FigureArtifact], path: str | Path) -> Path:
    """将综合分、关键风险和统计图组合为无需服务器的静态HTML。"""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for artifact in artifacts:
        png = next((Path(item) for item in artifact.files if item.lower().endswith(".png")), None)
        if png is None:
            continue
        relative = png.relative_to(output.parent) if png.is_relative_to(output.parent) else png
        cards.append(
            "<section class='figure-card'>"
            f"<h2>{html.escape(artifact.figure_id)} · {html.escape(artifact.title)}</h2>"
            f"<p>{html.escape(artifact.description)}</p>"
            f"<img src='{html.escape(relative.as_posix())}' alt='{html.escape(artifact.title)}'>"
            "</section>"
        )
    report = result.assessment
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'>
<title>EDQSG可视化驾驶舱</title>
<style>
body{{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;background:#f4f5f7;line-height:1.55}}
main{{max-width:1280px;margin:auto;padding:24px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:24px}}
.metric,.figure-card{{background:white;border-radius:10px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.metric strong{{display:block;font-size:1.8rem;margin-top:5px}}
.figure-card{{margin-bottom:20px}} .figure-card img{{width:100%;height:auto}}
.warning{{background:white;padding:16px;border-radius:10px;margin-bottom:20px}}
</style></head><body><main>
<h1>EDQSG SQL Server评价可视化驾驶舱</h1>
<p>数据库：{html.escape(result.metadata.database_name)}　采集时间：{html.escape(result.metadata.collected_at)}</p>
<div class='summary'>
<div class='metric'>数据质量域 Q<strong>{report.dq.score:.2f}</strong></div>
<div class='metric'>结构治理域 S<strong>{report.sg.score:.2f}</strong></div>
<div class='metric'>最终综合分<strong>{report.final_score:.2f}</strong></div>
<div class='metric'>评价等级<strong>{html.escape(report.overall_grade.value)}</strong></div>
<div class='metric'>综合可信度<strong>{report.overall_confidence:.3f}</strong></div>
<div class='metric'>底线风险数<strong>{len(report.bottom_line_triggers)}</strong></div>
</div>
<div class='warning'><strong>解释提示：</strong>图表用于定位问题、分析成因和展示治理效果；低可信度或高未知度指标仍需补充业务证据。</div>
{''.join(cards)}
</main></body></html>"""
    output.write_text(content, encoding="utf-8")
    return output
