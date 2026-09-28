#!/usr/bin/env python3
"""長期予報（段階D）のショート用 short.json の骨組みを source.md から作る。

使い方:
  python3 scripts/seasonal_short.py material/<dir>/source.md --out material/<dir_short>/short.json \
      --periods "9/26〜10/2,10/3〜10/9,10/10〜10/23" [--map images/japan.png]
  → 数値の場面（気温の地方塗り分け、期間×地方のマス目、天気の傾向の塗り分け）と照合表を埋めた short.json。
    見出し・ナレーション・天気の傾向の文言は TODO のまま出るので、発表文を読んで書く。
  地図は先に  python3 scripts/render_map.py --bbox 24.0,122.9,45.6,146.2 --size 1080x900 --inner 60,40,900,860 \
      --no-borders --regions --out material/<dir_short>/images/japan.png

場面の型（4場面＋共通CTA、45〜60秒）:
  1 regions  気温の結論（地方ごとに「高い 60%」を塗り分け）。確率の意味はここのナレーションで一度だけ
  2 grid     期間ごとの気温（1か月予報は週、3か月予報は月）
  3 regions  天気の傾向（発表文の「晴れの日が多い」「数日の周期で変わる」を地方ごとに）
  4 close    共通CTA。cta.next に次回の発表日時
色は気象庁の平年偏差図に合わせる: 気温 高い=橙 F97C00 / 低い=青 387DFF、降水量 多い=青緑 2FB4B4 / 少ない=茶 B06131、
日照 多い=黄 FFC83C / 少ない=灰 787878、平年並=灰 8B95A3。alpha は確率: 70%→.85 60%→.7 50%→.55 40%→.4
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_seasonal import parse  # noqa: E402

MID = "#8B95A3"
COLORS = {"気温": ("#387DFF", MID, "#F97C00"), "降水量": ("#B06131", MID, "#2FB4B4"), "日照時間": ("#787878", MID, "#FFC83C")}
ALPHA = {70: .85, 60: .7, 50: .55, 40: .4}
REGIONS = ["北日本", "東日本", "西日本", "沖縄・奄美"]


def alpha(pct):
    return ALPHA.get(pct, .85 if pct > 70 else .35)


def starred(vals, heads):
    """特徴ありの階級 [(name, pct, idx)]。無ければ最大の階級を1つ。"""
    st = [(heads[i], p, i) for i, (p, s) in enumerate(vals) if s]
    if st:
        return st
    i = max(range(3), key=lambda k: vals[k][0])
    return [(heads[i], vals[i][0], i)]


def cell(name, pct, idx, elem):
    return {"text": name, "sub": f"{pct}%", "color": COLORS[elem][idx], "alpha": alpha(pct)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--periods", default="", help="期間名に添える日付。カンマ区切り")
    ap.add_argument("--map", default="images/japan.png")
    a = ap.parse_args()
    md = Path(a.source).read_text(encoding="utf-8")
    secs, heads = parse(md)
    title = re.search(r"^## (.+)", md, re.M).group(1).strip()
    issued = re.search(r"発表: (\S+)", md).group(1)
    headline = (re.search(r"見出し: (.+)", md) or re.search(r"$^", md)).group(1).strip() if re.search(r"見出し: ", md) else ""
    m = re.search(r"([０-９\d]+月[０-９\d]+日)", md[md.find("次回"):]) if "次回" in md else None
    nxt = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")) if m else "TODO"
    periods = [p.strip() for p in a.periods.split(",")] if a.periods else []
    main_sec = next(iter(secs))
    check = [["項目", "動画の値", "原文（source.md）", "確認"], ["発表", issued, issued, "✓"]]

    # 1 気温の結論
    regs = []
    for reg, vals in secs[main_sec]["気温"]:
        st = starred(vals, heads["気温"])
        val = "または".join(n for n, _, _ in st) + f" {st[0][1]}%"
        regs.append({"name": reg, "value": val, "color": COLORS["気温"][st[-1][2]], "alpha": alpha(st[0][1])})
        check.append([f"{main_sec} 気温 {reg}", val, " / ".join(f"{heads['気温'][i]} {p}%{'★' if s else ''}" for i, (p, s) in enumerate(vals)), "✓"])
    s1 = {"type": "regions", "tone": "jma", "band": "気象庁の予報", "dur": 15, "kicker": f"{issued[5:7].lstrip('0')}月{issued[8:10].lstrip('0')}日発表",
          "heading": "TODO 気温の結論を一言で", "map": a.map, "regions": regs,
          "takeaway": "TODO", "narration": "TODO 確率の意味（平年なら3区分が各33%。60%は平年の約2倍起こりやすい。必ずそうなる意味ではない）をここで一度だけ"}

    # 2 期間ごとの気温
    wsecs = [k for k in secs if k != main_sec and "気温" in secs[k]]
    zen = str.maketrans("０１２３４５６７８９～", "0123456789〜")
    cols = [{"label": k.translate(zen), "sub": periods[i] if i < len(periods) else ""} for i, k in enumerate(wsecs)]
    rows = []
    for reg in REGIONS:
        cells = []
        for k in wsecs:
            vals = dict(secs[k]["気温"]).get(reg)
            if not vals:
                cells.append({"text": "", "sub": "", "color": MID, "alpha": .2})
                continue
            st = starred(vals, heads["気温"])
            cells.append([cell(n, p, i, "気温") for n, p, i in st] if len(st) > 1 else cell(*st[0], "気温"))
            check.append([f"{k} 気温 {reg}", "／".join(f"{n} {p}%" for n, p, _ in st),
                          " / ".join(f"{heads['気温'][i]} {p}%{'★' if s else ''}" for i, (p, s) in enumerate(vals)), "✓"])
        rows.append({"label": reg, "cells": cells})
    s2 = {"type": "grid", "tone": "jma", "band": "気象庁の予報", "dur": 14, "heading": "TODO 推移を一言で", "sub": "期間ごとの気温（気象庁が特徴ありとした階級）",
          "cols": cols, "rows": rows,
          "legend": [{"label": "低い", "color": COLORS["気温"][0]}, {"label": "平年並", "color": MID}, {"label": "高い", "color": COLORS["気温"][2]}],
          "legend_note": "濃いほど確率が高い", "narration": "TODO"}

    # 3 天気の傾向（文言は発表文から手で入れる）
    s3 = {"type": "regions", "tone": "jma", "band": "気象庁の予報", "dur": 13, "heading": "TODO 天気の傾向を一言で", "map": a.map,
          # 文言が長いので札は海の上に出す（北・東は日本海側に左出し、西は九州の南に右出し）
          "regions": [{"name": "北日本", "value": "TODO 例: 数日の周期", "color": MID, "alpha": .4, "at": [40.0, 138.6], "side": "left"},
                      {"name": "東日本", "value": "TODO 例: 数日の周期", "color": MID, "alpha": .4, "at": [37.0, 136.5], "side": "left", "sub": "TODO 任意の補足"},
                      {"name": "西日本", "value": "TODO 例: 晴れの日が多い", "color": COLORS["日照時間"][2], "alpha": .55, "at": [31.3, 131.0], "side": "right"},
                      {"name": "沖縄・奄美", "value": "TODO 例: 晴れの日が多い", "color": COLORS["日照時間"][2], "alpha": .55}],
          "takeaway": f"TODO 見出し: {headline}" if headline else "TODO", "narration": "TODO"}
    for elem in ("降水量", "日照時間"):
        for reg, vals in secs[main_sec].get(elem, []):
            st = [(heads[elem][i], p) for i, (p, s) in enumerate(vals) if s]
            if st:
                check.append([f"{main_sec} {elem} {reg}", "または".join(n for n, _ in st) + f" {st[0][1]}%",
                              " / ".join(f"{heads[elem][i]} {p}%{'★' if s else ''}" for i, (p, s) in enumerate(vals)), "✓"])
    check.append(["次回発表", nxt, md[md.find("次回"):].split("\n")[0].strip() if "次回" in md else "", "✓"])

    data = {"title": f"TODO【{title}】", "date": issued[:10], "date_label": issued[:10].replace("-", "."), "brand": "気象予報士なべ",
            "source": {"label": f"気象庁 {title}（{issued[:10].replace('-', '年', 1).replace('-', '月')}日発表）", "url": "https://www.jma.go.jp/bosai/season/"},
            "footer": "気象庁の予報の解説です。独自の予想は含みません",
            "scenes": [s1, s2, s3], "check": check,
            "cta": {"next": nxt, "lines_before": ["予報は期間が近づくほど確かに。週間予報とあわせて"], "narration_before": "▶期間が近づくほど予報は確かになります。週間予報とあわせて見てください。"}}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out, "TODO の箇所:", json.dumps(data, ensure_ascii=False).count("TODO"))


if __name__ == "__main__":
    main()
