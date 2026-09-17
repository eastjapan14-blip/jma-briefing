#!/usr/bin/env python3
"""台本（script.md）から16:9のpptxを生成する（Keynote対応）。

台本の書式（Markdown）:
  # 動画タイトル
  ## スライド見出し            ← 1つの見出しが1枚
  [type: title|jma|action|note] ← 任意。省略時は jma
      title : 表紙 / jma : 気象庁発表の内容（白地） / action : 視聴者の行動指針（橙） / note : 補足（青）
  - 箇条書き（スライドに載る文。28pt固定なので1枚4項目まで）
  | 列1 | 列2 |               ← 表。2行目の |---| は省略可。1行目が見出し行
  ![出典の表記](images/ファイル名.png)   ← 図。箇条書きがあれば右半分、無ければ中央に大きく
  [ref: rain 30] / [ref: wind 23] / [ref: wave 7] / [ref: typhoon_strength 25] / [ref: typhoon_size 大型]
      ← 気象庁の定義表を出し、該当する行を強調する。1枚に2つまで（横に並ぶ）
  > ナレーション（ノート欄に入る。スライドには出ない）
  ---                          ← この行より下はスライドにしない（照合チェック表用）

文字サイズ: 本文・表・帯ラベルは28pt以上。出典表記と下部の注記だけ小さい。

使い方:
  python3 scripts/build_pptx.py material/<dir>/script.md [--out material/<dir>/slides.pptx]
"""
import argparse, re, sys, zipfile
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

W, H = Emu(12192000), Emu(6858000)  # 16:9 の正規値
FONT = "Hiragino Sans"
BODY = 28          # 本文の最小サイズ
SMALL = 14         # 出典・注記だけに使う
THEME = {
    "title":  {"bg": "0F2A44", "fg": "FFFFFF", "accent": "F2B134", "label": ""},
    "jma":    {"bg": "FFFFFF", "fg": "1A1A1A", "accent": "0F2A44", "label": "気象庁発表"},
    "action": {"bg": "FFF4E0", "fg": "1A1A1A", "accent": "D9480F", "label": "今すぐの行動"},
    "note":   {"bg": "EEF3F8", "fg": "1A1A1A", "accent": "3A6EA5", "label": "補足"},
}
HILITE = "FFE066"

# 気象庁の予報用語の定義（下限以上・上限未満）。upper=None は上限なし
REF = {
    "rain": ("雨の強さ", "mm/h", [("やや強い雨", 10, 20), ("強い雨", 20, 30), ("激しい雨", 30, 50), ("非常に激しい雨", 50, 80), ("猛烈な雨", 80, None)]),
    "wind": ("風の強さ", "m/s", [("やや強い風", 10, 15), ("強い風", 15, 20), ("非常に強い風", 20, 30), ("猛烈な風", 30, None)]),
    "wave": ("波の高さ", "m", [("やや高い", 1.5, 2.5), ("高い", 2.5, 4), ("しける", 4, 6), ("大しけ", 6, 9), ("猛烈にしける", 9, None)]),
    "typhoon_strength": ("台風の強さ", "最大風速 m/s", [("台風", 17.2, 33), ("強い", 33, 44), ("非常に強い", 44, 54), ("猛烈な", 54, None)]),
    "typhoon_size": ("台風の大きさ", "強風域 km", [("台風", 0, 500), ("大型", 500, 800), ("超大型", 800, None)]),
}
REF_NOTE = "定義：気象庁「予報用語」。雨は1時間雨量、風は平均風速、台風の強さは最大風速、大きさは風速15m/s以上の半径。範囲は下限以上・上限未満"


def rgb(h):
    return RGBColor.from_string(h)


def parse(md):
    title, slides, cur = "", [], None
    for line in md.splitlines():
        s = line.rstrip()
        if s == "---":
            break
        if s.startswith("# ") and not title:
            title = s[2:].strip()
        elif s.startswith("## "):
            cur = {"head": s[3:].strip(), "bullets": [], "notes": [], "type": "jma", "table": [], "image": None, "refs": []}
            slides.append(cur)
        elif cur is None:
            continue
        elif m := re.match(r"\[type:\s*(\w+)\]", s):
            cur["type"] = m.group(1)
        elif m := re.match(r"\[ref:\s*(\w+)\s+(\S+)\]", s):
            cur["refs"].append((m.group(1), m.group(2)))
        elif m := re.match(r"!\[(.*?)\]\((.*?)\)", s):
            cur["image"] = (m.group(2), m.group(1))
        elif s.startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                cur["table"].append(cells)
        elif s.startswith("- "):
            cur["bullets"].append(s[2:].strip())
        elif s.startswith(">"):
            cur["notes"].append(s[1:].strip())
    return title, slides


def add_box(slide, x, y, w, h, text, size, color, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=10):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, t in enumerate(text if isinstance(text, list) else [text]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing)
        r = p.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = rgb(color)
    return tb


def add_table(slide, x, y, w, rows, accent, fg, hilite_rows=(), size=BODY):
    nrow, ncol = len(rows), max(len(r) for r in rows)
    shape = slide.shapes.add_table(nrow, ncol, x, y, w, Inches(0.58) * nrow)
    tbl = shape.table
    # 列幅は各列の最長文字数に比例させる（最小 1.6in）。折り返しを減らして行の高さを抑える
    lens = [max(len(r[j]) if j < len(r) else 0 for r in rows) for j in range(ncol)]
    minw = Inches(1.6)
    raw = [max(minw, int(w * l / max(1, sum(lens)))) for l in lens]
    scale = w / sum(raw)
    for j in range(ncol):
        tbl.columns[j].width = int(raw[j] * scale)
    for i, row in enumerate(rows):
        for j in range(ncol):
            cell = tbl.cell(i, j)
            cell.text = row[j] if j < len(row) else ""
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size, r.font.name = Pt(size), FONT
                    r.font.bold = (i == 0) or (i in hilite_rows)
                    r.font.color.rgb = rgb("FFFFFF" if i == 0 else fg)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(accent if i == 0 else (HILITE if i in hilite_rows else ("FFFFFF" if i % 2 else "F4F6F8")))
    return shape


def add_image(slide, path, x, y, w, h):
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    return slide.shapes.add_picture(str(path), x + (w - pw) // 2, y, pw, ph)


def ref_rows(kind, value):
    title, unit, bands = REF[kind]
    rows = [[title, unit]]
    hit = None
    try:
        v = float(value)
    except ValueError:
        v = None
    for i, (name, lo, hi) in enumerate(bands, 1):
        rng = f"{lo:g}〜{hi:g}" if hi is not None else f"{lo:g}以上"
        rows.append([name, rng])
        if (v is not None and lo <= v and (hi is None or v < hi)) or (v is None and name == value):
            hit = i
    return rows, hit


def build(slides, out, footer, base):
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]
    warns = []
    for i, s in enumerate(slides):
        th = THEME.get(s["type"], THEME["jma"])
        sl = prs.slides.add_slide(blank)
        bg = sl.background.fill; bg.solid(); bg.fore_color.rgb = rgb(th["bg"])
        fcol = "BBBBBB" if s["type"] == "title" else "888888"
        add_box(sl, Inches(0.4), Inches(7.05), Inches(9.5), Inches(0.4), footer, SMALL - 3, fcol)
        add_box(sl, Inches(11.6), Inches(7.05), Inches(1.4), Inches(0.4), f"{i+1}/{len(slides)}", SMALL - 3, fcol, align=PP_ALIGN.RIGHT)
        if s["notes"]:
            sl.notes_slide.notes_text_frame.text = "\n".join(s["notes"])

        if s["type"] == "title":
            add_box(sl, Inches(0.8), Inches(1.8), Inches(11.7), Inches(3.0), s["head"], 48, th["fg"], bold=True, anchor=MSO_ANCHOR.MIDDLE)
            if s["bullets"]:
                add_box(sl, Inches(0.8), Inches(4.9), Inches(11.7), Inches(1.6), s["bullets"], BODY, th["accent"])
            continue

        # 上部の帯（ラベルも28pt）
        bar = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.75))
        bar.fill.solid(); bar.fill.fore_color.rgb = rgb(th["accent"]); bar.line.fill.background()
        add_box(sl, Inches(0.4), Inches(0.05), Inches(8), Inches(0.65), th["label"], BODY, "FFFFFF", bold=True, anchor=MSO_ANCHOR.MIDDLE)
        add_box(sl, Inches(0.7), Inches(0.95), Inches(12), Inches(1.0), s["head"], 36, th["accent"], bold=True, anchor=MSO_ANCHOR.MIDDLE)

        top, left, full_w = Inches(2.05), Inches(0.7), Inches(11.9)
        if len(s["bullets"]) > 4:
            warns.append(f"スライド{i+1}「{s['head']}」: 箇条書きが{len(s['bullets'])}項目。28ptでは4項目までが目安")

        if s["refs"]:
            n = len(s["refs"])
            colw = (full_w - Inches(0.4) * (n - 1)) // n if n > 1 else Inches(8)
            x0 = left if n > 1 else left + (full_w - colw) // 2   # 1つだけなら中央寄せ
            for k, (kind, val) in enumerate(s["refs"]):
                rows, hit = ref_rows(kind, val)
                add_table(sl, x0 + (colw + Inches(0.4)) * k, top, colw, rows, th["accent"], th["fg"], hilite_rows=(hit,) if hit else ())
            add_box(sl, left, Inches(6.5), full_w, Inches(0.5), REF_NOTE, SMALL - 2, "555555")
            if s["bullets"]:
                warns.append(f"スライド{i+1}: 定義表と箇条書きは同居できません（箇条書きは無視）")
            continue

        if s["image"]:
            path = base / s["image"][0]
            if not path.exists():
                warns.append(f"スライド{i+1}: 画像がありません {path}")
            else:
                if s["bullets"] or s["table"]:
                    bw = Inches(5.4)
                    add_image(sl, path, left + bw + Inches(0.3), top, full_w - bw - Inches(0.3), Inches(4.5))
                    add_box(sl, left + bw + Inches(0.3), Inches(6.55), full_w - bw - Inches(0.3), Inches(0.45), f"出典：{s['image'][1]}", SMALL, "555555")
                    if s["bullets"]:
                        add_box(sl, left, top, bw, Inches(4.6), [f"・{b}" for b in s["bullets"]], BODY, th["fg"], spacing=14)
                    else:
                        add_table(sl, left, top, bw, s["table"], th["accent"], th["fg"])
                else:
                    add_image(sl, path, left, Inches(1.95), full_w, Inches(5.05))
                    add_box(sl, Inches(0.4), Inches(7.05), Inches(9.5), Inches(0.4), f"出典：{s['image'][1]}", SMALL - 3, "555555")
                continue

        if s["table"]:
            add_table(sl, left, top, full_w, s["table"], th["accent"], th["fg"])
            if s["bullets"]:
                add_box(sl, left, top + Inches(0.75) * len(s["table"]) + Inches(0.3), full_w, Inches(1.5), [f"・{b}" for b in s["bullets"]], BODY, th["fg"], spacing=14)
            continue

        add_box(sl, left + Inches(0.2), top, full_w - Inches(0.4), Inches(4.6), [f"・{b}" for b in s["bullets"]], BODY, th["fg"], spacing=16)
    prs.save(out)
    return warns


def keynote_sanitize(path):
    """python-pptx の出力を Keynote が開ける形に直す（3点）。
    1. sldSz の type="screen4x3" と 16:9 幅の矛盾 → 12192000 に揃えて type を外す
    2. presentation.xml に notesMasterIdLst が無い → 追加
    3. Windows 用 printerSettings*.bin → 削除
    """
    with zipfile.ZipFile(path) as z:
        ent = {n: z.read(n) for n in z.namelist()}
    for n in [n for n in ent if n.startswith("ppt/printerSettings/")]:
        del ent[n]
    rels_p, pres_p, ct_p = "ppt/_rels/presentation.xml.rels", "ppt/presentation.xml", "[Content_Types].xml"
    rels = re.sub(r'<Relationship[^>]*printerSettings[^>]*/>', "", ent[rels_p].decode())
    ent[rels_p] = rels.encode()
    ent[ct_p] = re.sub(r'<Default Extension="bin"[^>]*/>', "", ent[ct_p].decode()).encode()
    pres = re.sub(r'<p:sldSz[^/]*/>', '<p:sldSz cx="12192000" cy="6858000"/>', ent[pres_p].decode(), count=1)
    if "<p:notesMasterIdLst" not in pres:
        m = re.search(r'<Relationship Id="(rId\d+)"[^>]*notesMaster[^>]*/>', rels)
        if m:
            pres = pres.replace("</p:sldIdLst>", f'</p:sldIdLst><p:notesMasterIdLst><p:notesMasterId r:id="{m.group(1)}"/></p:notesMasterIdLst>', 1)
    ent[pres_p] = pres.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in ent.items():
            z.writestr(n, d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--out")
    ap.add_argument("--footer", default="出典：気象庁発表（防災情報XML）／解説は発表内容の範囲に限ります")
    a = ap.parse_args()
    src = Path(a.script)
    title, slides = parse(src.read_text(encoding="utf-8"))
    if not slides:
        sys.exit("スライドが見つかりません（## 見出しが必要）")
    out = Path(a.out) if a.out else src.with_name("slides.pptx")
    warns = build(slides, out, a.footer, src.parent)
    keynote_sanitize(out)
    chars = sum(len("".join(s["notes"])) for s in slides)
    print(f"{out}  スライド {len(slides)} 枚 / ナレーション約 {chars} 文字（目安 {chars/300:.1f} 分）")
    for w in warns:
        print("注意:", w)


if __name__ == "__main__":
    main()
