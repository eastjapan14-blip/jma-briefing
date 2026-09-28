#!/usr/bin/env python3
"""気象庁の「地上実況図」XML（VZSA50）から、等圧線・前線・高低気圧・台風の座標を JSON にする。

ショート動画の天気図場面（build_short.py の synoptic）が、この JSON を地形図の上に描く。
地上実況図は 3 時間ごと（毎時 00 分の実況を約 2 時間後に配信）。気象庁 XML の長期フィード（regular_l.xml）は数日分しか残らない。

使い方:
  python3 scripts/fetch_surface.py --time 2026-09-28T06:00 --out material/<dir>/raw
    → raw/surface_2026092806.xml（原本）と raw/surface_2026092806.json
  python3 scripts/fetch_surface.py --xml 保存済み.xml --out material/<dir>/raw   ← 保存済みの XML を変換するだけ

JSON: {"target": "2026-09-28T06:00:00+09:00", "source": URL,
       "isobars": [{"hpa": 1012, "line": [[lat, lon], ...]}],
       "fronts": [{"type": "停滞前線", "line": [[lat, lon], ...]}],     ← 線の座標は XML の順のまま
       "centers": [{"type": "低気圧", "lat": .., "lon": .., "hpa": 1002, "dir": 50, "speed": "４５ｋｍ／ｈ"},
                   {"type": "台風", "lat": .., "lon": .., "hpa": 945, "number": "2626", "name": "スリゲ"}]}
"""
import argparse, json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

FEED = "https://www.data.jma.go.jp/developer/xml/feed/regular_l.xml"
UA = "jma-briefing/1.0 (+https://github.com/)"
JST = timezone(timedelta(hours=9))
ATOM = {"a": "http://www.w3.org/2005/Atom"}
PT = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")
CENTER_TYPES = ("低気圧", "高気圧", "台風", "熱帯低気圧")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def line(text):
    return [[float(a), float(b)] for a, b in PT.findall(text or "")]


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = {"target": None, "isobars": [], "fronts": [], "centers": []}
    for el in root.iter():
        if local(el.tag) == "TargetDateTime":
            out["target"] = el.text
            break
    for item in (e for e in root.iter() if local(e.tag) == "Item"):
        kinds = []
        for prop in (e for e in item.iter() if local(e.tag) == "Property"):
            t = next((c.text for c in prop if local(c.tag) == "Type"), None)
            kinds.append((t, prop))
        if not kinds:
            continue
        t0, p0 = kinds[0]
        if t0 == "等圧線":
            hpa = line_el = None
            for e in p0.iter():
                if local(e.tag) == "Pressure":
                    hpa = int(float(e.text))
                elif local(e.tag) == "Line":
                    line_el = e.text
            out["isobars"].append({"hpa": hpa, "line": line(line_el)})
        elif t0 and t0.endswith("前線"):
            txt = next((e.text for e in p0.iter() if local(e.tag) == "Line"), "")
            out["fronts"].append({"type": t0, "line": line(txt)})
        elif t0 in CENTER_TYPES:
            c = {"type": t0}
            for e in p0.iter():
                n = local(e.tag)
                if n == "Coordinate":
                    (la, lo), = line(e.text)[:1]
                    c["lat"], c["lon"] = la, lo
                elif n == "Pressure" and e.text:
                    c["hpa"] = int(float(e.text))
                elif n == "Direction" and e.text:
                    c["dir"] = int(float(e.text))
                elif n == "Speed" and e.get("unit") == "km/h":
                    c["speed"] = e.get("description")
            for t, p in kinds[1:]:
                if t == "呼称":
                    for e in p.iter():
                        if local(e.tag) == "Number":
                            c["number"] = e.text
                        elif local(e.tag) == "NameKana":
                            c["name"] = e.text
            out["centers"].append(c)
    return out


def find_url(target):
    """長期フィードから、指定時刻（JST）を実況時刻とする地上実況図の URL を探す。配信は実況の約2時間後。"""
    feed = ET.fromstring(get(FEED))
    cands = []
    for e in feed.findall("a:entry", ATOM):
        if e.find("a:title", ATOM).text != "地上実況図":
            continue
        up = datetime.fromisoformat(e.find("a:updated", ATOM).text.replace("Z", "+00:00"))
        lag = (up - target).total_seconds() / 3600
        if 0 < lag < 5:
            cands.append((lag, e.find("a:link", ATOM).get("href")))
    for _, url in sorted(cands):
        body = get(url)
        m = re.search(rb"<TargetDateTime>(.*?)</TargetDateTime>", body)
        if m and datetime.fromisoformat(m.group(1).decode()) == target:
            return url, body
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time", help="実況時刻（JST）例 2026-09-28T06:00。3時間ごと")
    ap.add_argument("--xml", help="保存済みの地上実況図 XML")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.xml:
        url, body = None, Path(a.xml).read_bytes()
    else:
        target = datetime.fromisoformat(a.time).replace(tzinfo=JST)
        url, body = find_url(target)
        if not body:
            sys.exit(f"地上実況図が見つかりません: {a.time}（フィードは数日分のみ。3時間ごとの時刻を指定）")
    data = parse(body)
    data["source"] = url
    stem = "surface_" + datetime.fromisoformat(data["target"]).strftime("%Y%m%d%H")
    if not a.xml:
        (out / f"{stem}.xml").write_bytes(body)
    (out / f"{stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out / f"{stem}.json", f"等圧線 {len(data['isobars'])} 前線 {len(data['fronts'])} 中心 {len(data['centers'])}")


if __name__ == "__main__":
    main()
