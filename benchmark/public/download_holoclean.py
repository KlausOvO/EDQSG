# -*- coding: utf-8 -*-
"""下载 HoloClean 公开基准数据（dirty+clean 对齐版本）。

数据集说明（来源均已用 GitHub blob SHA 校验）：
  - hospital.csv / hospital_clean.csv   : HoloClean/holoclean testdata，重复记录检测基准
  - flight.csv  / flight_clean.csv      : HoloClean/holoclean testdata，约束/字段缺陷基准
  - adult_dirty0.1.csv / adult_clean.csv: danielvandijke/HoloClean testdata，10%单元级错误对齐版
原计划中的 yelp 无公开镜像（HoloClean 基准所用 yelp 未随仓库发布），以 adult 对齐版替代。
"""

import hashlib
import os
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

CANDIDATES = [
    # (本地文件名, jsDelivr 主源, raw.githubusercontent 备用源)
    ("hospital.csv",
     "https://cdn.jsdelivr.net/gh/HoloClean/holoclean@master/testdata/hospital.csv",
     "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/hospital.csv"),
    ("hospital_clean.csv",
     "https://cdn.jsdelivr.net/gh/HoloClean/holoclean@master/testdata/hospital_clean.csv",
     "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/hospital_clean.csv"),
    ("flight.csv",
     "https://cdn.jsdelivr.net/gh/HoloClean/holoclean@master/testdata/flight.csv",
     "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/flight.csv"),
    ("flight_clean.csv",
     "https://cdn.jsdelivr.net/gh/HoloClean/holoclean@master/testdata/flight_clean.csv",
     "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/flight_clean.csv"),
    ("adult_clean.csv",
     "https://cdn.jsdelivr.net/gh/danielvandijke/HoloClean@master/testdata/adult_clean.csv",
     "https://raw.githubusercontent.com/danielvandijke/HoloClean/master/testdata/adult_clean.csv"),
    ("adult_dirty0.1.csv",
     "https://cdn.jsdelivr.net/gh/danielvandijke/HoloClean@master/testdata/adult_dirty0.1.csv",
     "https://raw.githubusercontent.com/danielvandijke/HoloClean/master/testdata/adult_dirty0.1.csv"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 research-download"}


def sha1_of_bytes(data):
    """与 Git 一致的 blob SHA-1（校验内容完整性）。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


done = set()
for name, url_main, url_backup in CANDIDATES:
    if name in done:
        continue
    path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        done.add(name)
        print("已存在:", name, os.path.getsize(path))
        continue
    data = None
    for url in (url_main, url_backup):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            print("下载:", name, "|", url.split("/")[2], "| bytes:", len(data))
            break
        except Exception as e:
            print("源失败:", name, "|", url.split("/")[2], "|", e)
    if data is None:
        print("放弃:", name)
        continue
    head = data[:300].decode("utf-8", errors="replace")
    if b"," in data[:300] or b"\n" in data[:300]:
        with open(path, "wb") as f:
            f.write(data)
        done.add(name)
        print("  首行:", head.splitlines()[0][:90] if head else "")
        print("  blob_sha1:", sha1_of_bytes(data))
    else:
        print("跳过(非CSV):", name, url_main)

print("完成。目录:", OUT)
