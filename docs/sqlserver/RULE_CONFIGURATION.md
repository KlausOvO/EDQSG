# SQL Server业务规则配置说明

## required_columns

用于必填和条件必填检测。`condition_sql`为空时对全部记录适用；不为空时，条件成立的记录才要求字段有值。

```yaml
required_columns:
  - table: "dbo.RepairOrder"
    column: "finish_time"
    condition_sql: "status_code = 'FINISHED'"
    description: "完工工单必须记录完工时间"
```

## business_keys

用于业务对象唯一性检测，支持联合业务键。

```yaml
business_keys:
  - table: "dbo.Equipment"
    columns: ["equipment_code"]
    bottom_line_threshold: 0.001
```

## domain_rules

用于标准代码集和值域检测。

```yaml
domain_rules:
  - table: "dbo.Equipment"
    column: "status_code"
    allowed_values: ["ACTIVE", "REPAIR", "SCRAPPED"]
```

## freshness_rules

用于时效性评价，字段必须是 SQL Server 日期时间类型。

```yaml
freshness_rules:
  - table: "dbo.Equipment"
    column: "updated_at"
    max_age_days: 365
```

## custom_sql_rules

条件成立表示违规。条件片段只能由可信维护人员配置；程序会拒绝明显的多语句、注释和DML/DDL关键字，但它不是完整SQL沙箱。

```yaml
custom_sql_rules:
  - rule_id: "R-DATE-ORDER"
    indicator_id: "DQ5"
    table: "dbo.RepairOrder"
    invalid_condition_sql: "finish_time < receive_time"
    applicable_condition_sql: "finish_time IS NOT NULL AND receive_time IS NOT NULL"
    description: "完工时间不得早于接修时间"
```

## master_data_groups

用于评价主数据权威来源。系统不会自动猜测哪张表是权威主数据表。

```yaml
master_data_groups:
  - entity_name: "器材"
    authoritative_table: "dbo.Equipment"
    related_tables: ["dbo.StockDetail", "dbo.RepairOrder"]
```
