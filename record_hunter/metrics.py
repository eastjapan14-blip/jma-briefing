"""Metric Registry。メトリクスの追加はここに定義を1件足すだけで済むようにする。

comparator: "max" = 大きいほど極端（気温高・降水・積雪）、"min" = 小さいほど極端（最低気温）。
near_abs / near_ratio: 従来1位にこれだけ近ければ順位ページを取得して歴代順位を確認する（enrich トリガー）。
rank_row: 地点別「観測史上1～10位の値」ページの要素名（前方一致）。None なら順位ページに該当行が無い。
ru_section: 「観測史上1位の値 更新状況」ページの節見出し（部分一致）。
season: 有効な月。None なら通年。季節外の CSV 404 はエラー扱いしない。
"""
from dataclasses import dataclass
from typing import Optional

MDRR = "https://www.data.jma.go.jp/stats/data/mdrr"


@dataclass(frozen=True)
class MetricDef:
    id: str
    label: str
    unit: str
    csv_key: str
    csv_url: str
    comparator: str = "max"
    decimals: int = 1
    near_abs: Optional[float] = None
    near_ratio: Optional[float] = None
    rank_row: Optional[str] = None
    ru_section: Optional[str] = None
    season: Optional[tuple] = None
    percent_meaningful: bool = False
    emoji: str = "📈"
    poll_minutes: int = 10      # ソースの更新周期（気温 60 分、降水 10 分）。これより短い間隔で再取得しない


_WINTER = (10, 11, 12, 1, 2, 3, 4, 5)

METRICS = {m.id: m for m in [
    MetricDef("tmax", "日最高気温", "℃", "mxtemsadext00", f"{MDRR}/tem_rct/alltable/mxtemsadext00_rct.csv",
              "max", 1, near_abs=1.0, rank_row="日最高気温の高い方から", ru_section="日最高気温の高い方から", emoji="🌡",
              poll_minutes=60),
    MetricDef("tmin", "日最低気温", "℃", "mntemsadext00", f"{MDRR}/tem_rct/alltable/mntemsadext00_rct.csv",
              "min", 1, near_abs=1.0, rank_row="日最低気温の低い方から", ru_section="日最低気温の低い方から", emoji="❄",
              poll_minutes=60),
    MetricDef("pre1h", "1時間降水量", "mm", "pre1h00", f"{MDRR}/pre_rct/alltable/pre1h00_rct.csv",
              "max", 1, near_ratio=0.9, rank_row="日最大1時間降水量", ru_section="1時間降水量の日最大値",
              percent_meaningful=True, emoji="🌧"),
    MetricDef("pre24h", "24時間降水量", "mm", "pre24h00", f"{MDRR}/pre_rct/alltable/pre24h00_rct.csv",
              "max", 1, near_ratio=0.9, rank_row=None, ru_section="24時間降水量の日最大値",
              percent_meaningful=True, emoji="🌧"),
    MetricDef("preday", "日降水量", "mm", "predaily00", f"{MDRR}/pre_rct/alltable/predaily00_rct.csv",
              "max", 1, near_ratio=0.9, rank_row="日降水量", ru_section="日降水量",
              percent_meaningful=True, emoji="🌧"),
    MetricDef("snowdepth", "積雪", "cm", "snc00", f"{MDRR}/snc_rct/alltable/snc00_rct.csv",
              "max", 0, near_ratio=0.9, rank_row="日最深積雪", ru_section="最深積雪", season=_WINTER,
              percent_meaningful=True, emoji="⛄", poll_minutes=60),
    MetricDef("snow24h", "24時間降雪量", "cm", "snd24h00", f"{MDRR}/snc_rct/alltable/snd24h00_rct.csv",
              "max", 0, near_ratio=0.9, rank_row=None, ru_section="24時間降雪量", season=_WINTER,
              percent_meaningful=True, emoji="⛄", poll_minutes=60),
]}


def cmp(m: MetricDef, a: float, b: float) -> int:
    """a が b より極端なら +1、同値 0、劣れば -1。"""
    if a == b:
        return 0
    more = a > b if m.comparator == "max" else a < b
    return 1 if more else -1


def more_extreme(m: MetricDef, a: float, b: float) -> bool:
    return cmp(m, a, b) > 0


def near(m: MetricDef, value: float, ref: float) -> bool:
    """value が ref（従来記録）に十分近いか（enrich トリガー）。"""
    if m.near_abs is not None:
        return abs(value - ref) <= m.near_abs
    if m.near_ratio is not None and ref > 0:
        return value >= ref * m.near_ratio
    return False


def fmt(m: MetricDef, v) -> str:
    if v is None:
        return "--"
    return f"{v:.{m.decimals}f}"


def active(m: MetricDef, month: int) -> bool:
    return m.season is None or month in m.season


def by_ru_section(heading: str) -> Optional[MetricDef]:
    """更新状況ページの節見出し → MetricDef。曖昧一致を避けるため長い順に照合。"""
    for m in sorted(METRICS.values(), key=lambda x: -len(x.ru_section or "")):
        if m.ru_section and m.ru_section in heading:
            return m
    return None
