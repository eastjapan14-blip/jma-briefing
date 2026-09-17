#!/usr/bin/env python3
"""気象庁の図を取得する（天気図PNG、台風経路図、雨雲レーダー）。

使い方:
  python3 scripts/fetch_images.py --out material/<dir>/images weather_map typhoon radar
    weather_map [--chart now|ft24|ft48]   実況天気図/予想天気図のPNG（気象庁が配布する画像）
    typhoon     [--center 緯度,経度 --zoom N]   台風経路図（気象庁サイトをChromeで撮影して余白を切る）
    radar       [--center 緯度,経度 --zoom N]   雨雲の動き（同上）

出力: 画像ファイルと images.md（出典・取得時刻の一覧。スライドの出典表記に使う）。
Chrome が必要（/Applications/Google Chrome.app）。
"""
import argparse, json, subprocess, sys, urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
JMA = "https://www.jma.go.jp/bosai"


def weather_map(out, chart="now"):
    lst = json.load(urllib.request.urlopen(f"{JMA}/weather_map/data/list.json", timeout=30))
    name = lst["near"][chart][-1]
    path = out / f"weather_map_{chart}.png"
    urllib.request.urlretrieve(f"{JMA}/weather_map/data/png/{name}", path)
    # ファイル名の 20260917030000 (UTC) が対象時刻
    import re
    utc = re.findall(r"_(\d{14})_", name)[0]
    t = datetime.strptime(utc, "%Y%m%d%H%M%S") + timedelta(hours=9)
    label = {"now": "実況天気図", "ft24": "24時間予想天気図", "ft48": "48時間予想天気図"}[chart]
    return path, f"気象庁 {label}（{t.month}月{t.day}日{t.hour}時）"


def shot(url, path, size=(1400, 1000), budget=20000):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={size[0]},{size[1]}", f"--virtual-time-budget={budget}",
                    f"--screenshot={path}", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    if not path.exists():
        sys.exit(f"スクリーンショット失敗: {url}")


def typhoon(out, center="24.5,143.0", zoom=6):
    lat, lon = center.split(",")
    path = out / "typhoon_map.png"
    shot(f"{JMA}/map.html#{zoom}/{lat}/{lon}/&elem=root&typhoon=all&contents=typhoon", path, size=(1800, 1000))
    im = Image.open(path)
    im.crop((240, 50, 1440, im.height)).save(path)   # 上部ヘッダと右の表を除き、地図だけにする（横長に）
    now = datetime.now()
    return path, f"気象庁 台風経路図（{now.month}月{now.day}日{now.hour}時{now.minute:02d}分に取得）"


def radar(out, center="33.0,137.0", zoom=5):
    lat, lon = center.split(",")
    path = out / "radar.png"
    shot(f"{JMA}/nowc/#zoom:{zoom}/lat:{lat}/lon:{lon}/colordepth:normal/elements:hrpns", path)
    im = Image.open(path)
    im.crop((0, 120, im.width, 910)).save(path)
    now = datetime.now()
    return path, f"気象庁 雨雲の動き（{now.month}月{now.day}日{now.hour}時{now.minute:02d}分に取得）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kinds", nargs="+", choices=["weather_map", "typhoon", "radar"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--chart", default="now")
    ap.add_argument("--center")
    ap.add_argument("--zoom", type=int)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    lines = []
    for k in a.kinds:
        if k == "weather_map":
            p, src = weather_map(out, a.chart)
        elif k == "typhoon":
            p, src = typhoon(out, a.center or "24.5,143.0", a.zoom or 6)
        else:
            p, src = radar(out, a.center or "33.0,137.0", a.zoom or 5)
        lines.append(f"- {p.name}: {src}")
        print(f"{p}  ({src})")
    md = out / "images.md"
    old = md.read_text() if md.exists() else "# 取得した図と出典\n\n"
    md.write_text(old + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
