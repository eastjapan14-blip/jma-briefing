"""Shorts 候補の判定（record_hunter/shorts.py）。2026-09-28 に人が下した判断を固定する。"""
from record_hunter import shorts
from record_hunter.notifier import format_single
from record_hunter.config import Config


def ev(**kw):
    base = {"id": "pre1h:0:2026-09-28", "metric": "pre1h", "station": "0", "date": "2026-09-28", "pref": "x",
            "name": "x", "value": 50.0, "tags": [], "severity": "B", "notifiable": True, "short_stats": False}
    base.update(kw)
    base["id"] = f"{base['metric']}:{base['station']}:{base['date']}"
    return base


# 呉: 9月の1位（従来 1924年）、通年4位、単独 → ◎
KURE = ev(station="67511", name="呉", pref="広島県", value=68.0, latitude=34.24, longitude=132.55,
          tags=["MONTHLY_1ST", "SINCE_2009"], local_rank=4, prev_monthly={"date": "1924-09-12", "value": 67.1})
# 上ノ国 石崎: 9月の1位（従来 2023年）、通年4位タイ、単独 → ×
ISHIZAKI = ev(station="24236", name="石崎", pref="北海道", value=47.5, latitude=41.7, longitude=140.0283,
              tags=["MONTHLY_1ST", "SINCE_2025"], local_rank=4, local_tie=True,
              prev_monthly={"date": "2023-09-12", "value": 41.0})


def test_kure_is_a_pick():
    j = shorts.judge(KURE, 1)
    assert j["grade"] == "◎"
    assert j["hook"] == "102年ぶり 9月の1位"
    assert "導入→順位→天気図" in j["plan"]


def test_kaminokuni_is_skipped():
    j = shorts.judge(ISHIZAKI, 1)
    assert j["grade"] == "×"
    assert "従来記録は3年前" in j["why"] and "単独地点" in j["why"]


def test_all_time_cluster_uses_map():
    e = ev(metric="preday", tags=["ALL_TIME_1ST"], prev={"date": "1996-09-22", "value": 321.0})
    j = shorts.judge(e, 7)
    assert j["grade"] == "◎" and "地図" in j["plan"]


def test_nearby_crosses_prefectures_and_groups():
    a = ev(station="1", name="大牟田", pref="福岡県", latitude=33.03, longitude=130.45, date="2026-09-27",
           value=71.0, tags=["MONTHLY_1ST"], prev_monthly={"date": "1999-09-24", "value": 60.0})
    b = ev(station="2", name="鹿北", pref="熊本県", latitude=33.12, longitude=130.72, date="2026-09-27",
           value=51.5, tags=["MONTHLY_1ST"], prev_monthly={"date": "1979-09-01", "value": 50.0})
    far = ev(station="3", name="呉", pref="広島県", latitude=34.24, longitude=132.55, date="2026-09-27",
             tags=["MONTHLY_1ST"])
    state = {"events": {e["id"]: e for e in (a, b, far)}}
    assert shorts.nearby(state, a) == 2
    rows = shorts.candidates(state, {"2026-09-27"})
    names = [r["event"]["name"] for r in rows]
    assert "呉" in names and len(rows) == 2          # 大牟田と鹿北は1件にまとまる
    host = next(r for r in rows if r["event"]["name"] != "呉")
    assert [x["name"] for x in host["near"]] in (["大牟田"], ["鹿北"])


def test_notification_has_shorts_line():
    state = {"events": {KURE["id"]: KURE}}
    _, msg, _ = format_single(dict(KURE, time="05:49", stats_start=1920), Config.from_env(), 0, None, state)
    assert "🎬 Shorts ◎ 9月の1位・通年4位・102年ぶり・単独地点" in msg
