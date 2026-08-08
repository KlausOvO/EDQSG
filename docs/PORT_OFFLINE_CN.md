# EDQSG 离线移植说明（SQL Server → CSV）

## 1. 目标环境

- 无网络；
- 仅有 Python（建议 3.10+）；
- 数据库以 CSV 表单形式提供；
- 不要求 SQL Server、SQLAlchemy、pyodbc、PyYAML、matplotlib。

## 2. 依赖决策（重要）

EDQSG **核心评价内核**（`evidence.py`、`scoring.py`、`bottom_line.py`、`coupling.py`、
`redundancy.py`、`governance.py`、`robustness.py`）只依赖 numpy。

- 若离线环境已有 numpy（例如便携版 Python 或已内置 numpy），**核心无需改动**；
- 若连 numpy 都没有，请先通过离线方式安装 numpy（`pip install numpy‑<版本>‑cp*.whl`），
  或联系作者提供纯标准库版核心。

## 3. 代码改动清单

### 新增（本次已提供）

| 文件 | 作用 |
|---|---|
| `src/edqsg/csvsource/loader.py` | 读取 CSV（`csv` 标准库）与 JSON 配置 |
| `src/edqsg/csvsource/profiler.py` | 按 DQ/SG 规则计算缺失、重复、孤儿、跨表一致、值域、时效等指标 |
| `src/edqsg/csvsource/runner.py` | 组装指标/耦合/底线/治理模板，调用 `EDQSGModel.evaluate`，导出 JSON/Markdown |
| `examples/csv/config_offline.json` | 离线评价配置示例 |
| `examples/csv/make_demo_data.py` | 生成含 DQ1–DQ8 缺陷的演示 CSV |
| `examples/csv/run_csv_offline.py` | 一键运行入口 |

### 不需要使用（离线环境跳过）

- `src/edqsg/sqlserver/`（adapter、metadata、profiler、analyzer、pipeline、cli）
- `config/sqlserver/*.yaml`（改用 JSON 配置）
- `src/edqsg/visualization/`（matplotlib 不可用时直接不导入）

## 4. 如何运行

```bash
# 1) 生成演示数据
python examples/csv/make_demo_data.py

# 2) 执行离线评价
python examples/csv/run_csv_offline.py
```

输出：

```text
examples/csv/output/assessment.json   # 完整评价结果
examples/csv/output/assessment.md    # 摘要报告
```

## 5. 接入你自己的 CSV 表

1. 把业务表导出为 CSV（保留表头），放入 `examples/csv/data/` 或任意目录；
2. 在 JSON 配置的 `tables` 中声明表名与相对路径；
3. 按实际字段修改 `dq_rules`：
   - `missing`：必填列缺失检测；
   - `domain`：值域校验（`allowed` 列表）；
   - `duplicate`：业务键重复（`columns` 为业务键）；
   - `orphan`：子表引用父表（`child_table/child_column/parent_table/parent_column`）；
   - `cross_table`：跨表同义值一致（需 `child_link/parent_link` 连接键）；
   - `stale`：按 `updated_at` 判断时效（`stale_max_age_days` 阈值）。
4. 按实际关系维护 `relationship_controls`（替代物理外键的控制证据）；
5. 底线规则写在 `bottom_line_rules`，条件基于 `metrics` 中的原始指标
   （如 `raw.dup_rate`、`raw.orphan_rate`、`raw.missing_rate.certificate`）；
6. 治理模板写在 `governance_templates`。

## 6. 与 SQL Server 版的差异

| 能力 | SQL Server 版 | CSV 离线版 |
|---|---|---|
| 数据读取 | SQLAlchemy + pyodbc 只读连接 | 标准库 `csv` 读取 |
| 元数据 | `sys.*` 系统目录 | JSON 配置声明 |
| 剖析 | SQL 聚合（full/sample/metadata） | Python 逐行统计 |
| 关系控制 | `RelationshipControlRule` | `relationship_controls` 配置 |
| 配置格式 | YAML | JSON |
| 可视化 | matplotlib 图表/驾驶舱 | 关闭（JSON/Markdown 报告） |
| 核心评价 | 相同 | 相同（numpy） |

## 7. 注意事项

- CSV 中的空单元格按"缺失"处理；数值型字段请保持字符串可解析；
- 跨表检测的连接键（`child_link/parent_link`）需在两边取值一致；
- 正式评价前请用干净数据做一轮基线，再叠加缺陷场景验证检测率；
- 时间字段建议统一为 `YYYY-MM-DD` 或 ISO 8601，便于 `stale` 检测。
