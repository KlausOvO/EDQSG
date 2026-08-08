# EDQSG 评价内核与 SQL Server 自动分析项目

本项目是“证据驱动的数据质量—结构治理评价模型”（Evidence-Driven Data Quality and Structural Governance Evaluation Model，EDQSG）的 Python 参考实现，当前软件版本为 **0.6.0**，对应模型修订版 **EDQSG-U1.2**。

0.6.0 在原有SQL Server自动分析、论文图和静态驾驶舱基础上，完成EDQSG-U1.2的规则增强与AeroMRO航空器材双域验证基准，可完成：

- SQL Server 用户名密码认证或 Windows 集成认证；
- 自动读取数据库、模式、表、字段、主键、唯一约束、外键、索引、检查约束和扩展说明；
- 在数据库端执行空值、空字符串、唯一性、业务键重复、孤儿记录、值域、时效性和自定义业务规则检测；
- 以预期业务关系为检测入口：物理外键、应用校验、存储过程、ETL门禁、消息校验和定期审计均可作为关系控制证据；
- 无物理外键不自动等同于缺陷，SG3/SG4结合替代控制、受控例外、责任信息和实际孤儿率判断；
- 根据记录粒度、多值字段禁用、主数据权威一致性、生命周期与互操作规则增强SG2、SG7和SG8；
- 将数据、结构、规则、过程和专家五类证据接入SQL Server评价流水线；
- 自动构建 DQ1—DQ8 数据质量域证据；
- 自动构建 SG1—SG8 结构治理域证据；
- 生成字段冗余与表冗余候选及风险等级；
- 触发真实底线规则，并执行非补偿性限级；
- 自动调用 EDQSG 内核完成证据推理、双域评价、Q-S 耦合诊断和治理任务排序；
- 输出 JSON、Markdown 和 HTML 报告；
- 自动生成指标得分、得分—可信度、证据构成、Q-S耦合、根因贡献、治理任务、冗余风险、字段缺失、违规帕累托等统计图；
- 可选执行蒙特卡洛稳健性分析并输出得分分布和根因排名稳定性图；
- 可执行±10%/±20%等单因素确定性敏感性分析；
- 附带AeroMRO-EDQSG干净库、缺陷场景、传播负载和真值目录；
- 输出PNG、SVG或PDF图形及静态HTML可视化驾驶舱。

> 数据库适配层全程按只读方式设计。生产环境必须为分析账户授予最小只读权限，不应授予 INSERT、UPDATE、DELETE、ALTER 或 CONTROL 权限。

## 一、项目结构

```text
edqsg_project/
├── src/edqsg/
│   ├── models.py                 # 领域对象、证据、耦合关系、报告和任务
│   ├── evidence.py               # 可靠性折扣、ER/DS证据组合和冲突处理
│   ├── scoring.py                # 双域评分、综合评价、平衡度和等级
│   ├── coupling.py               # 三源耦合校准与根因贡献度
│   ├── bottom_line.py            # 非补偿性底线约束
│   ├── redundancy.py             # 字段/表冗余风险模型
│   ├── governance.py             # 治理任务生成与排序
│   ├── reassessment.py           # 治理前后复评
│   ├── robustness.py             # 蒙特卡洛稳健性分析
│   ├── core.py                   # EDQSG总模型入口
│   ├── csvsource/                # CSV 离线评测入口（loader/profiler/runner）
│   ├── sqlserver/
│       ├── config.py             # SQL Server连接、扫描及业务规则配置
│       ├── adapter.py            # SQLAlchemy + pyodbc只读连接适配器
│       ├── metadata.py           # sys.*系统目录元数据采集
│       ├── profiler.py           # 数据剖析与业务规则执行
│       ├── analyzer.py           # SQL结果向EDQSG指标和证据映射
│       ├── reporting.py          # JSON/Markdown/HTML/图形报告导出
│       ├── pipeline.py           # 一体化自动评价、稳健性和可视化流水线
│       └── cli.py                # edqsg-sqlserver命令行入口
│   └── visualization/
│       ├── paper.py              # [CORE] 论文统计图批量生成
│       └── dashboard.py          # 静态HTML驾驶舱
├── benchmark/
│   ├── public/                   # HoloClean 公开基准（下载、双表验证、结果）
│   └── aeromro/                  # 航空器材 SQL Server 验证基准
├── config/
│   ├── example.json              # 模型参数配置示例
│   └── sqlserver/                # SQL Server 认证与规则配置
│       ├── example.yaml          # SQL Server认证配置示例
│       └── example_windows_auth.yaml # Windows集成认证示例
├── examples/
│   ├── csv/                      # CSV 离线演示与论文结果导出
│   ├── paper_case/               # 论文算例、消融与受控根因注入实验
│   └── sqlserver/                # SQL Server 自动分析示例
│       └── run_sqlserver_assessment.py
├── CORE_CODE_INDEX.md            # 核心代码文件与调用链索引
├── tests/                        # EDQSG内核、SQL Server与可视化测试
└── docs/                         # 模型、SQL Server、可视化和实现说明
```

## 公开基准与论文验证

模型通用机制使用 HoloClean 公开基准（hospital / flight / adult）与受控实验验证，
装备语义由构造算例实例化，具体见论文第 7、8 节：

- 公开基准下载（约 7.5 MB，含 SHA-256 校验清单）：`benchmark/public/download_holoclean.py`
- 双表验证（检测 P/R/F1、规则可观测度 C_rule 标定、污染率控制实验、
  双口径蒙特卡洛敏感性）：`benchmark/public/benchmark.py` → `benchmark/public/results/`
- 装备场景算例与消融（Q=82.3、S=71.7 等）：`examples/paper_case/run_paper_case.py`
- 受控根因注入实验（Top-1/Top-3/MRR）：`examples/paper_case/root_cause_injection.py`

运行方式（嵌入式 Python 需将 `src` 加入 `sys.path`）：

```bash
python benchmark/public/download_holoclean.py
python -c "import sys; sys.path.insert(0, 'src'); import runpy; \
runpy.run_path('benchmark/public/benchmark.py', run_name='__main__')"
python -c "import sys; sys.path.insert(0, 'src'); import runpy; \
runpy.run_path('examples/paper_case/root_cause_injection.py', run_name='__main__')"
```

## U1.2 航空器材验证基准快速入口

- 模型与代码修订说明：`docs/EDQSG_U1_2_IMPLEMENTATION_REPORT.md`；
- 完整规则配置：`config/sqlserver/aeromro_benchmark.yaml`；
- 建库、数据、缺陷脚本与真值：`benchmark/aeromro/`；
- U1.2规则说明：`docs/sqlserver/U1_2_RELATIONSHIP_CONTROL.md`。
- 受控无外键配置：`config/sqlserver/aeromro_controlled_no_fk.yaml`。
- 非受控无外键配置：`config/sqlserver/aeromro_uncontrolled_no_fk.yaml`。

最小基准库执行顺序：

```text
benchmark/aeromro/schema/00_create_database.sql
benchmark/aeromro/schema/01_clean_schema.sql
benchmark/aeromro/data/02_seed_clean_small.sql
```

随后在独立数据库副本中执行单个 `scenarios/*.sql`；结构传播实验还应继续执行对应的 `workload/*.sql`。不要在同一副本连续叠加多个单缺陷场景。

## 二、环境要求

- Python 3.10 及以上；
- Microsoft ODBC Driver 18 for SQL Server；
- SQLAlchemy 2.x；
- pyodbc 5.x；
- Matplotlib 3.8及以上（统计图与论文图）。

### 安装全部依赖

```bash
python -m pip install -e ".[all,dev]"
```

安装 SQL Server、YAML和可视化运行依赖：

```bash
python -m pip install -e ".[sqlserver,yaml,visualization]"
```

### 检查本机 ODBC 驱动

```python
import pyodbc
print(pyodbc.drivers())
```

应当能够看到类似：

```text
ODBC Driver 18 for SQL Server
```

## 三、数据库账户权限

建议由数据库管理员创建专用只读账户，并在目标数据库执行类似授权：

```sql
GRANT CONNECT TO edqsg_reader;
GRANT VIEW DEFINITION TO edqsg_reader;
GRANT SELECT TO edqsg_reader;
```

不要向评价账户授予数据库结构修改或数据写入权限。

## 四、配置与运行

复制并修改：

```text
config/sqlserver/example.yaml
```

SQL Server认证时，将密码放入环境变量：

### Windows PowerShell

```powershell
$env:EDQSG_DB_PASSWORD = "your-password"
```

### Linux/macOS

```bash
export EDQSG_DB_PASSWORD='your-password'
```

测试连接：

```bash
edqsg-sqlserver config/sqlserver/example.yaml --test-connection
```

执行自动评价：

```bash
edqsg-sqlserver config/sqlserver/example.yaml --output output/sqlserver
```

也可使用 Python：

```python
from edqsg.sqlserver import SQLServerAssessmentPipeline

pipeline = SQLServerAssessmentPipeline.from_file(
    "config/sqlserver/example.yaml"
)
try:
    result = pipeline.run_and_export("output/sqlserver")
    print(result.assessment.final_score)
    print(result.assessment.overall_grade.value)
finally:
    pipeline.close()
```

## 五、扫描模式

### `metadata`

只读取数据库结构，不扫描业务数据。速度最快，但 DQ 域中缺少直接证据的指标会保留较高未知度。

### `sample`

对每个字段使用 `TOP (sample_rows)` 执行样本剖析，适合首次摸底。该方式不是随机抽样，可能受物理存储和记录顺序影响，因此不能替代关键指标的全量验证。

### `full`

对目标表执行全量聚合检测，适合正式评价和治理验收，但可能对大型生产库产生负载。建议：

- 限定 schema 和表；
- 避开业务高峰；
- 先在只读副本或备库验证；
- 与 DBA 确认执行计划、超时和资源限制。

## 六、自动化边界

### 可以自动完成

- 表、字段、主外键、索引和约束读取；
- 空值、空字符串、字段唯一率和孤儿记录检测；
- 配置化业务键、值域、时效性和自定义规则检测；
- 字段/表冗余候选初筛；
- EDQSG证据融合、评分、底线、根因和治理任务生成。

### 需要业务规则配置

- 关键字段和条件必填字段；
- 业务唯一键；
- 标准代码集；
- 时间、数量和状态逻辑；
- 关键表和底线阈值；
- 主数据权威来源。

### 通常需要人工复核

- 两个字段是否真正同义；
- 相似表是否属于不合理冗余；
- 反规范化是否具有性能和业务必要性；
- Q-S耦合强度的专家值；
- 治理任务责任边界和实施成本。

## 七、统计图与论文图

在配置文件中启用：

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

执行评价后，输出目录新增：

```text
figures/
├── fig01_indicator_scores.png
├── fig02_score_confidence.png
├── fig03_evidence_composition.png
├── fig04_qs_coupling_heatmap.png
├── fig05_root_cause_ranking.png
├── fig06_governance_priority.png
├── fig07_redundancy_risk.png
├── fig08_table_scale.png
├── fig09_field_missing_rate.png
├── fig10_violation_pareto.png
├── fig11_robustness_distribution.png   # 开启稳健性时生成
├── fig12_root_cause_stability.png      # 开启稳健性时生成
└── figure_manifest.json

edqsg_dashboard.html
```

其中PNG用于论文插图，SVG适合后续矢量编辑。未获得适用数据的图会自动跳过，不会生成无意义空图。

## 八、测试

```bash
python -m pytest
```

当前版本包含 39 项自动化测试（EDQSG 内核、SQL Server 假执行器流水线、复核与聚合边界、
根因参与条件等）。由于交付环境没有实际目标 SQL Server，本项目没有在用户生产数据库上执行
连接测试；首次使用前应在测试库或只读副本完成验证。

## 九、重要研究说明

- 自动生成的 Q-S 关系默认只有“规范机制”来源，可信度为保守值；正式论文应加入专家咨询和历史治理数据进行三源校准；
- 未配置业务规则的指标可能使用弱代理证据或中性基础分，因此必须关注报告中的 `review_indicator_ids`、未知度和采集异常；
- 字段和表冗余结果是候选清单，不应未经业务确认直接删除对象；
- 治理后必须重新连接数据库采集新证据，不能人为提高分值；
- SQL自定义规则应由可信人员维护，且运行账户必须保持只读。
