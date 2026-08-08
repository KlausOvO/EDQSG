"""CSV 数据源：离线环境下以 CSV 表单替代 SQL Server 的自动剖析与评价。"""

from .loader import load_config, load_table
from .profiler import build_indicators, build_sg_indicators, compute_metrics
from .runner import run_assessment

__all__ = [
    "load_config",
    "load_table",
    "compute_metrics",
    "build_indicators",
    "build_sg_indicators",
    "run_assessment",
]
