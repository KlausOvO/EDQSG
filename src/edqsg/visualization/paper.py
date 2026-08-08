"""[CORE] EDQSG论文图自动生成核心。

本模块坚持两个原则：
1. 图表必须对应明确的研究问题，而不是装饰性展示；
2. 每个图独立生成，便于在论文中单独编号、裁剪和替换。

只依赖 Matplotlib，不依赖 Seaborn。默认同时导出高分辨率PNG和SVG矢量图。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import numpy as np

from ..models import Domain, EvidenceType, RobustnessReport

if TYPE_CHECKING:
    from ..sqlserver.config import SQLServerVisualizationConfig
    from ..sqlserver.reporting import SQLServerPipelineResult


@dataclass(frozen=True)
class FigureArtifact:
    """单幅统计图的导出记录。"""

    figure_id: str
    title: str
    description: str
    files: tuple[str, ...]


class PaperFigureGenerator:
    """从SQL Server评价结果批量生成论文图和项目报告图。"""

    def __init__(self, config: "SQLServerVisualizationConfig"):
        self.config = config
        self.formats = tuple(fmt.lower() for fmt in config.formats)

    @staticmethod
    def _plt():
        """延迟导入Matplotlib，未安装可视化依赖时不影响模型内核运行。"""

        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:  # pragma: no cover - 依赖缺失分支
            raise RuntimeError(
                "生成统计图需安装Matplotlib：pip install edqsg[visualization]"
            ) from exc
        plt.rcParams["axes.unicode_minus"] = False
        # 优先注册系统中已有的CJK字体。这里只读取系统字体，不随项目分发字体文件。
        try:
            from matplotlib import font_manager

            candidates = [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf",
            ]
            family = None
            for candidate in candidates:
                if Path(candidate).exists():
                    font_manager.fontManager.addfont(candidate)
                    family = font_manager.FontProperties(fname=candidate).get_name()
                    break
            if family:
                plt.rcParams["font.family"] = family
            else:
                plt.rcParams["font.sans-serif"] = [
                    "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"
                ]
        except Exception:  # 字体检测失败不应阻断评价流程。
            plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        return plt

    def _save(self, fig, output_dir: Path, stem: str) -> tuple[str, ...]:
        output_dir.mkdir(parents=True, exist_ok=True)
        files: list[str] = []
        for fmt in self.formats:
            path = output_dir / f"{stem}.{fmt}"
            kwargs = {"bbox_inches": "tight"}
            if fmt == "png":
                kwargs["dpi"] = self.config.dpi
            fig.savefig(path, **kwargs)
            files.append(str(path))
        self._plt().close(fig)
        return tuple(files)

    @staticmethod
    def _indicator_label(item) -> str:
        return f"{item.indicator_id} {item.name}"

    @staticmethod
    def _weight_map(result: "SQLServerPipelineResult") -> dict[str, float]:
        metadata = result.assessment.metadata
        raw = metadata.get("indicator_weights", {})
        return {str(key): float(value) for key, value in raw.items()} if isinstance(raw, dict) else {}

    def plot_indicator_scores(self, result, output_dir: Path) -> FigureArtifact:
        """图1：双域指标得分，回答“系统短板在哪里”。"""

        plt = self._plt()
        items = sorted(
            result.assessment.indicator_results,
            key=lambda item: (item.domain.value, item.indicator_id),
            reverse=True,
        )
        labels = [self._indicator_label(item) for item in items]
        values = [item.score for item in items]
        fig, ax = plt.subplots(figsize=(10, max(5.5, len(items) * 0.38)))
        y = np.arange(len(items))
        bars = ax.barh(y, values)
        ax.set_yticks(y, labels)
        ax.set_xlim(0, 100)
        ax.set_xlabel("评价得分")
        ax.set_title("数据质量域与结构治理域一级指标得分")
        ax.grid(axis="x", alpha=0.25)
        for bar, value in zip(bars, values, strict=True):
            near_edge = value >= 94.0
            x_text = value - 1.0 if near_edge else value + 1.0
            ax.text(
                x_text,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}",
                va="center",
                ha="right" if near_edge else "left",
            )
        files = self._save(fig, output_dir, "fig01_indicator_scores")
        return FigureArtifact("F01", "双域指标得分图", "展示DQ1-DQ8与SG1-SG8的相对短板。", files)

    def plot_score_confidence(self, result, output_dir: Path) -> FigureArtifact:
        """图2：得分—可信度气泡图，回答“哪些结论确定、哪些需补证”。"""

        plt = self._plt()
        items = result.assessment.indicator_results
        weights = self._weight_map(result)
        fig, ax = plt.subplots(figsize=(9, 6.5))
        for domain in (Domain.DATA_QUALITY, Domain.STRUCTURAL_GOVERNANCE):
            group = [item for item in items if item.domain is domain]
            x = [item.score for item in group]
            y = [item.confidence for item in group]
            sizes = [160 + 1400 * weights.get(item.indicator_id, 1 / max(1, len(group))) for item in group]
            ax.scatter(x, y, s=sizes, alpha=0.65, label=domain.value)
            for index, item in enumerate(group):
                # 采用交错偏移减少右上角高分指标标签重叠，不引入额外依赖。
                offset_y = ((index % 5) - 2) * 7
                offset_x = 5 if index % 2 == 0 else -18
                ax.annotate(
                    item.indicator_id,
                    (item.score, item.confidence),
                    xytext=(offset_x, offset_y),
                    textcoords="offset points",
                    fontsize=8,
                )
        ax.axvline(70, linestyle="--", linewidth=1)
        ax.axhline(0.70, linestyle="--", linewidth=1)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 1.03)
        ax.set_xlabel("指标得分")
        ax.set_ylabel("评价可信度")
        ax.set_title("指标得分—可信度联合分布")
        ax.grid(alpha=0.25)
        ax.legend(title="评价域")
        files = self._save(fig, output_dir, "fig02_score_confidence")
        return FigureArtifact("F02", "得分—可信度气泡图", "定位低分高可信度治理重点和低可信度待复核指标。", files)

    def plot_evidence_composition(self, result, output_dir: Path) -> FigureArtifact:
        """图3：五类证据贡献与未知度，体现EDQSG的证据驱动特征。"""

        plt = self._plt()
        items = sorted(result.assessment.indicator_results, key=lambda item: item.indicator_id)
        types = list(EvidenceType)
        labels = [item.indicator_id for item in items]
        matrix = np.zeros((len(items), len(types) + 1), dtype=float)
        for row, item in enumerate(items):
            for evidence in item.evidence_results:
                col = types.index(evidence.evidence_type)
                matrix[row, col] += evidence.effective_reliability
            total = matrix[row, :-1].sum()
            if total > 0:
                matrix[row, :-1] *= (1.0 - item.unknown_degree) / total
            matrix[row, -1] = item.unknown_degree
        fig, ax = plt.subplots(figsize=(11, 6.5))
        x = np.arange(len(items))
        bottom = np.zeros(len(items))
        legend_labels = [item.value for item in types] + ["unknown"]
        for col, label in enumerate(legend_labels):
            values = matrix[:, col]
            ax.bar(x, values, bottom=bottom, label=label)
            bottom += values
        ax.set_xticks(x, labels, rotation=45, ha="right")
        ax.set_ylim(0, 1)
        ax.set_ylabel("证据贡献比例")
        ax.set_title("一级指标的多源证据构成与未知度")
        ax.legend(ncol=3)
        ax.grid(axis="y", alpha=0.2)
        files = self._save(fig, output_dir, "fig03_evidence_composition")
        return FigureArtifact("F03", "证据构成图", "展示数据、结构、规则、过程、专家证据及未知度。", files)

    def plot_coupling_heatmap(self, result, output_dir: Path) -> FigureArtifact | None:
        """图4：Q-S耦合热力图，回答“结构缺陷如何影响数据质量”。"""

        relations = result.assessment.coupling_relations
        if not relations:
            return None
        plt = self._plt()
        dq_ids = sorted({item.dq_indicator_id for item in relations})
        sg_ids = sorted({item.sg_indicator_id for item in relations})
        matrix = np.full((len(dq_ids), len(sg_ids)), np.nan)
        confidence = np.full_like(matrix, np.nan)
        for relation in relations:
            i = dq_ids.index(relation.dq_indicator_id)
            j = sg_ids.index(relation.sg_indicator_id)
            matrix[i, j] = relation.strength
            confidence[i, j] = relation.confidence
        fig, ax = plt.subplots(figsize=(9, 6.5))
        image = ax.imshow(matrix, vmin=0, vmax=1, aspect="auto")
        fig.colorbar(image, ax=ax, label="耦合强度")
        ax.set_xticks(np.arange(len(sg_ids)), sg_ids)
        ax.set_yticks(np.arange(len(dq_ids)), dq_ids)
        ax.set_xlabel("结构治理指标")
        ax.set_ylabel("数据质量指标")
        ax.set_title("数据质量—结构治理耦合关系")
        for i in range(len(dq_ids)):
            for j in range(len(sg_ids)):
                if np.isfinite(matrix[i, j]):
                    marker = "*" if confidence[i, j] >= 0.70 else ""
                    ax.text(j, i, f"{matrix[i, j]:.2f}{marker}", ha="center", va="center", fontsize=8)
        files = self._save(fig, output_dir, "fig04_qs_coupling_heatmap")
        return FigureArtifact("F04", "Q-S耦合热力图", "颜色表示耦合强度，星号表示较高可信度。", files)

    def plot_root_causes(self, result, output_dir: Path) -> FigureArtifact | None:
        """图5：根因贡献度排序。"""

        items = result.assessment.root_causes[: self.config.top_n]
        if not items:
            return None
        plt = self._plt()
        items = list(reversed(items))
        labels = [item.sg_indicator_id for item in items]
        values = [item.contribution for item in items]
        fig, ax = plt.subplots(figsize=(8.5, max(4.5, len(items) * 0.45)))
        bars = ax.barh(labels, values)
        ax.set_xlabel("根因贡献度")
        ax.set_title("结构治理根因贡献度排序")
        ax.grid(axis="x", alpha=0.25)
        for bar, item in zip(bars, items, strict=True):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {item.contribution:.4f} / C={item.confidence:.2f}", va="center")
        files = self._save(fig, output_dir, "fig05_root_cause_ranking")
        return FigureArtifact("F05", "根因贡献度排序图", "显示结构治理根因及其结论可信度。", files)

    def plot_governance_priority(self, result, output_dir: Path) -> FigureArtifact | None:
        """图6：治理任务成本—优先级四象限。"""

        tasks = result.assessment.governance_tasks[: self.config.top_n]
        if not tasks:
            return None
        plt = self._plt()
        fig, ax = plt.subplots(figsize=(9, 6.5))
        x = [task.cost for task in tasks]
        y = [task.priority for task in tasks]
        sizes = [120 + 900 * task.impact for task in tasks]
        ax.scatter(x, y, s=sizes, alpha=0.65)
        for task in tasks:
            ax.annotate(task.task_id, (task.cost, task.priority), xytext=(4, 4), textcoords="offset points", fontsize=8)
        ax.axvline(float(np.median(x)), linestyle="--", linewidth=1)
        ax.axhline(float(np.median(y)), linestyle="--", linewidth=1)
        ax.set_xlabel("治理成本（标准化值）")
        ax.set_ylabel("治理优先级")
        ax.set_title("治理任务成本—优先级分布")
        ax.grid(alpha=0.25)
        files = self._save(fig, output_dir, "fig06_governance_priority")
        return FigureArtifact("F06", "治理任务优先级图", "支持识别高收益低成本的优先治理任务。", files)

    def plot_redundancy_risk(self, result, output_dir: Path) -> FigureArtifact | None:
        """图7：冗余相似度—风险指数散点图。"""

        items = sorted(result.assessment.redundancy_results, key=lambda item: item.risk_index, reverse=True)[: self.config.top_n]
        if not items:
            return None
        plt = self._plt()
        fig, ax = plt.subplots(figsize=(9, 6.5))
        x = [item.similarity for item in items]
        y = [item.risk_index for item in items]
        sizes = [120 + 850 * item.impact for item in items]
        ax.scatter(x, y, s=sizes, alpha=0.65)
        for index, item in enumerate(items, start=1):
            ax.annotate(f"R{index}", (item.similarity, item.risk_index), xytext=(4, 4), textcoords="offset points")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, max(1.0, max(y) * 1.1))
        ax.set_xlabel("冗余相似度")
        ax.set_ylabel("冗余风险指数")
        ax.set_title("字段与表冗余候选风险分布")
        ax.grid(alpha=0.25)
        files = self._save(fig, output_dir, "fig07_redundancy_risk")
        return FigureArtifact("F07", "冗余风险图", "区分高相似受控冗余与高风险非受控冗余。", files)

    def plot_table_scale(self, result, output_dir: Path) -> FigureArtifact | None:
        """图8：数据库表规模统计。"""

        tables = sorted(result.metadata.tables, key=lambda item: item.row_count, reverse=True)[: self.config.top_n]
        if not tables:
            return None
        plt = self._plt()
        tables = list(reversed(tables))
        labels = [item.qualified_name for item in tables]
        values = [max(0, item.row_count) for item in tables]
        fig, ax = plt.subplots(figsize=(9, max(4.5, len(tables) * 0.42)))
        ax.barh(labels, values)
        ax.set_xlabel("记录数")
        ax.set_title("数据库表规模分布（Top N）")
        if max(values, default=0) > 10000:
            ax.set_xscale("symlog", linthresh=10)
        ax.grid(axis="x", alpha=0.25)
        files = self._save(fig, output_dir, "fig08_table_scale")
        return FigureArtifact("F08", "表规模分布图", "展示记录数最多的业务表。", files)

    def plot_missing_fields(self, result, output_dir: Path) -> FigureArtifact | None:
        """图9：字段缺失率排序。"""

        columns = sorted(result.profile.columns, key=lambda item: item.missing_rate, reverse=True)
        columns = [item for item in columns if item.missing_rate > 0][: self.config.top_n]
        if not columns:
            return None
        plt = self._plt()
        columns = list(reversed(columns))
        labels = [f"{item.table}.{item.column}" for item in columns]
        values = [100 * item.missing_rate for item in columns]
        fig, ax = plt.subplots(figsize=(10, max(4.5, len(columns) * 0.42)))
        ax.barh(labels, values)
        ax.set_xlabel("缺失率（%）")
        ax.set_title("字段缺失率排序（Top N）")
        ax.grid(axis="x", alpha=0.25)
        files = self._save(fig, output_dir, "fig09_field_missing_rate")
        return FigureArtifact("F09", "字段缺失率图", "定位缺失问题最集中的表和字段。", files)

    @staticmethod
    def _violation_counts(result) -> list[tuple[str, int]]:
        profile = result.profile
        counts = {
            "字段缺失": sum(item.missing_count for item in profile.columns),
            "必填缺失": sum(item.missing_count for item in profile.required_columns),
            "业务键重复": sum(item.duplicate_rows for item in profile.business_keys),
            "孤儿记录": sum(item.orphan_count for item in profile.foreign_keys),
            "超期记录": sum(item.stale_count for item in profile.freshness),
            "非法值域": sum(item.invalid_count for item in profile.domains),
            "自定义规则违规": sum(item.invalid_count for item in profile.custom_rules),
        }
        return sorted(((name, value) for name, value in counts.items() if value > 0), key=lambda item: item[1], reverse=True)

    def plot_violation_pareto(self, result, output_dir: Path) -> FigureArtifact | None:
        """图10：违规类型帕累托图，识别主要问题来源。"""

        data = self._violation_counts(result)
        if not data:
            return None
        plt = self._plt()
        labels = [item[0] for item in data]
        values = np.asarray([item[1] for item in data], dtype=float)
        cumulative = 100 * np.cumsum(values) / values.sum()
        fig, ax = plt.subplots(figsize=(9, 6))
        bars = ax.bar(np.arange(len(labels)), values)
        ax.set_xticks(np.arange(len(labels)), labels, rotation=30, ha="right")
        ax.set_ylabel("违规记录数")
        ax.set_title("数据质量违规类型帕累托图")
        ax.grid(axis="y", alpha=0.2)
        # 将累计比例以文本形式标注在柱顶，避免双纵轴造成误读。
        for bar, pct in zip(bars, cumulative, strict=True):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{pct:.0f}%", ha="center", va="bottom", fontsize=8)
        files = self._save(fig, output_dir, "fig10_violation_pareto")
        return FigureArtifact("F10", "违规类型帕累托图", "柱高为违规数，柱顶为累计贡献比例。", files)

    def plot_robustness_distribution(self, robustness: RobustnessReport, output_dir: Path) -> FigureArtifact | None:
        """图11：蒙特卡洛综合得分分布。"""

        if not robustness.score_samples:
            return None
        plt = self._plt()
        values = np.asarray(robustness.score_samples, dtype=float)
        fig, ax = plt.subplots(figsize=(8.5, 5.8))
        ax.hist(values, bins="auto", alpha=0.75)
        ax.axvline(robustness.baseline_score, linestyle="--", linewidth=1.5, label="基线")
        ax.axvline(robustness.score_quantiles[0], linestyle=":", linewidth=1, label="5%分位")
        ax.axvline(robustness.score_quantiles[2], linestyle=":", linewidth=1, label="95%分位")
        ax.set_xlabel("综合评价得分")
        ax.set_ylabel("模拟次数")
        ax.set_title("EDQSG蒙特卡洛稳健性分布")
        ax.legend()
        ax.grid(axis="y", alpha=0.2)
        files = self._save(fig, output_dir, "fig11_robustness_distribution")
        return FigureArtifact("F11", "蒙特卡洛得分分布图", "展示参数扰动下综合分的分布和区间。", files)

    def plot_root_stability(self, robustness: RobustnessReport, output_dir: Path) -> FigureArtifact | None:
        """图12：首要根因出现概率。"""

        data = robustness.top_root_cause_probabilities[: self.config.top_n]
        if not data:
            return None
        plt = self._plt()
        data = list(reversed(data))
        labels = [item[0] for item in data]
        values = [100 * item[1] for item in data]
        fig, ax = plt.subplots(figsize=(8.5, max(4.2, len(data) * 0.42)))
        ax.barh(labels, values)
        ax.set_xlim(0, 100)
        ax.set_xlabel("成为首要根因的概率（%）")
        ax.set_title("结构治理根因排名稳定性")
        ax.grid(axis="x", alpha=0.25)
        files = self._save(fig, output_dir, "fig12_root_cause_stability")
        return FigureArtifact("F12", "根因排名稳定性图", "展示蒙特卡洛模拟中各指标成为首要根因的概率。", files)

    def generate_all(
        self,
        result: "SQLServerPipelineResult",
        output_dir: str | Path,
        robustness: RobustnessReport | None = None,
    ) -> list[FigureArtifact]:
        """生成全部有数据支撑的图；无适用数据的图会自动跳过。"""

        directory = Path(output_dir)
        builders = [
            self.plot_indicator_scores,
            self.plot_score_confidence,
            self.plot_evidence_composition,
            self.plot_coupling_heatmap,
            self.plot_root_causes,
            self.plot_governance_priority,
            self.plot_redundancy_risk,
            self.plot_table_scale,
            self.plot_missing_fields,
            self.plot_violation_pareto,
        ]
        artifacts: list[FigureArtifact] = []
        for builder in builders:
            artifact = builder(result, directory)
            if artifact is not None:
                artifacts.append(artifact)
        if robustness is not None:
            for builder in (self.plot_robustness_distribution, self.plot_root_stability):
                artifact = builder(robustness, directory)
                if artifact is not None:
                    artifacts.append(artifact)
        return artifacts
