"""「最新の気象データ」CSV（Shift_JIS、全地点1ファイル）→ Observation。

列名は日付で変わる（「18日の最高気温(℃)」「17日までの観測史上1位の値（℃）」）ので、
位置ではなく正規表現でヘッダを引く。必要列が無ければ ParserError（推測で値を作らない）。
"""
import csv
import io
import re
from datetime import date, timedelta
from typing import Optional

from ..log import log
from ..models import Observation, ParserError, Quality, Record, quality_from_code, today_quality_from_code

_UNIT = r"[\(（](?:℃|mm|cm)[\)）]"


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParserError("CSV をデコードできません")


def _find(header, pattern, required=True):
    rx = re.compile(pattern)
    hits = [i for i, h in enumerate(header) if rx.search(h)]
    if not hits:
        if required:
            raise ParserError(f"列が見つかりません: {pattern}")
        return None
    return hits[0]


def find_columns(header: list) -> dict:
    """ヘッダ → 列インデックス。今日の値 / 品質 / 起時 / 観測史上1位 / 当月1位 / 統計開始年。"""
    c = {}
    c["station"] = _find(header, r"^観測所番号$")
    c["pref"] = _find(header, r"^都道府県$")
    c["name"] = _find(header, r"^地点$")
    c["cur_y"], c["cur_m"], c["cur_d"] = (_find(header, r"^現在時刻\(年\)$"), _find(header, r"^現在時刻\(月\)$"),
                                          _find(header, r"^現在時刻\(日\)$"))
    c["cur_h"], c["cur_mi"] = _find(header, r"^現在時刻\(時\)$"), _find(header, r"^現在時刻\(分\)$")
    # 今日の値: 「N日の最高気温(℃)」「N日の最大値(mm)」「N日の値(mm)」など。平年・前日差は除外
    vals = [i for i, h in enumerate(header)
            if re.match(r"^\d+日の[^ま]*" + _UNIT + r"$", h) and "平年" not in h and "起時" not in h]
    if not vals:
        raise ParserError("今日の値の列が見つかりません")
    c["value"] = vals[0]
    vh = header[c["value"]]
    m = re.match(r"^(\d+)日の(.*?)" + _UNIT + r"$", vh)
    c["day"] = int(m.group(1))
    stem = f"{m.group(1)}日の{m.group(2)}"
    c["quality"] = _find(header, "^" + re.escape(stem) + r"の品質情報$")
    c["time_h"] = _find(header, "^" + re.escape(stem) + r"起時（時）", required=False)
    c["time_m"] = _find(header, "^" + re.escape(stem) + r"起時（分）", required=False)
    c["flag"] = _find(header, r"^極値更新$")
    c["short"] = _find(header, r"^10年未満での極値更新$")
    c["at_v"] = _find(header, r"^\d+日までの観測史上1位の値" + _UNIT + r"$")
    c["at_q"] = _find(header, r"^\d+日までの観測史上1位の値の品質情報$")
    c["at_y"] = _find(header, r"^\d+日までの観測史上1位の値(?:を観測した起日（年）|の年)$")
    c["at_m"] = _find(header, r"^\d+日までの観測史上1位の値(?:を観測した起日（月）|の月)$")
    c["at_d"] = _find(header, r"^\d+日までの観測史上1位の値(?:を観測した起日（日）|の日)$")
    c["mo_v"] = _find(header, r"^\d+日までの\d+月の1位の値(?:" + _UNIT + r")?$")
    c["month"] = int(re.search(r"(\d+)月の1位", header[c["mo_v"]]).group(1))
    c["mo_q"] = _find(header, r"^\d+日までの\d+月の1位の値の品質情報$")
    c["mo_y"] = _find(header, r"^\d+日までの\d+月の1位の値(?:の起日（年）|の年)$")
    c["mo_m"] = _find(header, r"^\d+日までの\d+月の1位の値(?:の起日（月）|の月)$")
    c["mo_d"] = _find(header, r"^\d+日までの\d+月の1位の値(?:の起日（日）|の日)$")
    c["start"] = _find(header, r"^統計開始年$")
    return c


def _num(s) -> Optional[float]:
    s = (s or "").strip().replace("+", "")
    if s in ("", "×", "--", "///", "#"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ymd(y, m, d) -> Optional[str]:
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except (ValueError, TypeError):
        return None


def split_name(s: str):
    """「宗谷岬（ソウヤミサキ）」→ ("宗谷岬", "ソウヤミサキ")"""
    m = re.match(r"^(.*?)[（(](.*?)[）)]\s*$", s.strip())
    return (m.group(1), m.group(2)) if m else (s.strip(), "")


def split_pref(s: str):
    """「北海道 宗谷地方」→ ("北海道", "北海道 宗谷地方")。他県はそのまま。"""
    s = re.sub(r"\s+", " ", s.strip())
    if s.startswith("北海道"):
        return "北海道", s
    return s, s


def parse(metric, data: bytes) -> list:
    text = decode(data)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ParserError("CSV が空です")
    c = find_columns(rows[0])
    out = []
    bad = 0
    for r in rows[1:]:
        if len(r) < len(rows[0]) - 1:
            bad += 1
            continue
        try:
            cur = date(int(r[c["cur_y"]]), int(r[c["cur_m"]]), int(r[c["cur_d"]]))
        except ValueError:
            bad += 1
            continue
        # 値の対象日: 現在時刻の日と列名の日が違えば前日（0時台の切替）
        obs_date = cur if cur.day == c["day"] else cur - timedelta(days=1)
        if obs_date.day != c["day"]:
            obs_date = cur
        name, _kana = split_name(r[c["name"]])
        pref, pref_full = split_pref(r[c["pref"]])
        flag_s = r[c["flag"]].strip()
        flag = int(flag_s) if flag_s.isdigit() else None
        t = None
        if c["time_h"] is not None and r[c["time_h"]].strip():
            t = f'{int(r[c["time_h"]]):02d}:{int(r[c["time_m"]] or 0):02d}'
        at = Record(_num(r[c["at_v"]]), _ymd(r[c["at_y"]], r[c["at_m"]], r[c["at_d"]]),
                    quality_from_code(r[c["at_q"]])) if _num(r[c["at_v"]]) is not None else None
        mo = Record(_num(r[c["mo_v"]]), _ymd(r[c["mo_y"]], r[c["mo_m"]], r[c["mo_d"]]),
                    quality_from_code(r[c["mo_q"]])) if _num(r[c["mo_v"]]) is not None else None
        start = r[c["start"]].strip()
        out.append(Observation(
            metric=metric.id, station_id=r[c["station"]].strip(), name=name, pref=pref, pref_full=pref_full,
            obs_date=obs_date.isoformat(), obs_time=t, value=_num(r[c["value"]]),
            quality=today_quality_from_code(r[c["quality"]]), flag=flag,
            short_stats=(r[c["short"]].strip() == "1"), prev_alltime=at, prev_monthly=mo,
            stats_start=int(start) if start.isdigit() else None, source="csv",
            source_time=f'{cur.isoformat()}T{int(r[c["cur_h"]]):02d}:{int(r[c["cur_mi"]]):02d}'))
    if bad:
        log("parse", "parser_warning", metric=metric.id, skipped_rows=bad)
    log("parse", "parse_n", metric=metric.id, n=len(out), month=c["month"], day=c["day"])
    return out
