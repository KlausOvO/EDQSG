# 详细模型与代码映射

| 模型内容 | 代码位置 |
|---|---|
| 证据可靠性 `r_ie` | `EvidenceFusionEngine.reliability` |
| 等级支持分布与未知度 | `Evidence.belief_degrees`、`unknown_degree` |
| 证据可靠性折扣 `r_e`（论文口径不含 importance） | `EvidenceFusionEngine.reliability` / `discount` |
| 冲突系数 K | `EvidenceFusionEngine._conflict` |
| 递归证据组合 | `EvidenceFusionEngine._combine_two` |
| 两类复核状态（证据不足/冲突） | `IndicatorAssessment.review_state` |
| 聚合门槛 θ_excl 与权重重归一 | `EDQSGModel.evaluate`（`aggregate`） |
| 证据覆盖率 ω_cov | `DomainAssessment.evidence_coverage`、`AssessmentReport.evidence_coverage` |
| 诊断充分性门槛 θ_RC | `CouplingAnalyzer.analyze`（`below_threshold`）、`EDQSGConfig.root_cause_threshold` |
| 指标得分与可信度 | `EvidenceFusionEngine.fuse` |
| CRITIC客观权重 | `weights.critic_weights` |
| 主客观组合权重 | `weights.combine_weights` |
| Q、S和G0、B、CG | `ScoreCalculator` |
| 非补偿性底线 | `BottomLineEngine` |
| 三源耦合校准 | `CouplingCalibrator` |
| 耦合平滑更新 | `CouplingCalibrator.smooth_update` |
| 根因贡献度 RC | `CouplingAnalyzer.analyze` |
| 字段/表冗余风险 | `RedundancyAnalyzer` |
| 治理任务优先级 | `GovernanceTaskPlanner.priority` |
| 治理前后复评 | `ReassessmentEngine.compare` |
| 蒙特卡洛反转率 | `MonteCarloAnalyzer.run` |
| 聚合门槛边界语义（未知度≤θ_excl 仍参与） | `EDQSGModel.evaluate`（`aggregate`） |
| 单元区间校验浮点容差 | `validators.validate_unit_interval` |
| 公开基准数据下载（HoloClean） | `benchmark/public/download_holoclean.py` |
| 公开基准双表验证（P/R/F1、块级相关、敏感性） | `benchmark/public/benchmark.py` |
| 装备场景算例与消融（Q=82.3/S=71.7 等） | `examples/paper_case/run_paper_case.py` |
| 规则可观测度 C_rule 与初始未知度 β_U^0 = 1 − C_sample·C_rule | `Evidence.rule_observability`、`EvidenceFusionEngine._raw_distribution` |
| 样本覆盖度 C_sample（与证据完整性 C_e 分离） | `Evidence.sample_coverage` |
| C_rule 标定（70% 子集召回率分档） | `benchmark/public/benchmark.py: calibrate_rule_observability` |
| 污染率控制实验 | `benchmark/public/benchmark.py: run_contamination` |
| 受控根因注入实验（Top-1/Top-3/MRR） | `examples/paper_case/root_cause_injection.py` |
| 结构侧复核不参与根因排名 | `CouplingAnalyzer.analyze`（SG 侧 review_state 检查） |
| 蒙特卡洛双口径（仅模型 vs 含底线限级） | `MonteCarloAnalyzer.run(perturb_bottom_line=...)` |
