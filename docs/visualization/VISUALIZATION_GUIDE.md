# EDQSG统计图与论文图使用指南

## 1. 输出目标

0.4.0将EDQSG结果分为四类图：

1. **评价结果图**：指标得分、得分—可信度、证据构成；
2. **诊断决策图**：Q-S耦合、根因贡献、治理任务、冗余风险；
3. **数据库描述图**：表规模、字段缺失、违规类型；
4. **模型验证图**：蒙特卡洛得分分布、根因排名稳定性。

所有图由 `src/edqsg/visualization/paper.py` 独立生成，一幅图对应一个研究问题，不使用多子图拼接。

## 2. 推荐论文图

| 文件 | 建议论文名称 | 研究问题 |
|---|---|---|
| `fig01_indicator_scores` | 双域一级指标评价结果 | 系统的主要短板是什么 |
| `fig02_score_confidence` | 指标得分与评价可信度联合分布 | 哪些结论确定，哪些需补证 |
| `fig03_evidence_composition` | 指标多源证据构成与未知度 | 评价依据来自哪里 |
| `fig04_qs_coupling_heatmap` | 数据质量—结构治理耦合关系 | 结构问题如何影响质量 |
| `fig05_root_cause_ranking` | 结构治理根因贡献度 | 哪些结构缺陷是主要根因 |
| `fig06_governance_priority` | 治理任务成本—优先级 | 资源应优先投向哪里 |
| `fig07_redundancy_risk` | 字段与表冗余风险 | 哪些冗余需要治理 |
| `fig08_table_scale` | 数据库表规模分布 | 数据规模和扫描边界如何 |
| `fig09_field_missing_rate` | 字段缺失率排序 | 缺失集中在哪些字段 |
| `fig10_violation_pareto` | 数据质量违规类型帕累托图 | 主要质量问题是什么 |
| `fig11_robustness_distribution` | 蒙特卡洛综合得分分布 | 综合评价是否稳健 |
| `fig12_root_cause_stability` | 首要根因排名稳定性 | 根因排序是否稳定 |

## 3. 配置

```yaml
visualization:
  enabled: true
  formats: ["png", "svg"]
  dpi: 300
  top_n: 15
  generate_dashboard: true
  generate_robustness: false
  robustness_iterations: 500
  robustness_perturbation: 0.10
```

- `formats`：支持 `png`、`svg`、`pdf`；
- `dpi`：只影响位图，论文建议300及以上；
- `top_n`：治理任务、根因、冗余和字段排序展示数量；
- `generate_dashboard`：是否输出静态HTML驾驶舱；
- `generate_robustness`：是否在每次数据库评价后执行蒙特卡洛；
- `robustness_iterations`：正式论文建议不少于1000，首次调试可设为50—200；
- `robustness_perturbation`：参数相对扰动幅度。

## 4. 图形解释边界

- 气泡大小表示指标权重或业务影响，不表示样本量；
- Q-S热力图展示模型校准后的耦合强度，不应直接解释为严格因果效应；
- 冗余图仅输出候选关系，不能据此自动删除表或字段；
- `sample`模式得到的字段缺失率属于样本结果，正式论文关键结论应使用`full`模式验证；
- 违规帕累托图中不同违规类型的适用分母不同，主要用于问题数量分布，不应用柱高直接比较发生率；
- 稳健性图检验参数扰动稳定性，不能替代治理前后真实复评。

## 5. 字体与文件

程序优先调用操作系统已有的中文字体，不包含或分发字体文件。Windows通常会使用微软雅黑或黑体；Linux建议安装Noto Sans CJK。PNG适合直接插入Word，SVG适合矢量编辑。
