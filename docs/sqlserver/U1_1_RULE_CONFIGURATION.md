# EDQSG-U1.1 SQL Server 规则扩展

U1.1 新增五类配置，以减少“删除约束同时删除检测入口”和结构指标弱代理问题。

## logical_foreign_keys

逻辑关联规则独立于物理外键。即使数据库删除了外键，剖析器仍执行 LEFT JOIN 孤儿检测，并可配置底线阈值。

## table_model_rules

为关键业务表显式声明记录粒度列、最大字段数、是否允许堆表、是否要求表说明，以及禁止出现的多值字段。SG2 优先使用这些规则；未配置时才回退到宽表、堆表和说明覆盖率代理。

`forbidden_multivalue_columns`用于声明不应在单字段中保存逗号、分号等分隔集合的字段，例如器材适用机型必须进入关联表，而不能放在`part_master.applicable_type_codes`中。

## master_data_consistency_rules

配置权威表、引用表、键映射和复制属性映射。系统同时输出：

- 主数据孤儿率；
- 复制属性冲突率；
- DQ5、DQ6 和 SG7 证据；
- 可选底线触发。

## lifecycle_control_rules

对关键表声明审计字段、互操作字段、时态表要求和说明要求。SG8 不再只依赖通用审计字段代理。

## supplemental_evidence

允许把 process、expert 等证据直接加入 SQL Server 自动流水线。可提供数值得分或五等级置信分布，并完整记录覆盖度、权威性、时效性、可重复性和业务适配性。

完整示例见 `config/sqlserver/aeromro_benchmark.yaml`。

## deterministic sensitivity

`EDQSGModel.sensitivity(...)`提供单因素确定性敏感性分析。它在保持其他参数不变时，逐一扰动指标权重、双域权重或耦合关系，记录综合分数、等级、前五根因和前五治理任务是否反转。正式实验建议至少使用`(0.8, 0.9, 1.1, 1.2)`，与±10%和±20%设计对应。

## 验证注意事项

- 逻辑外键、主数据一致性和自定义SQL规则均会产生数据库查询负载，应先在测试库或只读副本评估执行计划；
- `supplemental_evidence`中的合成过程/专家证据只用于基准验证，不得在正式论文中冒充真实访谈、日志或工单证据；
- 单缺陷场景必须在独立干净副本执行，避免缺陷叠加影响真值；
- 结构传播场景先评价结构域，再执行`workload`，最后复评数据质量域和根因排序。
