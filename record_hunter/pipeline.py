"""1回の実行: 取得 → 正規化 → 判定 → （候補だけ）Enrich → Event/Dedupe → 通知 → 確認 → State 保存。"""
from datetime import date, datetime, timedelta

from . import events as E
from . import notifier
from . import state as st
from .detector import detect
from .enricher import enrich
from .log import log, summary
from .metrics import METRICS, active
from .models import ParserError
from .sources import latest_csv, rank_update
from .sources.stations import Stations


def load_stations(fetcher, cfg) -> Stations:
    cached = st.cache_get(cfg.state_dir, "meta_amedastable", cfg.cache_ttl_days)
    if cached:
        return Stations(cached.get("table", {}))
    s = Stations.load(fetcher)
    if s.table:
        st.cache_put(cfg.state_dir, "meta_amedastable", {"table": s.table})
    return s


def collect_csv(cfg, fetcher, state, today: date) -> list:
    obs = []
    for mid in cfg.enabled_metrics:
        m = METRICS.get(mid)
        if m is None:
            log("fetch", "fetch_skip", metric=mid, reason="unknown_metric")
            continue
        if not active(m, today.month):
            log("fetch", "fetch_skip", metric=mid, reason="off_season")
            continue
        src = state["sources"].setdefault(m.csv_key, {})
        if src.get("last_success"):
            age = (datetime.fromisoformat(st.now_iso()) - datetime.fromisoformat(src["last_success"])).total_seconds() / 60
            if age < m.poll_minutes - 2:
                log("fetch", "fetch_skip", metric=mid, reason="poll_interval", age_min=int(age))
                continue
        if src.get("fail_count", 0) >= 3 and state["runs"] % min(2 ** (src["fail_count"] - 2), 8) != 0:
            log("fetch", "fetch_skip", metric=mid, reason="backoff", fail_count=src["fail_count"])
            continue
        r = fetcher.get(m.csv_url, key=m.csv_key)
        if r.not_modified or not r.ok:
            continue
        try:
            rows = latest_csv.parse(m, r.body)
        except ParserError as e:
            log("parse", "parser_warning", metric=mid, error=str(e), action="halt_metric")
            continue
        if rows:
            t = rows[0].source_time
            if t and t == src.get("source_time"):
                log("fetch", "fetch_skip", metric=mid, reason="same_source_time", t=t)
                continue
            src["source_time"] = t
            src["last_success"] = st.now_iso()
        obs.extend(rows)
    return obs


def collect_rank_update(cfg, fetcher, stations, day: date, provisional: bool = True) -> list:
    url = notifier.rank_update_url(day.isoformat())
    r = fetcher.get(url)
    if not r.ok:
        return []
    try:
        rows = rank_update.parse(r.body.decode("utf-8", errors="replace"), day.isoformat(), provisional)
    except ParserError as e:
        log("parse", "parser_warning", source="rank_update", error=str(e))
        return []
    out = []
    for o in rows:
        o.station_id = stations.find_id(o.name, o.pref)
        if o.station_id:
            out.append(o)
        else:
            log("parse", "parser_warning", source="rank_update", reason="station_unresolved", name=o.name, pref=o.pref)
    return out


def run(cfg, fetcher, state: dict, today: date, dry: bool, stations: Stations = None) -> dict:
    now = st.now_iso()
    state["runs"] = state.get("runs", 0) + 1
    tod = today.isoformat()
    stations = stations or load_stations(fetcher, cfg)

    yday = today - timedelta(days=1)
    obs = collect_csv(cfg, fetcher, state, today)
    stations.register(obs)
    ru_yday = []
    if cfg.enable_rank_update:
        obs += collect_rank_update(cfg, fetcher, stations, today)
        # 前日ページ（確定値）も候補源にする。日降水量など 24 時に確定する記録は当日 CSV に載らない
        ru_yday = collect_rank_update(cfg, fetcher, stations, yday, provisional=False)
        obs += ru_yday

    cands = detect(obs, cfg)
    evs = [E.merge(state, c, now, stations) for c in cands]
    if cfg.enable_enrich:
        pending = [e for e in {e["id"]: e for e in evs}.values() if e.get("enrich_pending")]
        for e in pending:
            st.cache_invalidate(cfg.state_dir, e["station"]) if e.get("severity") == "A" and not e.get("enriched_at") else None
        enrich(pending, stations, fetcher, cfg)
    E.build_clusters(state, cfg, tod)

    sent = 0
    for n in E.plan(state, cfg, tod):
        evs_n = [state["events"][i] for i in n["events"]]
        if len(evs_n) == 1 and not n.get("grow"):
            title, msg, click = notifier.format_single(evs_n[0], cfg, n["cluster_n"], stations)
        else:
            title, msg, click = notifier.format_group(evs_n, n["new"], cfg)
        if notifier.send(cfg, n["kind"], title, msg, click, dry):
            E.mark_notified(state, n, now)
            sent += 1

    if cfg.enable_confirm and ru_yday and yday.isoformat() not in state["confirm_checked"] \
            and any(e["date"] == yday.isoformat() for e in state["events"].values()):
        if True:
            for ev in E.confirm(state, ru_yday, yday.isoformat()):
                title, msg, click = notifier.format_revised(ev, cfg)
                notifier.send(cfg, "R", title, msg, click, dry)
            state["confirm_checked"][yday.isoformat()] = True

    st.prune(state, tod, cfg.prune_days)
    state["last_run"] = now
    st.save(cfg.state_dir, state)
    summary()
    return {"observations": len(obs), "candidates": len(cands), "notifications": sent, "requests": fetcher.count}
