"""Fixture を使った end-to-end。実網にはアクセスしない。"""
from datetime import date

from conftest import FIXTURES

from record_hunter import state as st
from record_hunter.config import Config
from record_hunter.http import FixtureFetcher
from record_hunter.pipeline import run
from record_hunter.sources.stations import Stations


def _cfg(tmp_path):
    c = Config()
    c.state_dir = tmp_path / "state"
    c.enabled_metrics = ("tmax", "tmin", "pre1h", "pre24h", "preday")
    return c


def test_quiet_day_sends_nothing(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    f = FixtureFetcher(FIXTURES / "2026-09-18")
    r = run(cfg, f, st.default_state(), date(2026, 9, 18), dry=True, stations=Stations({}, {}))
    assert r["candidates"] == 0 and r["notifications"] == 0
    assert "DRY" not in capsys.readouterr().out
    assert (cfg.state_dir / "state.json").exists()


def test_synthetic_records(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    cfg.enabled_metrics = ("tmax",)
    cfg.enable_rank_update = False
    index = {"11016": {"kind": "s", "prec": "11", "block": "47401"}}   # 稚内だけ順位ページあり
    f = FixtureFetcher(FIXTURES / "synthetic")
    s = st.default_state()
    r = run(cfg, f, s, date(2026, 9, 18), dry=True, stations=Stations({}, index))
    out = capsys.readouterr().out
    ev = s["events"]
    toyama, fushiki, uozu = ev["tmax:55102:2026-09-18"], ev["tmax:55091:2026-09-18"], ev["tmax:55056:2026-09-18"]
    assert toyama["severity"] == "A" and toyama["margin_abs"] == 0.9 and toyama["notified_severity"] == "A"
    assert fushiki["tags"][0] == "ALL_TIME_1ST_TIE" and fushiki["severity"] == "B"
    assert uozu["severity"] == "B" and uozu["tags"] == ["MONTHLY_1ST", "PREFECTURE_CLUSTER"]
    assert "tmax:55166:2026-09-18" not in ev                          # 上市は何も無い
    assert "tmax:55151:2026-09-18" not in ev                          # 疑問値は候補にしない
    assert ev["tmax:44132:2026-09-18"]["severity"] == "B"             # 10年未満は A にしない
    wakkanai = ev["tmax:11016:2026-09-18"]
    assert wakkanai["local_rank"] == 2 and wakkanai["years_since"] == 5 and "ALL_TIME_TOP3" in wakkanai["tags"]
    assert "観測史上1位を更新（従来 39.8℃ 2010" in out or "観測史上1位を更新" in out
    assert "観測史上1位タイ" in out and "[記録] 富山 40.7℃ 日最高気温" in out
    assert "富山県内ではほか2地点" in out
    assert r["notifications"] == 4   # 富山(A) + 富山県まとめ(伏木・魚津 B) + 東京(B) + 稚内(B)
    assert sorted(f.requested).count("rank_s_11_47401.html") == 1  # 順位ページは候補地点だけ
    # 2回目: 何も再通知しない、順位ページはキャッシュ
    f2 = FixtureFetcher(FIXTURES / "synthetic")
    s = st.load(cfg.state_dir)
    r2 = run(cfg, f2, s, date(2026, 9, 18), dry=True, stations=Stations({}, index))
    assert r2["notifications"] == 0 and "rank_s_11_47401.html" not in f2.requested


def test_replay_0914_monthly_group(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    cfg.enabled_metrics = ("pre1h",)
    cfg.enable_enrich = False
    table = {"1": {"kjName": "仁別"}, "2": {"kjName": "須知"}, "3": {"kjName": "福渡"}, "4": {"kjName": "柳井"},
             "5": {"kjName": "北原"}}
    f = FixtureFetcher(FIXTURES / "2026-09-14")
    s = st.default_state()
    r = run(cfg, f, s, date(2026, 9, 14), dry=True, stations=Stations(table, {}))
    out = capsys.readouterr().out
    assert r["candidates"] == 5 and r["notifications"] == 5          # 5県それぞれ1通
    assert "9月の1位タイ（2013/9/2 と同値）" in out
    assert "柳井 68.0mm" in out and "従来 49.5mm 2021/9/17" in out
    assert s["events"]["pre1h:4:2026-09-14"]["muni"] == "柳井市"
