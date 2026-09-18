"""「観測史上1位の値 更新状況」（rank_update/dMMDD.html）→ Observation。

節構成: 「観測史上１位の値」の下に要素別見出し「日最高気温の高い方から（N地点）」…、
その後「M月の１位の値」の下に同じ要素別見出し。各表の列は
  都道府県 | 市町村 | 地点 | 更新した値 | [起時] | N日までの1位の値 | 起日 | 統計開始年 | 備考([タイ記録])
要素名は <table> の <caption>（「1時間降水量の日最大値（5地点）」）。
CSV に無い市町村と [タイ記録] の備考が取れる。値の記号 ")" "]" は品質へ写す。
"""
import re
from datetime import date
from html.parser import HTMLParser

from ..log import log
from ..metrics import by_ru_section
from ..models import Observation, ParserError, Record, quality_from_mark


class _P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []           # ("h", text) | ("row", cells)
        self._h = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "caption"):
            self._h = ""
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "caption") and self._h is not None:
            self.items.append(("h", re.sub(r"\s+", " ", self._h).strip()))
            self._h = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(self._cell.strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.items.append(("row", self._row))
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data
        elif self._h is not None:
            self._h += data


_VAL = re.compile(r"^(-?\d+(?:\.\d+)?)\s*([\)\]]?)")


def _val(s):
    m = _VAL.match(s.strip())
    if not m:
        return None, ""
    return float(m.group(1)), m.group(2)


def _iso(s):
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{4})/(\d{1,2})", s)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


def parse(html: str, obs_date: str) -> list:
    """obs_date: このページが表す日（"YYYY-MM-DD"）。"""
    p = _P()
    p.feed(html)
    if not any(k == "h" and "更新状況" in t for k, t in p.items):
        raise ParserError("更新状況ページの見出しが見つかりません")
    month = int(obs_date[5:7])
    section = None    # 13 = 観測史上1位, month = 当月1位
    metric = None
    header = None
    out = []
    for kind, item in p.items:
        if kind == "h":
            if "観測史上" in item and "位の値" in item and "地点数" not in item and "更新状況" not in item:
                section, metric = 13, None
            elif re.search(r"\d+月の[１1]位の値", item):
                section, metric = month, None
            elif section is not None:
                metric = by_ru_section(item)
                header = None
            continue
        cells = item
        if metric is None or section is None or not cells:
            continue
        if cells[0] == "都道府県":
            header = cells
            continue
        if len(cells) < 7 or header is None:
            continue
        has_time = "時分" in "".join(cells[3:5]) or len(cells) >= 9
        # 列: 都道府県, 市町村, 地点, 値, [起時], 従来値, 起日, 統計開始年, [備考]
        pref, muni, name_raw, val_s = cells[0], cells[1], cells[2], cells[3]
        i = 5 if has_time else 4
        prev_s, prev_date_s, start_s = cells[i], cells[i + 1], cells[i + 2]
        remark = cells[i + 3] if len(cells) > i + 3 else ""
        time_s = cells[4] if has_time else ""
        value, mark = _val(val_s)
        if value is None:
            continue
        name = re.sub(r"[（(].*?[）)]", "", name_raw).strip()
        pv, pmark = _val(prev_s)
        prev = Record(pv, _iso(prev_date_s), quality_from_mark(pmark)) if pv is not None else None
        start = re.sub(r"\D", "", start_s)
        obs = Observation(
            metric=metric.id, station_id=None, name=name, pref="北海道" if pref.startswith("北海道") else pref,
            pref_full=pref, obs_date=obs_date, value=value, quality=quality_from_mark(mark),
            obs_time=time_s[:5] if re.match(r"\d\d:\d\d", time_s) else None, muni=muni or None,
            flag=section, stats_start=int(start) if start else None, source="rank_update",
            remark=remark.strip("[]［］ "))
        if section == 13:
            obs.prev_alltime = prev
        else:
            obs.prev_monthly = prev
        out.append(obs)
    log("parse", "parse_n", source="rank_update", date=obs_date, n=len(out))
    return out
