# EDQSG-U1.2 预期关系与完整性控制配置

## 1. 修订目的

U1.2不再把“存在可信物理外键”作为关系质量的唯一实现形式。评价对象调整为三层：

1. **预期关系是否被明确登记**：子表、父表、字段映射、基数、空值策略、删除/更新策略和责任主体；
2. **关系完整性是否存在有效控制**：物理外键、应用写入校验、受控存储过程、ETL门禁、消息消费校验、定期审计或人工对账；
3. **控制运行结果是否有效**：孤儿率、控制覆盖度、可靠性、运行有效性和问题发现时延。

因此，“没有物理外键”只是一项结构事实，不自动等同于结构缺陷。

## 2. relationship_controls

```yaml
relationship_controls:
  - relationship_id: REL-TX-PART
    child_table: aero.inventory_transaction
    child_columns: [part_id]
    parent_table: aero.part_master
    parent_columns: [part_id]
    description: 库存事务必须引用权威器材主数据
    cardinality: many_to_one
    child_nullable: false
    delete_policy: restrict_in_application
    update_policy: immutable_identifier
    owner: 航材库存系统组
    criticality: critical

    physical_fk_required: false
    enforcement_modes:
      - application_validation
      - scheduled_audit
    control_coverage: 0.99
    control_reliability: 0.98
    operating_effectiveness: 0.99
    audit_frequency_hours: 1

    exception_approved: true
    exception_reason: 高并发写入经压力测试后不启用物理外键
    performance_evidence_id: PERF-TX-PART-2026-001
    review_due_date: 2027-01-31

    maximum_orphan_rate: 0.0
    minimum_control_score: 0.75
    bottom_line_cap: 50
```

## 3. 支持的替代控制

| enforcement_mode | 典型含义 | 默认机制强度 |
|---|---|---:|
| `application_validation` | 应用服务写入前验证父记录 | 0.82 |
| `stored_procedure` | 所有写入通过受控存储过程 | 0.88 |
| `etl_gate` | 批量加载前关联校验并阻断 | 0.82 |
| `message_validation` | 消息生产或消费阶段校验 | 0.78 |
| `scheduled_audit` | 周期性孤儿记录扫描 | 依据频率约0.35-0.72 |
| `manual_reconciliation` | 人工定期对账 | 0.35 |
| `documentation_only` | 仅有设计约定，无技术控制 | 0.15 |

多种机制采用互补组合，而不是简单相加。可信且启用的物理外键作为强预防控制，机制强度为1.0。

## 4. 评分逻辑

关系控制有效度：

```text
E_j = M_j × C_j × R_j × V_j
```

- `M_j`：控制机制综合强度；
- `C_j`：控制覆盖度；
- `R_j`：控制可靠性；
- `V_j`：运行有效性。

SG3使用关系重要度加权后的控制有效度；SG4评价关系语义、责任、策略和受控例外证据；DQ6始终依据预期关系执行孤儿检测，不依赖物理外键存在。

未配置`relationship_controls`时，程序仍兼容`logical_foreign_keys`，但物理外键比例仅作为低业务适配度的弱代理，不再因为数据库没有外键而直接记零分。

## 5. 底线规则

关键关系只有在下列条件之一成立时才触发底线：

- 控制有效度低于`minimum_control_score`；
- 实际孤儿率高于`maximum_orphan_rate`。

因此，受控无外键关系在替代控制充分、审批证据完整且孤儿率为零时，不触发底线；没有有效替代控制的关键关系即使暂时尚未产生孤儿数据，也可作为结构性风险触发底线。

## 6. AeroMRO三组对照

| 实验 | 物理外键 | 替代控制 | 预期结果 |
|---|---|---|---|
| 基线 | 有 | 审计作为补充 | SG3高，DQ6孤儿率0 |
| 受控无外键 | 无 | 应用实时校验+小时审计+审批/性能证据 | 不因无FK自动降级，不触发底线 |
| 非受控无外键 | 无 | 仅文档约定 | SG3明显下降并触发底线；负载后DQ6下降 |

对应文件：

- `config/sqlserver/aeromro_benchmark.yaml`
- `config/sqlserver/aeromro_controlled_no_fk.yaml`
- `config/sqlserver/aeromro_uncontrolled_no_fk.yaml`
- `benchmark/aeromro/ground_truth/relationship_control_experiments.csv`
