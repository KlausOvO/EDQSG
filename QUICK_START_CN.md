# EDQSG-U1.2 + AeroMRO 快速执行指南（Windows / SQL Server）

## 1. 推荐环境

- Windows 10/11 64位
- Python 3.10—3.12 64位
- SQL Server 2019或以上
- SQL Server Management Studio（SSMS）
- Microsoft ODBC Driver 18 for SQL Server

建议把整个目录放在不含中文和空格的短路径，例如：

```text
C:\EDQSG_U1_2
```

## 2. 建立Python环境并运行测试

在项目根目录打开PowerShell：

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all,dev]"
python -m pytest
```

正常结果应为32项测试全部通过。

## 3. 创建干净的AeroMRO验证数据库

在SSMS中按顺序执行：

```text
benchmark\aeromro\schema\00_create_database.sql
benchmark\aeromro\schema\01_clean_schema.sql
benchmark\aeromro\data\02_seed_clean_small.sql
```

脚本会创建数据库：

```text
AeroMRO_EDQSG
```

每次做单缺陷实验，建议从干净数据库备份恢复，或重新运行上述三个脚本。不要把多个单缺陷场景连续叠加到同一数据库副本。

## 4. 可选：重新生成small/medium/large数据脚本

```powershell
python benchmark\aeromro\tools\generate_dataset.py --scale small --seed 20260725 --output benchmark\aeromro\data\02_seed_clean_small_regenerated.sql
```

把`small`改成`medium`或`large`即可生成更大规模SQL脚本。

## 5. 配置SQL Server连接

先复制配置：

```powershell
Copy-Item config\sqlserver\aeromro_benchmark.yaml config\sqlserver\aeromro_local.yaml
```

编辑`config\sqlserver\aeromro_local.yaml`中的服务器、数据库、用户名等信息。数据库名应为：

```text
AeroMRO_EDQSG
```

SQL Server用户名密码认证时，在PowerShell设置密码环境变量。变量名以YAML中`password_env`配置为准；常用示例：

```powershell
$env:EDQSG_DB_PASSWORD = "你的密码"
```

Windows集成认证则使用项目中的Windows认证示例配置，并保证当前Windows用户具有目标数据库读取权限。

推荐只读权限：

```sql
GRANT CONNECT TO edqsg_reader;
GRANT VIEW DEFINITION TO edqsg_reader;
GRANT SELECT TO edqsg_reader;
```

## 6. 测试连接并运行基线评价

```powershell
edqsg-sqlserver config\sqlserver\aeromro_local.yaml --test-connection
edqsg-sqlserver config\sqlserver\aeromro_local.yaml --output output\baseline
```

也可以不用安装后的命令入口，直接运行：

```powershell
python -m edqsg.sqlserver.cli config\sqlserver\aeromro_local.yaml --output output\baseline
```

主要输出包括：

```text
output\baseline\edqsg_sqlserver_report.json
output\baseline\edqsg_sqlserver_report.md
output\baseline\edqsg_sqlserver_report.html
```

以及指标图、根因图、治理任务图和稳健性分析结果（取决于配置）。

## 7. 执行一个缺陷场景

例如验证“受控无物理外键”：

1. 从干净数据库副本开始；
2. 在SSMS执行：

```text
benchmark\aeromro\scenarios\SG3_controlled_no_physical_fk.sql
```

3. 使用对应配置运行：

```powershell
edqsg-sqlserver config\sqlserver\aeromro_controlled_no_fk.yaml --output output\controlled_no_fk
```

验证“非受控无物理外键”时执行：

```text
benchmark\aeromro\scenarios\SG3_uncontrolled_no_physical_fk.sql
```

然后运行：

```powershell
edqsg-sqlserver config\sqlserver\aeromro_uncontrolled_no_fk.yaml --output output\uncontrolled_no_fk
```

如需观察结构缺陷传播，再执行相应`benchmark\aeromro\workload\*.sql`，之后重新评价。

## 8. 推荐的正式实验顺序

1. 干净基线；
2. 单个数据缺陷；
3. 单个结构缺陷；
4. 受控无物理外键；
5. 非受控无物理外键；
6. 执行传播负载后的复评；
7. 与`benchmark\aeromro\ground_truth\`中的真值文件对比。

## 9. 常见问题

### `pyodbc`安装失败

先安装Microsoft ODBC Driver 18，并确认Python与ODBC驱动都是64位。

### 登录时报证书错误

测试环境可在连接配置中按项目示例设置`TrustServerCertificate`；生产环境应正确部署和校验证书，不建议长期绕过。

### PowerShell禁止激活虚拟环境

仅对当前窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 全量评价速度慢

先使用`metadata`或`sample`扫描模式；正式实验再在测试库、只读副本或低峰期使用`full`。
