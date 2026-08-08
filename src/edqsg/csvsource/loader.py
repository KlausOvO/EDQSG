"""CSV 数据加载与 JSON 配置读取（仅标准库）。"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path


def load_table(path: str | os.PathLike) -> list[dict[str, str]]:
    """读取一张 CSV 表，返回行字典列表（值均为字符串，空单元格为空串）。"""

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV 表不存在：{p}")
    with p.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV 表缺少表头：{p}")
        return [dict(row) for row in reader]


def load_config(path: str | os.PathLike) -> dict:
    """读取 JSON 配置（离线环境不依赖 PyYAML）。"""

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在：{p}")
    with p.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_paths(config: dict, base_dir: str | os.PathLike) -> dict[str, Path]:
    """把配置中的相对 CSV 路径解析为绝对路径。"""

    base = Path(base_dir)
    tables = config.get("tables", {})
    return {
        name: (base / rel).resolve()
        for name, rel in tables.items()
    }
