#!/usr/bin/env python3
"""気象庁の報道発表資料を取得し、台本用の press.md にする（段階A）。

使い方:
  python3 scripts/fetch_press.py --list [--days 3]        # 最近の報道発表を一覧（段階Aの候補に印）
  python3 scripts/fetch_press.py <報道発表ページのURL> --out material/<dir>
    → <out>/press.md（本文＋PDFの全文テキスト）、<out>/raw/*.pdf
PDFの文字抽出には pdftotext（poppler）を使う。
"""
import argparse, re, subprocess, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = "https://www.jma.go.jp"
LIST_JS = f"{BASE}/jma/press_list.js"
UA = {"User-Agent": "Mozilla/5.0"}
# 記者会見に対応する報道発表の目印（URLのyokoku、見通し・影響についての表題）
TIER_A = re.compile(r"yokoku|見通し|影響について|記者会見|会見")
KEYWORDS = re.compile(r"台風|大雨|大雪|暴風|線状降水帯|特別警報|高潮|梅雨前線|見通し|影響について|会見")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def press_list():
    js = get(LIST_JS).decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r"array\[num\+\+\] = \['(\d)','([^']*)','(\d+)','(\d+)','(\d+)','([^']*)'\]", js):
        typ, url, y, mo, d, title = m.groups()
        y = int(y)
        year = 1988 + y if y > 11 else 2018 + y
        url = url if url.startswith("http") else BASE + url
        out.append({"type": typ, "url": url, "date": date(year, int(mo), int(d)), "title": title.strip()})
    return out


def recent(days=3):
    since = date.today() - timedelta(days=days)
    for e in press_list():
        if e["date"] < since or e["type"] != "1":
            continue
        if not KEYWORDS.search(e["title"] + e["url"]):
            continue
        e["tier"] = "A" if TIER_A.search(e["title"] + e["url"]) else "B"
        yield e


def html_text(html):
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    body = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", body)
    txt = re.sub(r"<[^>]+>", " ", body)
    txt = re.sub(r"[ \t　]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt


def fetch_page(url, out):
    html = get(url).decode("utf-8", "ignore")
    title = (re.findall(r"<title>(.*?)</title>", html) or [""])[0].replace(" | 気象庁", "")
    txt = html_text(html)
    i, j = txt.find("報道発表日"), txt.find("問合せ先")
    main = txt[i:j].strip() if i >= 0 and j > i else txt[:3000]
    parts = [f"# 報道発表資料：{title}", f"- URL: {url}", "", "## 本文", main, ""]
    (out / "raw").mkdir(parents=True, exist_ok=True)
    for m in re.finditer(r'<a href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        pdf_url = href if href.startswith("http") else url.rsplit("/", 1)[0] + "/" + href
        pdf = out / "raw" / pdf_url.rsplit("/", 1)[-1]
        pdf.write_bytes(get(pdf_url))
        txt_path = pdf.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(pdf), str(txt_path)], check=False)
        body = txt_path.read_text(errors="ignore") if txt_path.exists() else "(pdftotext 失敗)"
        pages = body.split("\f")
        parts.append(f"## PDF：{label}（{len(pages)}ページ）")
        parts.append(f"- ファイル: raw/{pdf.name}")
        for k, pg in enumerate(pages, 1):
            pg = pg.strip()
            if pg:
                parts.append(f"### p.{k}")
                parts.append(pg)
        parts.append("")
        print(f"PDF {pdf.name} {len(pages)}ページ", file=sys.stderr)
    (out / "press.md").write_text("\n".join(parts), encoding="utf-8")
    print(out / "press.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.list or not a.url:
        for e in recent(a.days):
            print(f'{e["tier"]} {e["date"]} {e["title"]} | {e["url"]}')
        return
    out = Path(a.out) if a.out else Path("material") / f"{date.today():%Y%m%d}_press"
    fetch_page(a.url, out)


if __name__ == "__main__":
    main()
