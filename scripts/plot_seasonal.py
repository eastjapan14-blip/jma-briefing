#!/usr/bin/env python3
"""季節予報（1か月・3か月）の source.md から、地方ごとの確率を図にする（PIL のみ。matplotlib 不要）。

色は気象庁の平年偏差図（https://www.data.jma.go.jp/cpd/longfcst/tenkou/hensa_map.html）に合わせる:
  気温    高い=橙 F97C00 / 低い=青 387DFF
  降水量  多い=青緑 2FB4B4 / 少ない=茶 B06131
  日照    多い=黄 FFC83C / 少ない=灰 787878
  平年並はどれも薄い灰色

生成物（--out で指定したフォルダ）:
  summary.png        : 向こう1か月（3か月）の 気温・降水量・日照時間 を地方ごとの帯グラフで並べる
  weekly_grid.png    : 期間×地方の気温を、特徴ありの階級の色で塗ったマス目にする
  weekly_region.png  : 地方ごとのパネルに、期間ごとの気温の積み上げ棒を並べる
  <spec>.png         : --cards で渡した JSON（カード型の図。結論・天気の傾向・生活の観点など）
  images.md          : 出典の表記

使い方:
  python3 scripts/plot_seasonal.py material/<dir>/source.md --out material/<dir>/images \
      --periods "9/26〜10/2,10/3〜10/9,10/10〜10/23" --cards material/<dir>/figures.json

figures.json の書式:
  {"figures": [
    {"file": "conclusion.png", "bg": "FFFFFF", "title": "任意",
     "cards": [
       {"title": "北日本", "icon": "cycle",            ← icon: sun / rain / cloud / cycle / thermo / umbrella / calendar
        "rows": [{"label": "気温", "chip": "高い 60%", "color": "F97C00"},   ← 色付きの札
                 {"text": "天気は数日の周期で変わる"}]}                       ← ただの文
     ],
     "banner": {"icon": "rain", "text": "下に置く帯の文（任意）"}}
  ]}
"""
import argparse, json, math, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_B = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_R = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
MID = "D9D9D9"
COLORS = {  # (低い/少ない, 平年並, 高い/多い)
    "気温": ("387DFF", MID, "F97C00"),
    "降水量": ("B06131", MID, "2FB4B4"),
    "日照時間": ("787878", MID, "FFC83C"),
}
STAR = "B3261E"
FG, BG = "1A1A1A", "FFFFFF"
W = 2400


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def c(h):
    return "#" + h


def mix(h, t):
    """色 h を白と混ぜる（t=1 でそのまま、0 で白）"""
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#%02X%02X%02X" % tuple(int(255 - (255 - v) * t) for v in (r, g, b))


def text_dark(h):
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def parse(md):
    """{section: {element: [(region, [(pct, starred) x3])]}} と列見出しを返す"""
    out, heads, sec, elem = {}, {}, None, None
    for line in md.splitlines():
        if m := re.match(r"### (.+)", line):
            sec = m.group(1).strip(); out.setdefault(sec, {})
        elif m := re.match(r"#### (\S+) の確率", line):
            elem = m.group(1); out[sec][elem] = []
        elif line.startswith("|") and sec and elem:
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", x) for x in cells):
                continue
            if cells[0] == "地域":
                heads[elem] = cells[1:]
                continue
            vals = []
            for x in cells[1:]:
                m = re.match(r"(\d+)%(★?)", x)
                vals.append((int(m.group(1)), bool(m.group(2))) if m else (0, False))
            out[sec][elem].append((cells[0], vals))
    return out, heads


def ctext(d, cx, cy, s, f, fill=c(FG)):
    tw = d.textlength(s, font=f)
    d.text((cx - tw / 2, cy - f.size * 0.6), s, fill=fill, font=f)


# ---------- アイコン（box: (x, y, size)） ----------
def icon(d, kind, x, y, s):
    if kind == "sun":
        r = s * 0.28; cx, cy = x + s / 2, y + s / 2
        for k in range(8):
            a = k * math.pi / 4
            d.line([cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35, cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75], fill=c("F97C00"), width=max(4, int(s * 0.06)))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c("FFC83C"), outline=c("F97C00"), width=max(3, int(s * 0.04)))
    elif kind in ("cloud", "rain"):
        col = c("9AA5B1") if kind == "rain" else c("C9CED6")
        cx, cy = x + s / 2, y + s * 0.42
        for dx, dy, r in ((-0.2, 0.05, 0.2), (0.05, -0.08, 0.26), (0.28, 0.08, 0.18), (0.0, 0.14, 0.2)):
            d.ellipse([cx + (dx - r) * s, cy + (dy - r) * s, cx + (dx + r) * s, cy + (dy + r) * s], fill=col)
        d.rectangle([cx - 0.4 * s, cy + 0.02 * s, cx + 0.46 * s, cy + 0.3 * s], fill=col)
        if kind == "rain":
            for k in range(4):
                bx = cx - 0.3 * s + k * 0.22 * s
                d.line([bx, cy + 0.42 * s, bx - 0.08 * s, cy + 0.62 * s], fill=c("387DFF"), width=max(4, int(s * 0.06)))
    elif kind == "cycle":   # 晴れと雨が交互
        icon(d, "sun", x, y, s * 0.6)
        icon(d, "rain", x + s * 0.4, y + s * 0.35, s * 0.6)
    elif kind == "thermo":
        cx = x + s / 2; w = s * 0.16
        d.rounded_rectangle([cx - w, y + s * 0.1, cx + w, y + s * 0.7], radius=int(w), fill=c("FFFFFF"), outline=c(FG), width=max(3, int(s * 0.04)))
        d.rectangle([cx - w * 0.45, y + s * 0.3, cx + w * 0.45, y + s * 0.7], fill=c("F97C00"))
        d.ellipse([cx - s * 0.16, y + s * 0.58, cx + s * 0.16, y + s * 0.9], fill=c("F97C00"), outline=c(FG), width=max(3, int(s * 0.04)))
    elif kind == "umbrella":
        cx, cy = x + s / 2, y + s * 0.5
        d.pieslice([cx - s * 0.42, cy - s * 0.42, cx + s * 0.42, cy + s * 0.42], 180, 360, fill=c("387DFF"), outline=c("1F4E99"), width=max(3, int(s * 0.04)))
        d.line([cx, cy, cx, cy + s * 0.38], fill=c(FG), width=max(4, int(s * 0.06)))
        d.arc([cx - s * 0.16, cy + s * 0.26, cx + s * 0.0, cy + s * 0.46], 0, 180, fill=c(FG), width=max(4, int(s * 0.06)))
    elif kind == "calendar":
        d.rounded_rectangle([x + s * 0.1, y + s * 0.15, x + s * 0.9, y + s * 0.9], radius=int(s * 0.08), fill=c("FFFFFF"), outline=c(FG), width=max(3, int(s * 0.04)))
        d.rectangle([x + s * 0.1, y + s * 0.15, x + s * 0.9, y + s * 0.35], fill=c("0F2A44"))
        for k in range(3):
            for j in range(4):
                d.rectangle([x + s * (0.2 + j * 0.18), y + s * (0.45 + k * 0.15), x + s * (0.3 + j * 0.18), y + s * (0.53 + k * 0.15)], fill=c("C9CED6"))


# ---------- 帯グラフ ----------
def hbar(d, x, y, w, h, vals, cols, fs):
    cx = x
    for (pct, star), col in zip(vals, cols):
        seg = int(w * pct / 100)
        d.rectangle([cx, y, cx + seg, y + h], fill=c(col), outline=c(BG), width=3)
        if star:
            d.rectangle([cx + 2, y + 2, cx + seg - 2, y + h - 2], outline=c(STAR), width=6)
        label = f"{pct}%" + ("★" if star else "")
        f = font(fs, bold=star)
        if d.textlength(label, font=f) + 12 <= seg:
            ctext(d, cx + seg / 2, y + h / 2, label, f, fill=c(FG) if text_dark(col) else c("FFFFFF"))
        cx += seg


def draw_summary(sec, heads, out, title):
    elems = [e for e in ("気温", "降水量", "日照時間") if e in sec]
    n = len(elems)
    fs, lab_w, bh, gap, top = 36, 270, 64, 18, 180
    H = top + (bh + gap) * max(len(sec[e]) for e in elems) + 170
    img = Image.new("RGB", (W, H), c(BG)); d = ImageDraw.Draw(img)
    d.text((40, 20), title, fill=c(FG), font=font(48, True))
    pw = (W - 80 - 40 * (n - 1)) // n
    for k, e in enumerate(elems):
        x0 = 40 + (pw + 40) * k
        d.text((x0, 100), e, fill=c(FG), font=font(44, True))
        rows, bw = sec[e], pw - lab_w
        for i, (region, vals) in enumerate(rows):
            y = top + (bh + gap) * i
            d.text((x0, y + 8), region, fill=c(FG), font=font(fs))
            hbar(d, x0 + lab_w, y, bw, bh, vals, COLORS[e], fs)
        y = top + (bh + gap) * len(rows) + 10
        f, x = font(30), x0 + lab_w
        for nm, col in zip(heads[e], COLORS[e]):
            d.rectangle([x, y, x + 30, y + 30], fill=c(col))
            d.text((x + 40, y - 4), nm, fill=c(FG), font=f)
            x += 40 + d.textlength(nm, font=f) + 40
    d.rectangle([40, H - 60, 70, H - 30], outline=c(STAR), width=5)
    d.text((80, H - 66), "★ 気象庁が特徴ありとした階級（帯の長さが確率。平年なら 33% ずつ）", fill=c(FG), font=font(32))
    img.save(out)


# ---------- 期間×地方のマス目 ----------
def draw_weekly_grid(secs, heads, out, title, periods):
    regions = [r for r, _ in secs[0][1]]
    n, m = len(secs), len(regions)
    H = 1020
    img = Image.new("RGB", (W, H), c(BG)); d = ImageDraw.Draw(img)
    d.text((40, 20), title, fill=c(FG), font=font(48, True))
    lab_w, top, bottom = 320, 210, H - 120
    cw = (W - 80 - lab_w) // n
    ch = (bottom - top) // m
    names = heads["気温"]
    for k, (name, rows) in enumerate(secs):
        x = 40 + lab_w + cw * k
        ctext(d, x + cw / 2, 130, name, font(40, True))
        if k < len(periods):
            ctext(d, x + cw / 2, 178, periods[k], font(30), fill=c("555555"))
        for i, (region, vals) in enumerate(rows):
            y = top + ch * i
            feats = [(names[j], pct, COLORS["気温"][j]) for j, (pct, star) in enumerate(vals) if star]
            if not feats:
                feats = [("特徴なし", None, "F4F6F8")]
            sw = (cw - 16) // len(feats)
            for j, (nm, pct, col) in enumerate(feats):
                sx = x + 8 + sw * j
                fill = mix(col, 0.35 + 0.65 * (pct - 30) / 40) if pct else c(col)
                d.rounded_rectangle([sx, y + 8, sx + sw - 8, y + ch - 8], radius=18, fill=fill, outline=c("FFFFFF"), width=4)
                dark = text_dark(fill.lstrip("#")) if pct else True
                fcol = c(FG) if dark else c("FFFFFF")
                if pct:
                    ctext(d, sx + (sw - 8) / 2, y + ch / 2 - 26, nm, font(38, True), fill=fcol)
                    ctext(d, sx + (sw - 8) / 2, y + ch / 2 + 28, f"{pct}%", font(44, True), fill=fcol)
                else:
                    ctext(d, sx + (sw - 8) / 2, y + ch / 2, nm, font(34), fill=c("777777"))
    for i, region in enumerate(regions):
        y = top + ch * i
        d.text((40, y + ch / 2 - 24), region, fill=c(FG), font=font(40, True))
    # 凡例
    x, y = 40 + lab_w, H - 80
    for nm, col in zip(names, COLORS["気温"]):
        d.rectangle([x, y, x + 34, y + 34], fill=c(col))
        d.text((x + 44, y - 4), nm, fill=c(FG), font=font(32))
        x += 44 + d.textlength(nm, font=font(32)) + 50
    d.text((x, y - 4), "色が濃いほど確率が高い（気象庁が特徴ありとした階級のみ表示）", fill=c("555555"), font=font(30))
    img.save(out)


# ---------- 地方ごとのパネル（期間ごとの積み上げ棒） ----------
def draw_weekly_region(secs, heads, out, title, periods):
    regions = [r for r, _ in secs[0][1]]
    n, m = len(secs), len(regions)
    H = 1060
    img = Image.new("RGB", (W, H), c(BG)); d = ImageDraw.Draw(img)
    d.text((40, 20), title, fill=c(FG), font=font(48, True))
    gx0, gtop, gbot = 40, 190, 800
    pw = (W - gx0 - 40) // m
    bw = int((pw - 60) / (n + 0.6))
    cols = COLORS["気温"]
    for i, region in enumerate(regions):
        x0 = gx0 + pw * i
        d.rounded_rectangle([x0 + 10, 100, x0 + pw - 10, gbot + 80], radius=24, fill=c("F7F8FA"))
        ctext(d, x0 + pw / 2, 140, region, font(42, True))
        for k, (name, rows) in enumerate(secs):
            vals = dict(rows)[region]
            x = x0 + 30 + int(bw * 0.3) + bw * k
            y = gbot
            for (pct, star), col in zip(vals, cols):
                seg = int((gbot - gtop) * pct / 100)
                d.rectangle([x, y - seg, x + bw - 14, y], fill=c(col), outline=c(BG), width=3)
                if star:
                    d.rectangle([x + 2, y - seg + 2, x + bw - 16, y - 2], outline=c(STAR), width=6)
                label = f"{pct}%" + ("★" if star else "")
                f = font(32, bold=star)
                if seg >= 42:
                    ctext(d, x + (bw - 14) / 2, y - seg / 2, label, f, fill=c(FG) if text_dark(col) else c("FFFFFF"))
                y -= seg
            ctext(d, x + (bw - 14) / 2, gbot + 40, name, font(32, True))
    if periods:
        d.text((40, gbot + 150), "　".join(f"{n}: {p}" for (n, _), p in zip(secs, periods)), fill=c("555555"), font=font(30))
    x, y = 40, H - 60
    for nm, col in zip(heads["気温"], cols):
        d.rectangle([x, y, x + 32, y + 32], fill=c(col))
        d.text((x + 42, y - 4), nm, fill=c(FG), font=font(32))
        x += 42 + d.textlength(nm, font=font(32)) + 50
    d.rectangle([x, y, x + 32, y + 32], outline=c(STAR), width=5)
    d.text((x + 42, y - 4), "★ 気象庁が特徴ありとした階級", fill=c(FG), font=font(32))
    img.save(out)


# ---------- カード型（JSON 指定） ----------
def wrap(d, s, f, maxw):
    lines, cur = [], ""
    for ch in s:
        if d.textlength(cur + ch, font=f) > maxw and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    return lines + [cur]


def _draw_cards(spec, ch):
    """カードの本体の高さ ch で描き、(画像, 内容の最下端 y) を返す"""
    bg = spec.get("bg", BG)
    cards = spec["cards"]
    n = len(cards)
    top = 40
    banner = spec.get("banner")
    bh = 160 if banner else 0
    H = top + ch + 40 + (bh + 30 if banner else 0) + (70 if spec.get("title") else 0)
    img = Image.new("RGB", (W, H), c(bg)); d = ImageDraw.Draw(img)
    if spec.get("title"):
        d.text((40, 20), spec["title"], fill=c(FG), font=font(48, True)); top = 110
    gap = 30
    cw = (W - 80 - gap * (n - 1)) // n
    ymax = top
    for k, card in enumerate(cards):
        x = 40 + (cw + gap) * k
        acc = card.get("accent", "0F2A44")
        d.rounded_rectangle([x, top, x + cw, top + ch], radius=28, fill=c("FFFFFF"), outline=c(acc), width=4)
        d.rounded_rectangle([x, top, x + cw, top + 90], radius=28, fill=c(acc))
        d.rectangle([x, top + 50, x + cw, top + 90], fill=c(acc))
        ctext(d, x + cw / 2, top + 45, card["title"], font(44, True), fill=c("FFFFFF"))
        y = top + 110
        icons = card.get("icons") or ([card["icon"]] if card.get("icon") else [])
        if icons:
            isz = min(180, (cw - 40) // max(1, len(icons)))
            ix = x + (cw - isz * len(icons)) / 2
            for ic in icons:
                icon(d, ic, ix, y, isz); ix += isz
            y += isz + 20
        for row in card.get("rows", []):
            if "chip" in row:
                col = row.get("color", MID)
                f_lab, f_chip = font(32), font(row.get("size", 42), True)
                if row.get("label"):
                    d.text((x + 28, y), row["label"], fill=c("555555"), font=f_lab); y += 44
                tw = d.textlength(row["chip"], font=f_chip)
                while tw + 52 > cw - 56 and f_chip.size > 28:   # 札が枠に収まらなければ縮める
                    f_chip = font(f_chip.size - 2, True); tw = d.textlength(row["chip"], font=f_chip)
                d.rounded_rectangle([x + 28, y, x + 28 + max(tw + 52, 220), y + 68], radius=34, fill=c(col))
                d.text((x + 54, y + 8), row["chip"], fill=c(FG) if text_dark(col) else c("FFFFFF"), font=f_chip)
                y += 68 + 20
            elif "text" in row:
                f = font(row.get("size", 38), row.get("bold", False))
                for ln in wrap(d, row["text"], f, cw - 56):
                    d.text((x + 28, y), ln, fill=c(row.get("color", FG)), font=f); y += f.size + 14
                y += 12
        ymax = max(ymax, y)
    if banner:
        by = top + ch + 30
        d.rounded_rectangle([40, by, W - 40, by + bh], radius=24, fill=c(banner.get("color", "EEF3F8")))
        icon(d, banner.get("icon", "rain"), 60, by + 10, bh - 20)
        f = font(banner.get("size", 38), True)
        lines = wrap(d, banner["text"], f, W - 80 - bh - 60)
        ty = by + bh / 2 - (len(lines) * (f.size + 10)) / 2 + 5
        for ln in lines:
            d.text((60 + bh, ty), ln, fill=c(FG), font=f); ty += f.size + 10
    return img, ymax - top


def draw_cards(spec, out):
    _, content = _draw_cards(spec, 3000)
    img, _ = _draw_cards(spec, content + 24)
    img.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="向こう1か月の見通し（地方別）")
    ap.add_argument("--weekly-title", default="週ごとの気温の見通し（地方別）")
    ap.add_argument("--periods", default="", help="期間名に添える日付。カンマ区切り（例: 9/26〜10/2,10/3〜10/9,10/10〜10/23）")
    ap.add_argument("--cards", help="カード型の図の JSON（書式は冒頭コメント）")
    a = ap.parse_args()
    md = Path(a.source).read_text(encoding="utf-8")
    secs, heads = parse(md)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    names = list(secs)
    main_sec = next(s for s in names if s.startswith("向こう"))
    draw_summary(secs[main_sec], heads, out / "summary.png", a.title)
    periods = [p for p in a.periods.split(",") if p]
    weekly = [(s, secs[s]["気温"]) for s in names if s != main_sec and "気温" in secs[s]]
    if weekly:
        draw_weekly_grid(weekly, heads, out / "weekly_grid.png", a.weekly_title, periods)
        draw_weekly_region(weekly, heads, out / "weekly_region.png", a.weekly_title, periods)
    if a.cards:
        for spec in json.loads(Path(a.cards).read_text(encoding="utf-8"))["figures"]:
            draw_cards(spec, out / spec["file"])
    (out / "images.md").write_text(
        "# 図の出典\n\n- すべて気象庁「全般季節予報」（防災情報XML）の発表内容をもとに作図。色は気象庁の平年偏差図に合わせた\n", encoding="utf-8")
    print("生成:", ", ".join(p.name for p in sorted(out.glob("*.png"))))


if __name__ == "__main__":
    main()
