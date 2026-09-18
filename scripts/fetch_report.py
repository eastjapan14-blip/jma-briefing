#!/usr/bin/env python3
"""気象庁XML（1件以上）を取得し、台本作成用の素材Markdownに変換する。

使い方:
  python3 scripts/fetch_report.py <XMLのURL>... [--out material/YYYYMMDD_slug]

出力: <out>/source.md（本文テキスト）と <out>/raw/*.xml（原本）。
台風解析・予報情報は、実況と予報の要点を表に整形する。
"""
import argparse, re, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def text_report(root):
    """平文系（気象情報、防災速報、警報など）を見出し＋本文に整形。"""
    out = []
    head = None
    for el in root.iter():
        t = local(el.tag)
        if t == "Title" and head is None and el.text:
            pass
        if t == "Head":
            head = el
    control_title = root.find("./{http://xml.kishou.go.jp/jmaxml1/}Control/{http://xml.kishou.go.jp/jmaxml1/}Title")
    hb = "{http://xml.kishou.go.jp/jmaxml1/informationBasis1/}"
    title = root.findtext(f"./{hb}Head/{hb}Title", "")
    rdt = root.findtext(f"./{hb}Head/{hb}ReportDateTime", "")
    office = root.findtext("./{http://xml.kishou.go.jp/jmaxml1/}Control/{http://xml.kishou.go.jp/jmaxml1/}EditorialOffice", "")
    headline = root.findtext(f"./{hb}Head/{hb}Headline/{hb}Text", "") or ""
    out.append(f"## {title}")
    out.append(f"- 種別: {control_title.text if control_title is not None else ''}")
    out.append(f"- 発表: {rdt}（{office}）")
    if headline.strip():
        out.append(f"- 見出し: {headline.strip()}")
    out.append("")
    # Body内のTextをすべて拾う（type属性つきは見出しにする）
    body = None
    for el in root:
        if local(el.tag) == "Body":
            body = el
    if body is not None:
        for el in body.iter():
            if local(el.tag) == "Text" and el.text and el.text.strip():
                typ = el.get("type")
                if typ:
                    out.append(f"### {typ}")
                out.append(el.text.strip())
                out.append("")
        # 警報・注意報の地域別（Item/Kind/Name + Area/Name）
        rows = []
        for item in body.iter():
            if local(item.tag) != "Item":
                continue
            kinds = [k.findtext("{*}Name", "") for k in item.findall("{*}Kind")]
            kinds = [k for k in kinds if k]
            areas = [a.findtext("{*}Name", "") for a in item.iter() if local(a.tag) == "Area"]
            if kinds and areas:
                rows.append((", ".join(areas), " / ".join(kinds)))
        if rows and not any("###" in o for o in out[-3:]):
            out.append("### 地域別")
            out.append("| 地域 | 内容 |\n|---|---|")
            for a, k in rows[:60]:
                out.append(f"| {a} | {k} |")
            out.append("")
    return "\n".join(out)


def typhoon_report(root):
    """台風解析・予報情報を実況＋予報の表にする。"""
    out = []
    hb = "{http://xml.kishou.go.jp/jmaxml1/informationBasis1/}"
    rdt = root.findtext(f"./{hb}Head/{hb}ReportDateTime", "")
    out.append("## 台風解析・予報情報")
    out.append(f"- 発表: {rdt}（気象庁）")
    out.append("")
    out.append("| 時刻 | 区分 | 位置 | 階級 | 中心気圧 | 最大風速 | 最大瞬間 | 進行 | 予報円半径 |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for mi in root.iter():
        if local(mi.tag) != "MeteorologicalInfo":
            continue
        dt = mi.find("{*}DateTime")
        when = dt.text if dt is not None else ""
        kind = dt.get("type", "") if dt is not None else ""
        d = {"loc": "", "cls": "", "size": "", "inten": "", "p": "", "ws": "", "gust": "", "dir": "", "spd": "", "r70": ""}
        for el in mi.iter():
            t = local(el.tag)
            typ = el.get("type", "")
            if t == "Location":
                d["loc"] = el.text or ""
            elif t == "TyphoonClass":
                d["cls"] = el.text or ""
            elif t == "AreaClass":
                d["size"] = el.text or ""
            elif t == "IntensityClass":
                d["inten"] = el.text or ""
            elif t == "Pressure":
                d["p"] = el.text or ""
            elif t == "WindSpeed" and typ == "最大風速" and el.get("unit") == "m/s":
                d["ws"] = el.text or ""
            elif t == "WindSpeed" and typ == "最大瞬間風速" and el.get("unit") == "m/s":
                d["gust"] = el.text or ""
            elif t == "Direction" and typ == "移動方向":
                d["dir"] = el.text or ""
            elif t == "Speed" and typ == "移動速度" and el.get("unit") == "km/h":
                d["spd"] = el.text or ""
            elif t == "Radius" and typ == "７０パーセント確率半径" and el.get("unit") == "km":
                d["r70"] = el.text or ""
            elif t == "BasePoint" and typ == "中心位置（度）" and not d["loc"]:
                d["loc"] = el.get("description", "")
        cls = " ".join(x for x in (d["size"], d["inten"], d["cls"]) if x)
        mv = f'{d["dir"]} {d["spd"]}km/h'.strip() if d["dir"] or d["spd"] else ""
        out.append(f'| {when} | {kind} | {d["loc"]} | {cls} | {d["p"]}hPa | {d["ws"]}m/s | {d["gust"]}m/s | {mv} | {d["r70"]}km |')
    out.append("")
    for el in root.iter():
        if local(el.tag) == "Text" and el.text and el.text.strip():
            out.append(el.text.strip())
    return "\n".join(out)


def season_report(root):
    """季節予報（1か月・3か月・暖候期・寒候期）を、見通しの文章と確率表にする。★は気象庁が「特徴あり」とした階級。"""
    hb = "{http://xml.kishou.go.jp/jmaxml1/informationBasis1/}"
    title = root.findtext(f"./{hb}Head/{hb}Title", "")
    rdt = root.findtext(f"./{hb}Head/{hb}ReportDateTime", "")
    headline = (root.findtext(f"./{hb}Head/{hb}Headline/{hb}Text", "") or "").strip()
    out = [f"## {title}", f"- 発表: {rdt}（気象庁）"]
    if headline:
        out.append(f"- 見出し: {headline}")
    out.append("")

    def cells_of(cpv):
        cells = []
        for tag in ("ProbabilityOfBelowNormal", "ProbabilityOfNormal", "ProbabilityOfAboveNormal"):
            el = cpv.find("{*}" + tag)
            if el is None:
                cells.append("")
                continue
            v = (el.text or "").strip()
            cells.append(f"{v}%★" if el.get("significant") == "true" else f"{v}%")
        return cells

    def emit(period, gen, sig, tables):
        if not (gen or sig or tables):
            return
        out.append(f"### {period}")
        if gen:
            out.append(gen.strip())
            out.append("")
        for kind, text in sig:
            if text:
                out.append(f"- {kind}: {text.strip()}")
        if sig:
            out.append("")
        for kind, rows in tables.items():
            lo, hi = ("低い", "高い") if kind == "気温" else ("少ない", "多い")
            out.append(f"#### {kind} の確率（★＝気象庁が特徴ありとした階級）")
            out.append(f"| 地域 | {lo} | 平年並 | {hi} |\n|---|---|---|---|")
            for r in rows:
                out.append("| " + " | ".join(r) + " |")
            out.append("")

    def area_of(item):
        return item.findtext(".//{*}Area/{*}Name", "")

    for mi in root.iter():
        t = local(mi.tag)
        if t == "MeteorologicalInfo":
            period = mi.findtext("{*}Name", "") or mi.findtext("{*}DateTime", "")
            gen = mi.findtext(".//{*}GeneralSituationText", "")
            sig = [(e.get("kind", ""), e.findtext("{*}Text", "") or "") for e in mi.iter() if local(e.tag) == "SignificantClimateElement"]
            tables = {}
            for item in mi.iter():
                if local(item.tag) != "Item":
                    continue
                for cpv in item.iter():
                    if local(cpv.tag) == "ClimateProbabilityValues":
                        tables.setdefault(cpv.get("kind", ""), []).append([area_of(item)] + cells_of(cpv))
            emit(period, gen, sig, tables)
        elif t == "TimeSeriesInfo":
            names = {td.get("timeId"): td.findtext("{*}Name", "") for td in mi.iter() if local(td.tag) == "TimeDefine"}
            per = {k: {"gen": "", "sig": [], "tables": {}} for k in names}
            for el in mi.iter():
                lt = local(el.tag)
                if lt == "GeneralSituationText" and el.get("refID") in per:
                    per[el.get("refID")]["gen"] = el.text or ""
                elif lt == "SignificantClimateElement":
                    for tx in el.findall("{*}Text"):
                        if tx.get("refID") in per:
                            per[tx.get("refID")]["sig"].append((el.get("kind", ""), tx.text or ""))
            for item in mi.iter():
                if local(item.tag) != "Item":
                    continue
                area = area_of(item)
                for cpv in item.iter():
                    if local(cpv.tag) == "ClimateProbabilityValues" and cpv.get("refID") in per:
                        per[cpv.get("refID")]["tables"].setdefault(cpv.get("kind", ""), []).append([area] + cells_of(cpv))
            for k in sorted(per, key=lambda x: int(x)):
                emit(names[k], per[k]["gen"], per[k]["sig"], per[k]["tables"])
    nexts = [el.findtext("{*}Text", "") for el in root.iter() if local(el.tag) == "NextForecastSchedule"]
    if nexts:
        out.append("### 次回発表")
        out += [f"- {n}" for n in nexts if n]
        out.append("")
    return "\n".join(out)


def convert(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ct = root.findtext("./{http://xml.kishou.go.jp/jmaxml1/}Control/{http://xml.kishou.go.jp/jmaxml1/}Title", "")
    hb = "{http://xml.kishou.go.jp/jmaxml1/informationBasis1/}"
    if root.findtext(f"./{hb}Head/{hb}InfoKind", "") == "季節予報":
        return season_report(root), ct
    if ct.startswith("台風解析・予報情報"):
        return typhoon_report(root), ct
    return text_report(root), ct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--out", help="出力フォルダ（既定: material/日付_slug）")
    ap.add_argument("--slug", default="jma")
    args = ap.parse_args()

    out = Path(args.out) if args.out else ROOT / "material" / f'{datetime.now():%Y%m%d_%H%M}_{args.slug}'
    (out / "raw").mkdir(parents=True, exist_ok=True)
    parts = ["# 素材（気象庁発表の原文）", "", "出典: 気象庁防災情報XML（下記URL）。数値・地名・時刻は台本作成後に必ず原文と照合すること。", ""]
    for i, url in enumerate(args.urls, 1):
        data = fetch(url)
        name = url.rsplit("/", 1)[-1]
        (out / "raw" / name).write_bytes(data)
        md, ct = convert(data)
        parts.append(f"<!-- {url} -->")
        parts.append(md)
        parts.append("")
        print(f"[{i}] {ct} -> raw/{name}", file=sys.stderr)
    (out / "source.md").write_text("\n".join(parts), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
