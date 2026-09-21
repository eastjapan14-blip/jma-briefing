from conftest import FIXTURES

from record_hunter import events as E
from record_hunter.config import Config
from record_hunter.detector import detect
from record_hunter.enricher import rank_against
from record_hunter.metrics import METRICS
from record_hunter.models import Observation, Quality, Record
from record_hunter.state import default_state


def obs(**kw):
    base = dict(metric="tmax", station_id="1", name="A", pref="X県", obs_date="2026-09-18", value=30.0,
                quality=Quality.NORMAL, prev_alltime=Record(29.0, "1978-08-03"), prev_monthly=Record(28.0, "2010-09-05"))
    base.update(kw)
    return Observation(**base)


def test_detect_alltime_tie_monthly_and_rejects():
    cfg = Config()
    cands = detect([
        obs(station_id="1", flag=13, value=30.0),                      # 1位更新
        obs(station_id="2", flag=13, value=29.0),                      # 1位タイ
        obs(station_id="3", flag=9, value=28.5),                       # 月1位
        obs(station_id="4", value=28.7, prev_monthly=Record(29.5, "2000-09-01")),  # 1位に0.3℃ → enrich のみ
        obs(station_id="5", value=20.0),                               # 何でもない
        obs(station_id="6", flag=13, value=31.0, quality=Quality.INSUFFICIENT),  # 資料不足は却下
        obs(station_id="7", flag=13, value=31.0, quality=Quality.CAUTION),       # 準正常は候補だが通知しない
        obs(station_id="8", metric="tmin", flag=13, value=-5.0, prev_alltime=Record(-4.0, "1990-01-01"),
            prev_monthly=Record(-3.0, "2000-09-01")),                  # 最低気温は小さいほど極端
    ], cfg)
    by = {c.obs.station_id: c for c in cands}
    assert set(by) == {"1", "2", "3", "4", "7", "8"}
    assert by["1"].tags == ["ALL_TIME_1ST", "MONTHLY_1ST"] and by["1"].enrich
    assert by["2"].tags == ["ALL_TIME_1ST_TIE", "MONTHLY_1ST"]
    assert by["3"].tags == ["MONTHLY_1ST"]
    assert by["4"].tags == [] and by["4"].enrich and by["4"].reasons == ["near_alltime"]
    assert by["7"].notifiable is False
    assert by["8"].tags == ["ALL_TIME_1ST", "MONTHLY_1ST"]


def test_merge_severity_margin_age_and_upgrade_only():
    cfg = Config()
    s = default_state()
    c = detect([obs(flag=9, value=28.5)], cfg)[0]
    ev = E.merge(s, c, "t1")
    assert ev["severity"] == "B" and ev["tags"] == ["MONTHLY_1ST"]
    plan = E.plan(s, cfg, "2026-09-18")
    assert len(plan) == 1 and plan[0]["kind"] == "B"
    E.mark_notified(s, plan[0], "t1")
    assert E.plan(s, cfg, "2026-09-18") == []                          # 同じ格なら再通知しない
    c2 = detect([obs(flag=13, value=30.2)], cfg)[0]                    # 月1位 → 観測史上1位に格上げ
    ev = E.merge(s, c2, "t2")
    assert ev["severity"] == "A" and ev["tags"] == ["ALL_TIME_1ST", "MONTHLY_1ST"]
    assert ev["margin_abs"] == 1.2 and ev["record_age_years"] == 48 and ev["margin_pct"] is None
    plan = E.plan(s, cfg, "2026-09-18")
    assert [p["kind"] for p in plan] == ["A"]
    E.mark_notified(s, plan[0], "t2")
    assert E.plan(s, cfg, "2026-09-18") == []


def test_short_stats_caps_at_b_and_cluster():
    cfg = Config()
    s = default_state()
    for sid, flag, short, v in (("1", 13, True, 30.0), ("2", 9, False, 28.5), ("3", 9, False, 28.5)):
        E.merge(s, detect([obs(station_id=sid, flag=flag, short_stats=short, value=v)], cfg)[0], "t")
    assert s["events"]["tmax:1:2026-09-18"]["severity"] == "B"
    E.build_clusters(s, cfg, "2026-09-18")
    assert s["clusters"]["tmax:X県:2026-09-18"]["members"] == ["1", "2", "3"]
    assert "PREFECTURE_CLUSTER" in s["events"]["tmax:2:2026-09-18"]["tags"]
    plan = E.plan(s, cfg, "2026-09-18")
    assert len(plan) == 1 and plan[0]["kind"] == "B" and sorted(plan[0]["new"]) == [
        "tmax:1:2026-09-18", "tmax:2:2026-09-18", "tmax:3:2026-09-18"]
    E.mark_notified(s, plan[0], "t")
    # 4地点目が加わると閾値 4 を跨ぐので再通知
    E.merge(s, detect([obs(station_id="4", flag=9, value=28.5)], cfg)[0], "t2")
    E.build_clusters(s, cfg, "2026-09-18")
    plan = E.plan(s, cfg, "2026-09-18")
    assert len(plan) == 1 and plan[0]["grow"] is True and plan[0]["new"] == ["tmax:4:2026-09-18"]
    E.mark_notified(s, plan[0], "t2")
    assert E.plan(s, cfg, "2026-09-18") == []


def test_a_events_batched_when_many():
    cfg = Config()
    s = default_state()
    for sid in "123":
        E.merge(s, detect([obs(station_id=sid, flag=13)], cfg)[0], "t")
    plan = E.plan(s, cfg, "2026-09-18")
    assert len(plan) == 1 and plan[0]["kind"] == "A" and len(plan[0]["events"]) == 3
    cfg.a_batch_min = 5
    assert len(E.plan(s, cfg, "2026-09-18")) == 3


def test_rank_against_strict_vs_tie():
    m = METRICS["preday"]
    entries = [{"rank": 1, "value": 260.0, "date": "1965-08-01"}, {"rank": 2, "value": 230.0, "date": "1980-09-02"},
               {"rank": 3, "value": 215.0, "date": "1999-07-07"}, {"rank": 4, "value": 200.0, "date": "2026-09-18"}]
    r = rank_against(m, 215.0, entries, "2026-09-18")
    assert r["rank"] == 3 and r["tie"] is True and r["last_stricter_date"] == "1980-09-02" and r["years_since"] == 46
    r = rank_against(METRICS["tmin"], -10.0, [{"rank": 1, "value": -12.0, "date": "1981-01-01"}], "2026-09-18")
    assert r["rank"] == 2 and r["years_since"] == 45
    full = [{"rank": i + 1, "value": 100.0 - i, "date": "2000-01-01"} for i in range(10)]
    assert rank_against(m, 50.0, full, "2026-09-18")["rank"] is None   # 10位圏外
    assert rank_against(m, 100.0, full, "2026-09-18")["rank"] == 1


def test_confirm_marks_revised():
    cfg = Config()
    s = default_state()
    E.merge(s, detect([obs(station_id="1", flag=13, obs_date="2026-09-17")], cfg)[0], "t")
    s["events"]["tmax:1:2026-09-17"]["notified_severity"] = "A"
    E.merge(s, detect([obs(station_id="2", flag=9, value=28.5, obs_date="2026-09-17")], cfg)[0], "t")
    ru = [obs(station_id="2", flag=9, value=28.5, obs_date="2026-09-17", source="rank_update", muni="Y市")]
    revised = E.confirm(s, ru, "2026-09-17")
    assert [e["id"] for e in revised] == ["tmax:1:2026-09-17"]
    assert s["events"]["tmax:2:2026-09-17"]["status"] == "CONFIRMED"
    assert s["events"]["tmax:2:2026-09-17"]["muni"] == "Y市"


def test_plan_includes_yesterday_and_negative_margin_hidden():
    cfg = Config()
    s = default_state()
    ev = E.merge(s, detect([obs(station_id="1", flag=13, obs_date="2026-09-21")], cfg)[0], "t")
    assert [p["kind"] for p in E.plan(s, cfg, "2026-09-22")] == ["A"]   # 日付をまたいでも通知する
    assert E.plan(s, cfg, "2026-09-23") == []
    # 従来値の方が大きい（更新状況ページ由来の1位 vs CSV の長期統計）: 更新幅を出さない
    c = detect([obs(station_id="2", flag=13, value=30.0, prev_alltime=None, source="rank_update")], cfg)[0]
    ev = E.merge(s, c, "t")
    ev["prev"] = {"value": 35.0, "date": "1950-01-01"}
    E.merge(s, c, "t2")
    assert ev["margin_abs"] is None and ev["margin_pct"] is None and ev["tags"] == ["ALL_TIME_1ST", "MONTHLY_1ST"]


def test_enrich_recomputes_severity_and_drops_since_on_upgrade():
    from record_hunter.enricher import enrich
    from record_hunter.sources.stations import Stations
    from record_hunter.http import FixtureFetcher
    from conftest import FIXTURES
    cfg = Config(); cfg.state_dir = FIXTURES.parent / ".tmp_state"
    s = default_state()
    ev = E.merge(s, detect([obs(station_id="11016", value=32.2, flag=None, prev_alltime=Record(32.7, "2021-07-29"),
                                prev_monthly=Record(40.0, "2000-09-01"))], cfg)[0], "t")
    assert ev["severity"] == "NONE" and ev["enrich_pending"]
    enrich([ev], Stations({}, {"11016": {"kind": "s", "prec": "11", "block": "47401"}}),
           FixtureFetcher(FIXTURES / "synthetic"), cfg)
    assert ev["local_rank"] == 2 and "ALL_TIME_TOP3" in ev["tags"] and ev["severity"] == "B"
    assert E._normalize_tags(["ALL_TIME_1ST", "SINCE_2021", "ALL_TIME_TOP3"]) == ["ALL_TIME_1ST"]
    import shutil; shutil.rmtree(cfg.state_dir, ignore_errors=True)
