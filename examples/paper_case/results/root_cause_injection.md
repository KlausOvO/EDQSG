# 受控根因注入实验（EDQSG）

| 场景 | 注入结构问题 | 预期根因 | Top-1 | Top-3 | 预期根因排名 | MRR |
|---|---|---|---:|---:|---:|---:|
| S0_clean | clean |  | - | - | - | 0.0 |
| S1_orphan | orphan | SG3 | SG3 | SG3 | 1 | 1.0 |
| S2_master_conflict | master_conflict | SG7 | SG7 | SG7 | 1 | 1.0 |
| S3_duplicate | duplicate | SG3 | SG3 | SG3 | 1 | 1.0 |
| S4_missing | missing | SG3 | SG3 | SG3 | 1 | 1.0 |
| S5_stale | stale | SG8 | SG8 | SG8 | 1 | 1.0 |
| S6_audit_missing | audit_missing | SG8 | SG8 | SG8 | 1 | 1.0 |
| S7_authority_conflict | authority_conflict | SG7 | SG7 | SG7 | 1 | 1.0 |
| S8_domain_violation | domain_violation | SG3 | SG3 | SG3 | 1 | 1.0 |
| S9_combined | combined | SG3,SG7 | SG7 | SG7 | 1 | 1.0 |

- 注入场景（S1~S9，n=9）：Top-1 命中率 100.00%、Top-3 命中率 100.00%、MRR 1.00
- 干净基线 S0：未输出根因候选，误诊率 0.00%
