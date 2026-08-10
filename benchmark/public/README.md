# EDQSG 公开基准验证（HoloClean dirty+clean）

## 数据集与来源

采用 HoloClean 公开基准中的三组 dirty/clean 对齐数据，用于验证 EDQSG 检测层与评价层：

| 文件 | 来源 | 行数 | 说明 |
|---|---|---:|---|
| hospital.csv | HoloClean/holoclean testdata | 1 000 | 医院绩效数据（含字符级损坏） |
| hospital_clean.csv | HoloClean/holoclean testdata | 19 000 | (tid, attribute, correct_val) 单元级真值 |
| flight.csv | HoloClean/holoclean testdata | 57 246 | 航班多源时刻数据（多来源冲突+缺失） |
| flight_clean.csv | HoloClean/holoclean testdata | 13 884 | 按“航班+字段”给出权威真值 |
| adult_dirty0.1.csv | danielvandijke/HoloClean testdata | 1 100 | UCI Adult 的 10% 单元级损坏版 |
| adult_clean.csv | danielvandijke/HoloClean testdata | 12 122 | 与 dirty 对齐的单元级真值 |

原计划中的 yelp 数据集无公开镜像（HoloClean 基准所用 yelp 未随仓库发布），
以 adult 的 dirty/clean 对齐版替代，其结构（dirty 表 + 单元级真值文件）与 hospital/flight 一致。

## 内容校验

六个文件均与 GitHub blob SHA-1 一致，SHA-256（下载后校验用）：

| 文件 | SHA-256 |
|---|---|
| adult_clean.csv | F6A12FF0E2828A1E7F0D5B509EE172D31C67B69B32B19471EA4B17E24262C247 |
| adult_dirty0.1.csv | 0A16754214B7A427E974A7F25F8C293855CE5B901167B495716B433D2DE9CFE6 |
| flight.csv | F563725092C1B964B8429419AB2F84F1D355AF2E09B4AAB2D985888176020456 |
| flight_clean.csv | CEF9AC09799913E39FFE513691E85D018634B9EA1E53C30882D9DF22AF95BE87 |
| hospital.csv | BBB2F60E9E7BBDA68B1115B3BBB9A0D70587A9D33384A2373E4D447789FD619A |
| hospital_clean.csv | 5DC89F7701ABAE92AF81308AE9CBEEA584C39CBA288FDFFE3324397E15F8CA2C |

## 复现

```powershell
# 1) 下载数据（jsDelivr 主源，raw.githubusercontent 备用源）
python benchmark/public/download_holoclean.py

# 2) 运行双表验证（结果输出到 benchmark/public/results/）
#    需将 src 加入 sys.path（嵌入式 Python 忽略 PYTHONPATH）
python -c "import sys; sys.path.insert(0, 'src'); import runpy; runpy.run_path('benchmark/public/benchmark.py', run_name='__main__')"
```

## 实验口径

- 真值采用 `(tid, attribute, correct_val)` 单元级文件；flight 同一航班有多个来源行，
  评估按行实例计，任一来源值与权威真值不一致即记为缺陷。
- 检测规则对应 DQ 指标：缺失（DQ1）、域/格式（DQ3）、多源冲突（DQ2，组内众数投票）。
- 初始未知度 β_U^0 = 1 − C_sample·C_rule：C_rule 在 70% 标定子集上按规则集并集召回率
  分档估计（<0.35→0.3、0.35~0.70→0.6、>0.70→0.9），flight 按航班分组切分标定子集；
  标定种子 20260720，测试集不参与标定；C_sample 与可靠性属性中的 C_e（证据完整性）
  概念分离，公开基准证据 C_sample = 1（全量扫描）、C_e = 0.95。
- 评价指标：逐单元精确率/召回率/F1；污染率控制实验（0%~60% 七档，ρ 与自助 95%CI）；
  分块一致性（每数据集 10 块）；单因素 ±10% 与蒙特卡洛 ±10%（300 次）双口径
  （仅模型参数 vs 模型参数+底线限级值）的等级反转率与前 K 根因重叠度。
- 结构治理域在公开数据上采用 schema 级观测（键完整性 SG3、权威源存在性 SG7），
  根因与治理闭环验证见 `examples/paper_case/run_paper_case.py`。
- 受控根因注入实验（10 场景，Top-1/Top-3/MRR）见
  `examples/paper_case/root_cause_injection.py`。
  Top-1/Top-3/MRR 分母为 9 个含已知根因的注入场景，S0 干净基线单独报告误诊率。

## 已知限制

- 检测层只承诺检出“可规则化缺陷”；字符级替换型损坏（hospital/adult）规则不可观测，
  通过 C_rule 进入未知度，由证据覆盖率与复核清单显式披露，不进入得分；
  adult 因全部质量指标证据不足，按模型规则不出具总体等级。
- 公开数据不提供重复（DQ4）、跨表一致性（DQ5）、孤儿（DQ6）、时效（DQ7）、追溯（DQ8）
  的单元级真值，此类指标与完整 SG 链路由装备场景构造算例演示。
