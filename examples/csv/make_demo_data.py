"""生成离线演示 CSV（含 DQ1-DQ8 各类缺陷，可复现）。"""

from __future__ import annotations

import csv
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

FRESH = "2026-07-01"
STALE = "2025-10-01"


def write_csv(name: str, headers: list[str], rows: list[list[str]]) -> None:
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    print("生成", path, len(rows), "行")


# 器材主数据：12 行，注入 重复件号(3/4)、非法国家码(7)、缺名称(9)、过期(11)
master_headers = ["part_id", "part_code", "part_name", "serial_no", "country_code", "updated_at", "operator"]
master_rows = []
for i in range(1, 13):
    part_id = f"P-{i:03d}"
    serial = "SN-003" if i == 4 else f"SN-{i:03d}"
    name = "" if i == 9 else f"器材{i}"
    country = "XX" if i == 7 else "CN"
    updated = STALE if i == 11 else FRESH
    master_rows.append([part_id, f"CODE-{i:03d}", name, serial, country, updated, f"U{i % 3 + 1}"])
write_csv("part_master.csv", master_headers, master_rows)


# 器材实例：14 行，注入 孤儿(13)、缺证书(5)、缺操作人(9)、序列号与主数据冲突(6)、过期(12)
instance_headers = ["instance_id", "part_id", "serial_no", "certificate_no", "operator", "updated_at"]
instance_rows = []
for i in range(1, 15):
    part_id = "P-999" if i == 13 else f"P-{i:03d}"
    serial = "SN-WRONG" if i == 6 else (f"SN-{i:03d}" if i <= 12 else "SN-099")
    cert = "" if i == 5 else f"CERT-{i:04d}"
    operator = "" if i == 9 else f"O{i % 3 + 1}"
    updated = STALE if i == 12 else FRESH
    instance_rows.append([f"INST-{i:03d}", part_id, serial, cert, operator, updated])
write_csv("part_instance.csv", instance_headers, instance_rows)


# 库存事务：16 行，注入 孤儿(15)、序列号与主数据冲突(7)、缺操作人(8)、过期(16)
txn_headers = ["txn_id", "part_id", "serial_no", "quantity", "updated_at", "operator"]
txn_rows = []
for i in range(1, 17):
    part_id = "P-888" if i == 15 else f"P-{i % 12 + 1:03d}"
    serial = "SN-MISMATCH" if i == 7 else f"SN-{i % 12 + 1:03d}"
    operator = "" if i == 8 else f"T{i % 3 + 1}"
    updated = STALE if i == 16 else FRESH
    txn_rows.append([f"TXN-{i:03d}", part_id, serial, str(i * 10), updated, operator])
write_csv("inventory_transaction.csv", txn_headers, txn_rows)

print("演示数据生成完毕。")
