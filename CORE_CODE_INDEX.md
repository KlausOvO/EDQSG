# EDQSG 核心代码索引

本文件用于快速定位论文模型、SQL Server自动分析和可视化的关键实现。标记为 **核心** 的文件建议优先阅读，普通配置、示例和测试文件作为辅助。

## 一、模型计算核心

| 级别 | 文件 | 主要职责 |
|---|---|---|
| 核心 | `src/edqsg/core.py` | EDQSG总入口，组装证据融合、双域评分、底线约束、耦合诊断和治理任务 |
| 核心 | `src/edqsg/evidence.py` | 五维证据可靠性、可靠性折扣、ER/DS组合、冲突与未知度处理 |
| 核心 | `src/edqsg/scoring.py` | DQ/SG域评分、几何综合、平衡度、综合可信度与等级判定 |
| 核心 | `src/edqsg/coupling.py` | 规范—专家—数据三源耦合校准和根因贡献度 |
| 核心 | `src/edqsg/bottom_line.py` | 非补偿性底线限级和惩罚 |
| 核心 | `src/edqsg/governance.py` | 治理任务生成、底线任务优先和成本—收益排序 |
| 重要 | `src/edqsg/redundancy.py` | 字段冗余和表冗余风险评价 |
| 重要 | `src/edqsg/robustness.py` | 蒙特卡洛敏感性和关键排序稳定性分析 |
| 基础 | `src/edqsg/models.py` | 全部领域对象、报告对象和可序列化数据结构 |

## 二、SQL Server自动分析核心

| 级别 | 文件 | 主要职责 |
|---|---|---|
| 核心 | `src/edqsg/sqlserver/pipeline.py` | 从数据库连接到模型、图表和报告的一体化流水线 |
| 核心 | `src/edqsg/sqlserver/analyzer.py` | 将SQL Server元数据和剖析结果映射为DQ1—DQ8、SG1—SG8证据 |
| 重要 | `src/edqsg/sqlserver/metadata.py` | 读取表、字段、主外键、索引、检查约束和说明 |
| 重要 | `src/edqsg/sqlserver/profiler.py` | 数据库端聚合检测缺失、重复、孤儿、值域、时效性和自定义规则 |
| 重要 | `src/edqsg/sqlserver/adapter.py` | SQLAlchemy＋pyodbc只读连接和安全查询执行 |
| 配置 | `src/edqsg/sqlserver/config.py` | 数据库、扫描、RelationshipControlRule、业务规则、图形和稳健性配置 |
| 输出 | `src/edqsg/sqlserver/reporting.py` | JSON、Markdown、HTML、图形与驾驶舱导出 |

## 三、统计图与论文图核心

| 级别 | 文件 | 主要职责 |
|---|---|---|
| 核心 | `src/edqsg/visualization/paper.py` | 自动生成指标得分、可信度、证据构成、耦合、根因、治理、冗余和稳健性图 |
| 重要 | `src/edqsg/visualization/dashboard.py` | 将综合指标和PNG图组合成静态HTML驾驶舱 |

## 四、推荐阅读顺序

1. `models.py`：了解输入输出结构；
2. `evidence.py`：理解“证据驱动”的计算逻辑；
3. `core.py`：理解完整模型调用链；
4. `sqlserver/pipeline.py`：理解数据库自动分析流程；
5. `sqlserver/analyzer.py`：理解数据库指标如何映射到EDQSG；
6. `visualization/paper.py`：理解论文图的生成规则。

## 五、核心调用链

```text
SQLServerAssessmentPipeline.run()
    ├── SQLServerMetadataCollector.collect()
    ├── SQLServerProfiler.profile()
    ├── SQLServerEvidenceBuilder.build_indicators()
    ├── EDQSGModel.evaluate()
    │     ├── EvidenceFusionEngine.fuse()
    │     ├── ScoreCalculator.domain_assessment()
    │     ├── BottomLineEngine.apply()
    │     ├── CouplingAnalyzer.analyze()
    │     └── GovernanceTaskPlanner.build_tasks()
    ├── EDQSGModel.robustness()（可选）
    └── PaperFigureGenerator.generate_all()
```
