"""SQL Server自动评价命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import SQLServerAssessmentPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="连接SQL Server并自动执行EDQSG数据质量—结构治理评价。"
    )
    parser.add_argument("config", help="JSON或YAML配置文件路径")
    parser.add_argument("--output", help="报告输出目录；默认使用配置中的output_dir")
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="仅测试连接，不执行元数据和数据扫描",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = SQLServerAssessmentPipeline.from_file(args.config)
    try:
        if args.test_connection:
            if not hasattr(pipeline.executor, "test_connection"):
                raise RuntimeError("当前执行器不支持连接测试。")
            info = pipeline.executor.test_connection()
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        result = pipeline.run_and_export(args.output)
        print(
            json.dumps(
                {
                    "database": result.metadata.database_name,
                    "Q": round(result.assessment.dq.score, 4),
                    "S": round(result.assessment.sg.score, 4),
                    "final_score": round(result.assessment.final_score, 4),
                    "grade": result.assessment.overall_grade.value,
                    "confidence": round(result.assessment.overall_confidence, 4),
                    "bottom_line_count": len(result.assessment.bottom_line_triggers),
                    "governance_task_count": len(result.assessment.governance_tasks),
                    "profiling_issue_count": len(result.profile.issues),
                    "visualization_enabled": pipeline.config.visualization.enabled,
                    "robustness_generated": result.robustness is not None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI应输出可读错误并返回非零退出码
        print(f"EDQSG SQL Server评价失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        pipeline.close()


if __name__ == "__main__":
    raise SystemExit(main())
