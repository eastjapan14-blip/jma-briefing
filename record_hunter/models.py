"""データモデル（品質・観測値・順位エントリ・候補）。"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Quality(str, Enum):
    NORMAL = "NORMAL"          # 8 正常値
    CAUTION = "CAUTION"        # 5 準正常値
    INSUFFICIENT = "INSUFFICIENT"  # 4 資料不足 / 3 疑問 / 2 利用不適
    MISSING = "MISSING"        # 1 欠測 / 0 統計しない / 空欄


QUALITY_CODES = {"8": Quality.NORMAL, "5": Quality.CAUTION, "4": Quality.INSUFFICIENT,
                 "3": Quality.INSUFFICIENT, "2": Quality.INSUFFICIENT, "1": Quality.MISSING, "0": Quality.MISSING}


def quality_from_code(code) -> Quality:
    return QUALITY_CODES.get(str(code).strip(), Quality.MISSING)


# 当日の値は日が終わるまで「資料不足(4)」「準正常(5)」が付く（統計対象の時間がまだ欠けているため）。
# 気象庁自身がその値に極値更新フラグを付けるので、当日値については 8/5/4 を通常（速報値）として扱う。
# 本当に資料が欠けた値は翌日の「更新状況」ページとの突き合わせ（confirm）で REVISED にする。
TODAY_QUALITY_CODES = {"8": Quality.NORMAL, "5": Quality.NORMAL, "4": Quality.NORMAL, "3": Quality.INSUFFICIENT,
                       "2": Quality.INSUFFICIENT, "1": Quality.MISSING, "0": Quality.MISSING}


def today_quality_from_code(code) -> Quality:
    return TODAY_QUALITY_CODES.get(str(code).strip(), Quality.MISSING)


def quality_from_mark(mark: str) -> Quality:
    """HTML表の記号 ")"=準正常 "]"=資料不足 "×"=欠測。"""
    return {"": Quality.NORMAL, ")": Quality.CAUTION, "]": Quality.INSUFFICIENT}.get(mark, Quality.MISSING)


SEVERITY_ORDER = ["NONE", "C", "B", "A"]


def sev_gt(a: str, b: str) -> bool:
    return SEVERITY_ORDER.index(a) > SEVERITY_ORDER.index(b)


def sev_max(*xs: str) -> str:
    return max(xs, key=SEVERITY_ORDER.index) if xs else "NONE"


@dataclass
class Record:
    value: Optional[float]
    date: Optional[str]            # "YYYY-MM-DD" / "YYYY-MM" / "YYYY"
    quality: Optional[Quality] = None

    def to_dict(self):
        return {"value": self.value, "date": self.date}


@dataclass
class Observation:
    metric: str
    station_id: Optional[str]
    name: str
    pref: str                       # 都道府県（北海道は「北海道」に正規化）
    obs_date: str                   # "YYYY-MM-DD"
    value: Optional[float]
    quality: Quality
    obs_time: Optional[str] = None  # "HH:MM"
    muni: Optional[str] = None
    flag: Optional[int] = None      # 極値更新: 1-12 = 当月1位更新, 13 = 観測史上1位更新
    short_stats: bool = False       # 統計期間10年未満
    prev_alltime: Optional[Record] = None
    prev_monthly: Optional[Record] = None
    stats_start: Optional[int] = None
    source: str = "csv"             # csv | rank_update
    source_time: Optional[str] = None
    remark: str = ""
    pref_full: str = ""


@dataclass
class RankEntry:
    rank: int
    value: Optional[float]
    date: Optional[str]
    mark: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Candidate:
    obs: Observation
    tags: list = field(default_factory=list)
    notifiable: bool = True
    enrich: bool = False
    reasons: list = field(default_factory=list)


class ParserError(Exception):
    """ページ構造が想定と違う。推測で値を作らず通知を止める。"""
