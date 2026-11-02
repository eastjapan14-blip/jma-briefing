"""珍しさの説明（rarity.py）と、前日分の照合（confirm）の修正のテスト。"""
from record_hunter import events as E
from record_hunter import rarity
from record_hunter.models import Observation, Quality
from record_hunter.sources import rank_update


def ev(**kw):
    e = {"id": "x", "metric": "pre1h", "date": "2026-11-02", "pref": "山形県", "station": "1", "name": "A",
         "tags": ["MONTHLY_1ST"], "short_stats": False, "stats_start": 1978, "value": 27.0,
         "prev_monthly": {"value": 23.5, "date": "2009-11-14"}, "status": "PROVISIONAL", "severity": "B", "notified_severity": "B"}
    e.update(kw)
    return e


def test_short_stats_is_not_rare():
    e = ev(tags=["MONTHLY_1ST", "SHORT_STATS"], short_stats=True, stats_start=2026, prev_monthly={"value": 6.0, "date": "2026-11-01"})
    lines = rarity.explain(e, {})
    assert "珍しくない" in lines[0]
    assert any("統計1年目" in l for l in lines)
    assert any("前日に出た記録" in l for l in lines)


def test_long_record_and_old_previous_is_very_rare():
    lines = rarity.explain(ev(local_rank=4), {})
    assert "とても珍しい" in lines[0]
    assert any("統計49年（1978年〜）の11月で最大" in l for l in lines)
    assert any("17年ぶりの更新" in l for l in lines)


def test_alltime_tie_wording():
    e = ev(tags=["ALL_TIME_1ST_TIE"], prev={"value": 27.0, "date": "1999-08-01"})
    lines = rarity.explain(e, {})
    assert any("観測史上最大タイ" in l for l in lines)
    assert any("27.0mmに並ぶ" in l for l in lines)


def test_same_day_count():
    a, b = ev(), ev(id="y", station="2", pref="山形県")
    c = ev(id="z", station="3", pref="宮城県", status="REVISED")
    assert rarity.same_day({"events": {"x": a, "y": b, "z": c}}, a) == (1, 1)


def test_confirm_skips_short_stats_stations():
    # 更新状況ページは統計10年目以降の地点だけが対象。載っていなくても訂正にしない
    short = ev(tags=["MONTHLY_1ST", "SHORT_STATS"], short_stats=True, date="2026-11-01")
    long = ev(id="y", station="2", date="2026-11-01")
    page = [Observation(metric="pre1h", station_id="9", name="B", pref="新潟県", obs_date="2026-11-01",
                        value=30.0, quality=Quality.NORMAL,
                        flag=11, source="rank_update")]
    state = {"events": {"x": short, "y": long}}
    revised = E.confirm(state, page, "2026-11-01")
    assert short["status"] == "UNLISTED"
    assert long["status"] == "REVISED" and revised == [long]


def test_page_final_marker():
    head = "<h1>観測史上１位の値 更新状況 （ 11月2日 ） 13時20分現在</h1>11月2日に…した地点の一覧です"
    assert not rank_update.is_final(head)
    assert rank_update.is_final(head.replace("13時20分現在", ""))
