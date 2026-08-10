# AeroMRO-EDQSG 双域验证数据库（U1.2）

该基准面向航空器材采购、接收、检验、库存、装机、寿命控制、送修与报废业务，用于验证EDQSG-U1.2的数据质量域、结构治理域、证据可靠性、Q-S根因诊断和治理复评。

## U1.2新增重点

数据库关系质量不再仅以“是否存在物理外键”判断。基准新增三组对照：

1. 可信物理外键基线；
2. 无物理外键，但具有应用实时校验、小时级审计、审批与性能证据的受控例外；
3. 无物理外键，且仅有文档约定、没有有效替代控制的非受控缺口。

这三组实验分别验证：强预防控制、等效替代控制，以及关系控制不足向DQ6孤儿记录传播。

## 目录

- `schema/00_create_database.sql`：创建数据库和`aero`、`dq`模式。
- `schema/01_clean_schema.sql`：创建干净结构、约束、质量实验表和关系控制注册表。
- `data/02_seed_clean_small.sql`：固定随机种子的小型干净数据和关系控制真值。
- `tools/generate_dataset.py`：生成small/medium/large三档SQL数据。
- `config/sqlserver/aeromro_benchmark.yaml`：可信物理外键基线。
- `config/sqlserver/aeromro_controlled_no_fk.yaml`：受控无外键对照。
- `config/sqlserver/aeromro_uncontrolled_no_fk.yaml`：非受控无外键对照。
- `scenarios/`：数据域和结构域缺陷注入脚本。
- `workload/`：结构缺陷传播或阴性对照负载。
- `ground_truth/defect_catalog.csv`：缺陷与预期行为。
- `ground_truth/relationship_control_experiments.csv`：关系控制实验条件和预期结果。

## 推荐执行顺序

1. 执行`schema/00_create_database.sql`。
2. 执行`schema/01_clean_schema.sql`。
3. 执行`data/02_seed_clean_small.sql`。
4. 设置只读账号与`EDQSG_DB_PASSWORD`。
5. 运行基线配置并保存报告。
6. 在独立数据库副本执行单个场景，随后使用与场景匹配的配置重新评价。

### 关系控制三组实验

| 实验 | 场景脚本 | 配置 | 预期 |
|---|---|---|---|
| 物理外键基线 | 无 | `aeromro_benchmark.yaml` | SG3高，DQ6孤儿率0 |
| 受控无外键 | `SG3_controlled_no_physical_fk.sql` | `aeromro_controlled_no_fk.yaml` | 不因无FK自动降级，不触发关系底线 |
| 非受控无外键 | `SG3_uncontrolled_no_physical_fk.sql` | `aeromro_uncontrolled_no_fk.yaml` | SG3下降并触发关系底线 |
| 缺陷传播 | 上一场景后执行`W_SG3_orphan_part_propagation.sql` | 非受控配置 | DQ6下降，SG3→DQ6根因路径增强 |

`W_SG3_controlled_relation_valid_workload.sql`是阴性对照：在受控无外键场景中只写入有效器材引用，孤儿率应保持为0。

## 污染率实验

数据缺陷脚本默认包含`@RatePct`和`@Seed`。建议污染率为1%、3%、5%、10%、20%，每档至少五个随机种子。单缺陷场景应使用独立数据库副本，混合缺陷另设实验。

## 规模

| 档位 | 器材主数据 | 器材实例 | 采购单 | 用途 |
|---|---:|---:|---:|---|
| small | 80 | 300 | 30 | 开发、单元实验与演示 |
| medium | 800 | 8,000 | 500 | 主实验 |
| large | 5,000 | 100,000 | 5,000 | 可扩展性与性能实验 |

## 边界说明

该数据为合成验证数据，不代表真实航空运营人的生产数据。配置中的过程和专家证据是synthetic baseline，正式研究应替换为真实日志、制度文件、性能测试和专家材料。
