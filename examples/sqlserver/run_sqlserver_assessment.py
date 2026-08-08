"""从配置文件连接SQL Server并输出EDQSG报告。"""

from pathlib import Path

from edqsg.sqlserver import SQLServerAssessmentPipeline


CONFIG = Path("config/sqlserver/example.yaml")

pipeline = SQLServerAssessmentPipeline.from_file(CONFIG)
try:
    result = pipeline.run_and_export("output/sqlserver")
    print(f"数据库：{result.metadata.database_name}")
    print(f"Q={result.assessment.dq.score:.2f}")
    print(f"S={result.assessment.sg.score:.2f}")
    print(f"最终得分={result.assessment.final_score:.2f}")
    print(f"等级={result.assessment.overall_grade.value}")
finally:
    pipeline.close()
