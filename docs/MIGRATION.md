# 从原始 EDQSG.py 与0.1.0项目迁移

## 主要变化

1. `Indicator(score, confidence, evidence)` 被拆分为 `Indicator + Evidence + IndicatorAssessment`；
2. 证据新增五级支持分布、未知度、采集时间、作用范围和判断依据；
3. `EvidenceType` 新增 `EXPERT`；
4. 原简单加权证据融合替换为可靠性折扣与递归ER组合；
5. `CouplingRelation` 可由 `CouplingCalibrationInput` 三源校准得到；
6. 底线执行返回 `BottomLineOutcome`，明确上限、惩罚和触发规则；
7. 治理模板改为列表，支持根因模板与底线模板；
8. 报告新增总体等级、证据冲突、待复核指标和元数据；
9. 复评必须再次执行 `evaluate` 后使用 `model.compare`；
10. 稳健性分析通过 `model.robustness` 执行。

## 最小迁移示例

旧输入：

```python
Indicator(score=80, confidence=0.9, evidence=["data"])
```

新输入：

```python
Indicator(
    indicator_id="DQ1",
    name="完整性",
    domain=Domain.DATA_QUALITY,
    evidences=(
        Evidence(
            evidence_id="E1",
            evidence_type=EvidenceType.DATA,
            source="全量扫描",
            coverage=1,
            authority=0.9,
            timeliness=1,
            repeatability=1,
            business_fit=1,
            observed_score=80,
        ),
    ),
)
```
