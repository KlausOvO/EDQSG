# -*- coding: utf-8 -*-
"""重绘 EDQSG 论文图 1（总体运行逻辑）与图 2（算法总体流程）。

同一份布局数据输出两种产物：
  1) draw.io XML（mxfile），供在 draw.io 中继续微调；
  2) matplotlib PNG/SVG，与 XML 使用相同坐标与配色，供论文排版。

版式约定（对应《兵器装备工程学报》模板）：
  图内文字用楷体；图 1 双栏宽度（约 15 cm），图 2 单栏宽度（约 7.2 cm）；
  配色按功能分层：证据输入（橙）、证据处理/评价（蓝）、双域（绿）、
  底线/输出（黄）、根因/治理（紫），反馈路径用虚线。
"""

from __future__ import annotations

import html
import os
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


OUT = os.path.dirname(os.path.abspath(__file__))
KAITI_CANDIDATES = [
    r"C:\Windows\Fonts\simkai.ttf",
    r"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
KAITI = next((p for p in KAITI_CANDIDATES if os.path.exists(p)), None)
if KAITI is None:
    raise SystemExit("未找到楷体字体（simkai.ttf），请安装后重试或修改 KAITI_CANDIDATES")
font_manager.fontManager.addfont(KAITI)
KAI_PROP = FontProperties(fname=KAITI)
matplotlib.rcParams.update({
    "font.family": [KAI_PROP.get_name(), "Arial", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "svg.fonttype": "none",   # editable text in SVG
    "pdf.fonttype": 42,       # editable TrueType text in PDF
    "font.size": 10,
    "axes.linewidth": 0.8,
})
# 目标期刊版式：图 1 双栏宽约 150 mm，图 2 单栏宽约 72 mm（图内文字 7~8 级楷体）

# ---------------- 调色板（两图共用，按功能分层） ----------------
C_INPUT = ("#FBE5D6", "#C55A11")   # 证据/输入
C_PROC = ("#DEEBF7", "#2F5597")    # 处理/评价
C_DOMAIN = ("#E2F0D9", "#538135")  # Q/S 双域
C_OUT = ("#FFF2CC", "#BF8F00")     # 底线/输出
C_GOV = ("#E4DFEC", "#5B3E96")     # 根因/治理
C_NEUTRAL = ("#F2F2F2", "#595959") # 中性
C_EDGE = "#2F5597"
C_FEEDBACK = "#7F6000"


# ---------------- 图 1：总体运行逻辑 ----------------
FIG1 = {
    "name": "图1 EDQSG总体运行逻辑",
    "width": 1000,
    "height": 700,
    "figsize": (10.0, 7.0),
    "feedback_label_rotation": 90,
    "nodes": [
        ("ev1", "数据内容证据\n（全量剖析）", 90, 20, 140, 50, C_INPUT),
        ("ev2", "结构元数据证据\n（DDL/约束）", 260, 20, 140, 50, C_INPUT),
        ("ev3", "规则标准证据\n（标准/制度）", 430, 20, 140, 50, C_INPUT),
        ("ev4", "运行过程证据\n（日志/问题单）", 600, 20, 140, 50, C_INPUT),
        ("ev5", "专家判断证据\n（评审）", 770, 20, 140, 50, C_INPUT),
        ("proc", "证据可靠性折扣与 ER 融合\n（未知度、冲突度显式保留，式1~4）", 100, 108, 800, 54, C_PROC),
        ("q", "数据质量域 Q\n结果状态（DQ1~DQ8）", 100, 200, 390, 64, C_DOMAIN),
        ("s", "结构治理域 S\n成因与持续控制（SG1~SG8）", 510, 200, 390, 64, C_DOMAIN),
        ("g0", "双域聚合 G0\n（式7、8）", 100, 304, 230, 50, C_PROC),
        ("bl", "非补偿底线限级\n（式9）", 385, 304, 230, 50, C_OUT),
        ("g", "总体等级与证据覆盖率", 670, 304, 230, 50, C_OUT),
        ("rc", "Q-S 耦合根因排序\n（三源校准，式10~13）", 100, 394, 390, 54, C_GOV),
        ("gov", "治理任务与复评闭环\n（对象/责任/措施/验收）", 510, 394, 390, 54, C_GOV),
    ],
    "edges": [
        ("ev1", "proc", False, None),
        ("ev2", "proc", False, None),
        ("ev3", "proc", False, None),
        ("ev4", "proc", False, None),
        ("ev5", "proc", False, None),
        ("proc", "q", False, None),
        ("proc", "s", False, None),
        ("q", "g0", False, None),
        ("s", "g0", False, None),
        ("g0", "bl", False, None),
        ("bl", "g", False, None),
        ("g", "rc", False, None),
        ("rc", "gov", False, None),
        ("gov", "proc", True, "复评：重新采集证据，反向校准参数"),
    ],
}


# ---------------- 图 2：算法总体流程 ----------------
FIG2 = {
    "name": "图2 EDQSG算法总体流程",
    "width": 1040,
    "height": 1600,
    "figsize": (6.5, 10.0),
    "feedback_label_rotation": 90,
    "nodes": [
        ("in", "输入：五类证据、指标字典、预期关系清单、底线清单", 140, 25, 760, 60, C_INPUT),
        ("s1", "步骤1  证据采集与可靠性评估（式1）", 140, 125, 760, 72, C_PROC),
        ("s2", "步骤2  证据折扣与 ER 融合、冲突检测（式2~4）", 140, 225, 760, 72, C_PROC),
        ("s3", "步骤3  指标评分：已知期望分与可信度（式3）", 140, 325, 760, 72, C_PROC),
        ("s4", "步骤4  域内聚合与综合可信度（式5、6）", 140, 425, 760, 72, C_PROC),
        ("s5", "步骤5  双域聚合与协同度（式7、8）", 140, 525, 760, 72, C_PROC),
        ("s6", "步骤6  底线约束与等级判定（式9）", 140, 625, 760, 72, C_OUT),
        ("s7", "步骤7  Q-S 耦合校准与根因排序（式10~13）", 140, 725, 760, 72, C_GOV),
        ("s8", "步骤8  治理任务生成与复评更新", 140, 825, 760, 72, C_GOV),
        ("out", "输出：评价报告、复核清单、治理任务清单", 140, 940, 760, 56, C_NEUTRAL),
    ],
    "edges": [
        ("in", "s1", False, None),
        ("s1", "s2", False, None),
        ("s2", "s3", False, None),
        ("s3", "s4", False, None),
        ("s4", "s5", False, None),
        ("s5", "s6", False, None),
        ("s6", "s7", False, None),
        ("s7", "s8", False, None),
        ("s8", "out", False, None),
        ("out", "s1", True, "复评反馈：重新采集证据，反向校准参数"),
    ],
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def drawio_style(fill, stroke, dashed=False) -> str:
    base = (
        "rounded=1;whiteSpace=wrap;html=1;fontFamily=KaiTi;fontSize=10;"
        "fillColor=%s;strokeColor=%s;verticalAlign=middle;"
    ) % (fill, stroke)
    if dashed:
        base += "dashed=1;"
    return base


def export_drawio(spec: dict, out_xml: str) -> None:
    nodes = {nid: (label, x, y, w, h, (fill, stroke)) for nid, label, x, y, w, h, (fill, stroke) in spec["nodes"]}

    root = ET.Element("mxfile")
    root.set("host", "app.diagrams.net")
    root.set("type", "device")
    diagram = ET.SubElement(root, "diagram")
    diagram.set("id", spec["name"])
    diagram.set("name", spec["name"])
    model = ET.SubElement(diagram, "mxGraphModel")
    model.set("dx", "1200")
    model.set("dy", "800")
    model.set("grid", "1")
    model.set("gridSize", "10")
    model.set("guides", "1")
    model.set("tooltips", "1")
    model.set("connect", "1")
    model.set("arrows", "1")
    model.set("fold", "1")
    model.set("page", "1")
    model.set("pageScale", "1")
    model.set("pageWidth", str(spec["width"]))
    model.set("pageHeight", str(spec["height"]))
    model.set("math", "0")
    model.set("shadow", "0")
    cell_root = ET.SubElement(model, "root")
    ET.SubElement(cell_root, "mxCell", id="0")
    ET.SubElement(cell_root, "mxCell", id="1", parent="0")
    for nid, (label, x, y, w, h, (fill, stroke)) in nodes.items():
        cell = ET.SubElement(
            cell_root, "mxCell",
            id=nid, value=esc(label).replace("\n", "&#10;"),
            style=drawio_style(fill, stroke),
            vertex="1", parent="1",
        )
        geo = ET.SubElement(cell, "mxGeometry")
        geo.set("x", str(x))
        geo.set("y", str(y))
        geo.set("width", str(w))
        geo.set("height", str(h))
        geo.set("as", "geometry")
    for idx, (src, dst, dashed, label) in enumerate(spec["edges"]):
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
            "jettySize=auto;html=1;endArrow=block;endFill=1;"
            "strokeColor=%s;fontFamily=KaiTi;fontSize=9;"
        ) % (C_FEEDBACK if dashed else C_EDGE)
        if dashed:
            style += "dashed=1;"
        cell = ET.SubElement(
            cell_root, "mxCell",
            id="e%d" % idx, value="",
            style=style, edge="1", parent="1", source=src, target=dst,
        )
        geo = ET.SubElement(cell, "mxGeometry")
        geo.set("relative", "1")
        geo.set("as", "geometry")
        if label and not spec.get("feedback_label_rotation"):
            cell.set("value", esc(label).replace("\n", "&#10;"))
        if label and spec.get("feedback_label_rotation"):
            _, sx, sy, sw, sh, _ = nodes[src]
            _, dx, dy, dw, dh, _ = nodes[dst]
            rx1, ry1 = sx + sw, sy + sh / 2
            rx2, ry2 = dx + dw, dy + dh / 2
            mid_x = max(rx1, rx2) + 10
            mid_y = (ry1 + ry2) / 2
            label_len = len(label) * 17
            lab = ET.SubElement(
                cell_root, "mxCell",
                id="lab%d" % idx, value=esc(label),
                style=(
                    "text;html=1;fontFamily=KaiTi;fontSize=9;"
                    "rotation=%d;align=center;verticalAlign=middle;"
                ) % (-spec["feedback_label_rotation"]),
                vertex="1", parent="1",
            )
            lgeo = ET.SubElement(lab, "mxGeometry")
            lgeo.set("x", str(mid_x))
            lgeo.set("y", str(mid_y - label_len / 2))
            lgeo.set("width", "26")
            lgeo.set("height", str(label_len))
            lgeo.set("as", "geometry")
    tree = ET.ElementTree(root)
    tree.write(out_xml, encoding="utf-8", xml_declaration=True)
    print("draw.io XML saved:", out_xml)


def node_rect(node):
    _, _, x, y, w, h, _ = node
    return x, y, w, h


def render_matplotlib(spec: dict, out_png: str, out_svg: str, font_size: int) -> None:
    w_abs, h_abs = spec["width"], spec["height"]
    fw, fh = spec["figsize"]
    fig, ax = plt.subplots(figsize=(fw, fh))
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_xlim(0, w_abs)
    ax.set_ylim(0, h_abs)
    ax.axis("off")
    nodes = {nid: node for node in spec["nodes"] for nid in [node[0]]}

    for nid, label, x, y, w, h, (fill, stroke) in spec["nodes"]:
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=6,rounding_size=10",
                fc=fill, ec=stroke, lw=1.4,
            )
        )
        ax.text(
            x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=font_size, linespacing=1.55, color="#1F1F1F",
        )

    def edge_endpoints(src, dst, side="bottom_top"):
        sx, sy, sw, sh = node_rect(nodes[src])
        dx, dy, dw, dh = node_rect(nodes[dst])
        if side == "right_right":
            return (sx + sw, sy + sh / 2), (dx + dw, dy + dh / 2)
        return (sx + sw / 2, sy + sh), (dx + dw / 2, dy)

    def draw_edge(src, dst, dashed, label):
        color = C_FEEDBACK if dashed else C_EDGE
        if not dashed:
            (x1, y1), (x2, y2) = edge_endpoints(src, dst)
            ax.add_patch(
                FancyArrowPatch(
                    (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18,
                    lw=1.5, color=color,
                )
            )
        else:
            # 正交虚线反馈路径：从源框右侧出发、经右缘绕行回到目标框右侧
            (x1, y1), (x2, y2) = edge_endpoints(src, dst, side="right_right")
            mid_x = max(x1, x2) + 10
            pts = [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]
            ax.add_patch(
                FancyArrowPatch(
                    path=Path(pts), arrowstyle="-|>", mutation_scale=18,
                    linestyle=(0, (4, 3)), lw=1.4, color=color,
                )
            )
            if label:
                rotation = spec.get("feedback_label_rotation")
                if rotation:
                    ax.text(
                        mid_x + 12, (y1 + y2) / 2, label, rotation=rotation,
                        ha="center", va="center",
                        fontsize=font_size - 2, color=C_FEEDBACK,
                    )
                else:
                    ax.text(
                        mid_x + 10, (y1 + y2) / 2, label, ha="left", va="center",
                        fontsize=font_size - 1, color=C_FEEDBACK, linespacing=1.5,
                    )

    for src, dst, dashed, label in spec["edges"]:
        draw_edge(src, dst, dashed, label)

    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(out_svg, bbox_inches="tight", facecolor="white")
    fig.savefig(out_png.replace(".png", ".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(out_png.replace(".png", ".tiff"), dpi=600, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("PNG saved:", out_png)
    print("SVG saved:", out_svg)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    export_drawio(FIG1, os.path.join(OUT, "fig1.xml"))
    export_drawio(FIG2, os.path.join(OUT, "fig2.xml"))
    render_matplotlib(
        FIG1,
        os.path.join(OUT, "fig1.png"),
        os.path.join(OUT, "fig1.svg"),
        font_size=12,
    )
    render_matplotlib(
        FIG2,
        os.path.join(OUT, "fig2_algo.png"),
        os.path.join(OUT, "fig2.svg"),
        font_size=17,
    )


if __name__ == "__main__":
    main()
