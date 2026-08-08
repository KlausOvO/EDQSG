# SQL Server自动评价使用说明

## 1. 推荐上线顺序

1. 在测试库安装 ODBC Driver、Python 和项目依赖；
2. 创建只读评价账户；
3. 首次采用 `metadata` 模式，核对表和字段范围；
4. 改为 `sample` 模式，验证规则和报告；
5. 为关键表配置必填、业务键、值域、时效性和自定义规则；
6. 在低峰期对关键表采用 `full` 模式；
7. 组织业务、DBA和治理人员复核低可信度指标与冗余候选；
8. 形成治理任务，整改后重新执行评价。

## 2. 认证方式

### SQL Server认证

配置 `authentication: sql`，提供用户名，并通过 `password_env` 指定环境变量。

### Windows集成认证

配置 `authentication: windows`。运行Python进程的Windows身份必须已获得目标数据库权限。

## 3. 表范围

- `schemas`：限定模式；
- `include_tables`：为空时扫描模式中的全部用户表；
- `exclude_tables`：排除临时、系统或无关表；
- 表名可以使用 `table` 或 `schema.table`。

## 4. 报告

流水线输出：

- `edqsg_sqlserver_report.json`：完整机器可读报告；
- `edqsg_sqlserver_report.md`：适合研究和治理讨论；
- `edqsg_sqlserver_report.html`：便于浏览器查看。

报告同时保存原始元数据摘要、剖析结果、采集异常、指标未知度、根因贡献度、底线风险和治理任务。
