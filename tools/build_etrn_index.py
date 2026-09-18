#!/usr/bin/env python3
"""観測所番号 → 過去の気象データ検索（etrn）の prec_no / block_no 索引を一度だけ作る。

都道府県選択ページ（約60ページ）の viewPoint('a','0002','沓形','クツガタ','45','10.7','141','08.3',...) を読み、
amedastable.json の緯度経度（度・分）で観測所番号に結び付ける。直列・間隔つき。日常の監視では実行しない。

使い方: python3 tools/build_etrn_index.py [--out record_hunter/data/etrn_index.json] [--sleep 1.5]
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELECT = "https://www.data.jma.go.jp/stats/etrn/select"
TABLE = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
UA = "jma-briefing record-hunter index builder (one-off)"
VP = re.compile(r"viewPoint\('([as])','(\d+)','([^']*)','([^']*)','(\d+)','([\d.]+)','(\d+)','([\d.]+)'")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def key(lat_d, lat_m, lon_d, lon_m):
    return f"{int(lat_d)}:{round(float(lat_m), 1):.1f}:{int(lon_d)}:{round(float(lon_m), 1):.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "record_hunter" / "data" / "etrn_index.json"))
    ap.add_argument("--sleep", type=float, default=1.5)
    a = ap.parse_args()
    table = json.loads(get(TABLE).decode("utf-8"))
    by_pos = {}
    for sid, row in table.items():
        by_pos.setdefault(key(row["lat"][0], row["lat"][1], row["lon"][0], row["lon"][1]), []).append(sid)
    html = get(f"{SELECT}/prefecture00.php").decode("utf-8", errors="replace")
    precs = sorted(set(re.findall(r"prec_no=(\d+)", html)))
    index, unmatched = {}, []
    for prec in precs:
        time.sleep(a.sleep)
        page = get(f"{SELECT}/prefecture.php?prec_no={prec}&block_no=&year=&month=&day=&view=").decode("utf-8", errors="replace")
        seen = set()
        for kind, block, name, kana, lat_d, lat_m, lon_d, lon_m in VP.findall(page):
            if block in seen:
                continue
            seen.add(block)
            ids = by_pos.get(key(lat_d, lat_m, lon_d, lon_m), [])
            if len(ids) == 1:
                index[ids[0]] = {"kind": kind, "prec": prec, "block": block, "name": name}
            else:
                unmatched.append((prec, block, name, ids))
        print(f"prec {prec}: {len(seen)} 地点 → 累計 {len(index)}", file=sys.stderr)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(index, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"書き出し {a.out}: {len(index)} 地点（未対応 {len(unmatched)} 件）", file=sys.stderr)
    for u in unmatched[:30]:
        print("  unmatched:", u, file=sys.stderr)


if __name__ == "__main__":
    main()
