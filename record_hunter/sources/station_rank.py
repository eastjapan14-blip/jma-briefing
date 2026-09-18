"""地点別「観測史上1～10位の値」ページ（rank_s.php / rank_a.php）→ {要素名: (entries, 統計期間)}。

セル書式: "167.0(2016/9/6)"  "22 ](2026)"  "--(2026/8)"  "23.4 南南西(2015/10/2)"
"""
import re
from html.parser import HTMLParser

from ..models import ParserError, RankEntry


class _P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None
        self.h3 = []
        self._h3 = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""
        elif tag == "h3":
            self._h3 = ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(self._cell.strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "h3" and self._h3 is not None:
            self.h3.append(self._h3.strip())
            self._h3 = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data
        elif self._h3 is not None:
            self._h3 += data
        self.text += data


_CELL = re.compile(r"^\s*(--|-?\d+(?:\.\d+)?)\s*([\)\]]?)\s*[^\d(]*\((\d{4}(?:/\d{1,2}){0,2})")


def parse_cell(s: str, rank: int) -> RankEntry:
    m = _CELL.match(s)
    if not m:
        return RankEntry(rank, None, None, "?")
    v, mark, d = m.groups()
    parts = d.split("/")
    iso = parts[0] if len(parts) == 1 else (f"{parts[0]}-{int(parts[1]):02d}" if len(parts) == 2
                                            else f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}")
    return RankEntry(rank, None if v == "--" else float(v), iso, mark)


def parse(html: str) -> dict:
    p = _P()
    p.feed(html)
    if "表示することが出来ませんでした" in p.text:
        raise ParserError("順位ページが表示できない（地点番号が不正の可能性）")
    out = {"station": p.h3[-1] if p.h3 else "", "elements": {}}
    seen_header = False
    for r in p.rows:
        if r and r[0].startswith("要素名"):
            seen_header = True
            continue
        if not seen_header or len(r) < 12:
            continue
        label = r[0]
        entries = [parse_cell(c, i + 1) for i, c in enumerate(r[1:11])]
        out["elements"][label] = {"entries": [e.to_dict() for e in entries], "period": r[11]}
    if not out["elements"]:
        raise ParserError("順位表が見つかりません")
    return out


def find_row(parsed: dict, row_label: str):
    """要素名の前方一致で行を返す（"日最高気温の高い方から(℃)" など）。"""
    for label, row in parsed.get("elements", {}).items():
        if label.startswith(row_label):
            return row
    return None
