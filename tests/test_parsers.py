from conftest import FIXTURES
import pytest

from record_hunter.metrics import METRICS
from record_hunter.models import ParserError, Quality
from record_hunter.sources import latest_csv, rank_update, station_rank


def test_csv_columns_and_rows():
    data = (FIXTURES / "2026-09-18" / "mxtemsadext00.csv").read_bytes()
    obs = latest_csv.parse(METRICS["tmax"], data)
    assert len(obs) >= 30
    toyama = next(o for o in obs if o.name == "富山")
    assert toyama.station_id == "55102" and toyama.pref == "富山県"
    assert toyama.obs_date == "2026-09-18" and toyama.prev_alltime.value == 39.8
    assert toyama.prev_monthly.value == 38.3 and toyama.stats_start == 1939
    assert toyama.quality == Quality.NORMAL   # 当日値の 4 は速報として通常扱い
    wakkanai = next(o for o in obs if o.name == "稚内")
    assert wakkanai.pref == "北海道" and wakkanai.pref_full == "北海道宗谷地方"


def test_csv_precip_columns():
    data = (FIXTURES / "2026-09-18" / "pre1h00.csv").read_bytes()
    obs = latest_csv.parse(METRICS["pre1h"], data)
    o = obs[0]
    assert o.prev_alltime is not None and o.prev_alltime.date is not None
    assert o.obs_time is None or ":" in o.obs_time


def test_csv_missing_column_raises():
    with pytest.raises(ParserError):
        latest_csv.parse(METRICS["tmax"], "観測所番号,都道府県,地点\n1,2,3\n".encode("utf-8"))


def test_rank_update_0914():
    html = (FIXTURES / "2026-09-14" / "rank_update_d0914.html").read_text(encoding="utf-8")
    rows = rank_update.parse(html, "2026-09-14")
    by = {(o.metric, o.name): o for o in rows}
    assert len(rows) == 5                                     # 3h/6h は Phase 2 のメトリクス（未登録）
    assert {o.metric for o in rows} == {"pre1h"}
    assert all(o.flag == 9 for o in rows)                  # 9/14 は月別1位のみ
    yanai = by[("pre1h", "柳井")]
    assert yanai.value == 68.0 and yanai.muni == "柳井市" and yanai.pref == "山口県"
    assert yanai.prev_monthly.value == 49.5 and yanai.prev_monthly.date == "2021-09-17"
    assert yanai.stats_start == 1976 and yanai.obs_time == "09:58"
    shuchi = by[("pre1h", "須知")]
    assert "タイ" in shuchi.remark and shuchi.prev_monthly.value == 40.5
    assert ("pre24h", "仁別") not in by and ("preday", "仁別") not in by
    assert by[("pre1h", "仁別")].value == 69.0


def test_rank_update_quiet_day():
    html = (FIXTURES / "2026-09-18" / "rank_update_d0918.html").read_text(encoding="utf-8")
    assert rank_update.parse(html, "2026-09-18") == []


def test_station_rank_amedas_and_month():
    html = (FIXTURES / "2026-09-18" / "rank_a_11_0002.html").read_text(encoding="utf-8")
    p = station_rank.parse(html)
    assert "沓形" in p["station"]
    row = station_rank.find_row(p, "日最高気温の高い方から")
    assert row["entries"][0] == {"rank": 1, "value": 32.5, "date": "1989-08-07", "mark": ""}
    assert row["period"].startswith("1977")
    rain = station_rank.find_row(p, "日降水量")
    assert rain["entries"][1]["value"] == 154.0
    m = station_rank.parse((FIXTURES / "2026-09-18" / "rank_a_11_0002_m09.html").read_text(encoding="utf-8"))
    assert station_rank.find_row(m, "日最高気温の高い方から")["entries"][0]["value"] == 30.4


def test_station_rank_marks_and_errors():
    html = (FIXTURES / "2026-09-18" / "rank_s_11_47401.html").read_text(encoding="utf-8")
    p = station_rank.parse(html)
    days = station_rank.find_row(p, "日最高気温25℃以上年間日数")
    assert days["entries"][8] == {"rank": 9, "value": 22.0, "date": "2026", "mark": "]"}
    with pytest.raises(ParserError):
        station_rank.parse((FIXTURES / "synthetic" / "rank_a_11_9999.html").read_text(encoding="utf-8"))
