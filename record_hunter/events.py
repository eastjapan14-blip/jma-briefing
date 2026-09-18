"""Event Manager: event_id、State への merge、tags→severity、格上げ時のみ再通知、都道府県クラスター、確認。"""
from collections import defaultdict
from datetime import date, timedelta

from .log import log
from .metrics import METRICS
from .models import sev_gt, sev_max

_A_TAGS = {"ALL_TIME_1ST"}
_B_TAGS = {"ALL_TIME_1ST_TIE", "ALL_TIME_TOP3", "MONTHLY_1ST", "MONTHLY_1ST_TIE", "PREFECTURE_CLUSTER"}
_FAMILY = [("ALL_TIME_1ST", "ALL_TIME_1ST_TIE", "ALL_TIME_TOP3"), ("MONTHLY_1ST", "MONTHLY_1ST_TIE", "MONTHLY_TOP3")]


def event_id(metric: str, station: str, obs_date: str) -> str:
    return f"{metric}:{station}:{obs_date}"


def _normalize_tags(tags) -> list:
    """同じ系統（通年 / 当月）では最も強いタグだけ残す。"""
    s = set(tags)
    for fam in _FAMILY:
        present = [t for t in fam if t in s]
        for t in present[1:]:
            s.discard(t)
    return sorted(s)


def compute_severity(ev: dict) -> str:
    tags = set(ev["tags"])
    sev = "A" if tags & _A_TAGS else ("B" if tags & _B_TAGS else "NONE")
    if "SHORT_STATS" in tags and sev == "A":
        sev = "B"
    ev["severity"] = sev
    return sev


def _years_between(later: str, earlier) -> int:
    return int(later[:4]) - int(str(earlier)[:4])


def merge(state: dict, cand, now: str, stations=None) -> dict:
    o = cand.obs
    m = METRICS[o.metric]
    eid = event_id(o.metric, o.station_id, o.obs_date)
    ev = state["events"].get(eid)
    new = ev is None
    if new:
        ev = {"id": eid, "metric": o.metric, "station": o.station_id, "name": o.name, "pref": o.pref,
              "pref_full": o.pref_full, "muni": None, "date": o.obs_date, "time": None, "value": None,
              "unit": m.unit, "quality": o.quality.value, "short_stats": False, "flag": None,
              "local_rank": None, "local_tie": False, "monthly_rank": None, "monthly_tie": False,
              "prev": None, "prev_monthly": None, "record_age_years": None, "margin_abs": None,
              "margin_pct": None, "top3": [], "last_stricter_date": None, "years_since": None,
              "stats_start": None, "stats_period": None, "tags": [], "severity": "NONE", "notifiable": True,
              "notified_severity": "NONE", "notify_count": 0, "notified_at": None, "status": "PROVISIONAL",
              "first_seen": now, "last_seen": now, "enriched_at": None, "enrich_pending": False,
              "source_ref": None, "sources": [], "remark": ""}
        if stations:
            ev.update(stations.meta(o.station_id))
        state["events"][eid] = ev
    value_changed = o.value is not None and o.value != ev["value"]
    if o.value is not None and (ev["value"] is None or value_changed):
        ev["value"] = o.value
    ev["last_seen"] = now
    if o.obs_time:
        ev["time"] = o.obs_time
    if o.muni:
        ev["muni"] = o.muni
    if o.source == "csv":
        ev["quality"] = o.quality.value
        ev["notifiable"] = cand.notifiable
    elif ev["quality"] == "NORMAL" and not cand.notifiable:
        ev["notifiable"] = False
    if o.short_stats:
        ev["short_stats"] = True
    if o.flag:
        ev["flag"] = max(ev["flag"] or 0, o.flag)
    if o.stats_start:
        ev["stats_start"] = o.stats_start
    if o.remark:
        ev["remark"] = o.remark
    if o.prev_alltime and o.prev_alltime.value is not None and (ev["prev"] is None or o.source == "csv"):
        ev["prev"] = o.prev_alltime.to_dict()
    if o.prev_monthly and o.prev_monthly.value is not None and (ev["prev_monthly"] is None or o.source == "csv"):
        ev["prev_monthly"] = o.prev_monthly.to_dict()
    if o.source not in ev["sources"]:
        ev["sources"].append(o.source)
    ev["tags"] = _normalize_tags(ev["tags"] + cand.tags)
    # 記録年齢・更新幅（観測史上1位のとき）
    prev = ev["prev"]
    if prev and prev.get("value") is not None and ev["value"] is not None:
        diff = ev["value"] - prev["value"] if m.comparator == "max" else prev["value"] - ev["value"]
        ev["margin_abs"] = round(diff, m.decimals)
        ev["margin_pct"] = round(diff / prev["value"] * 100, 1) if m.percent_meaningful and prev["value"] > 0 else None
        ev["record_age_years"] = _years_between(ev["date"], prev["date"]) if prev.get("date") else None
    if cand.enrich and (new or value_changed or ev["enriched_at"] is None):
        ev["enrich_pending"] = True
    compute_severity(ev)
    if not new:
        log("event", "update", id=eid, value=ev["value"], sev=ev["severity"], tags=",".join(ev["tags"]))
    else:
        log("event", "new", id=eid, value=ev["value"], sev=ev["severity"], tags=",".join(ev["tags"]))
    return ev


def _groups(state: dict, today: str):
    g = defaultdict(list)
    for ev in state["events"].values():
        if ev["date"] == today and ev["notifiable"] and ev["severity"] in ("A", "B"):
            g[(ev["metric"], ev["pref"], ev["date"])].append(ev)
    return g


def build_clusters(state: dict, cfg, today: str):
    for (metric, pref, d), evs in _groups(state, today).items():
        if len(evs) < cfg.cluster_min:
            continue
        cid = f"{metric}:{pref}:{d}"
        c = state["clusters"].setdefault(cid, {"metric": metric, "pref": pref, "date": d, "members": [],
                                               "notified_members": 0, "notified_at": None})
        c["members"] = sorted(e["station"] for e in evs)
        for e in evs:
            if "PREFECTURE_CLUSTER" not in e["tags"]:
                e["tags"] = sorted(set(e["tags"]) | {"PREFECTURE_CLUSTER"})
                compute_severity(e)


def plan(state: dict, cfg, today: str) -> list:
    """通知計画。A は個別、B は（都道府県, 要素）ごとにまとめる。格上げ時のみ。"""
    out = []
    groups = _groups(state, today)
    for (metric, pref, d), evs in sorted(groups.items()):
        cid = f"{metric}:{pref}:{d}"
        cluster = state["clusters"].get(cid)
        for e in evs:
            if e["severity"] == "A" and "A" in cfg.notify_levels and sev_gt("A", e["notified_severity"]):
                out.append({"kind": "A", "events": [e["id"]], "new": [e["id"]], "metric": metric, "pref": pref,
                            "date": d, "cluster_n": len(evs) if cluster else 0})
            elif e["severity"] == "A" and sev_gt("A", e["notified_severity"]):
                log("notify", "notify_suppressed", id=e["id"], reason="level_disabled")
        b = [e for e in evs if e["severity"] == "B"]
        new_b = [e["id"] for e in b if sev_gt("B", e["notified_severity"])]
        grow = False
        if cluster and cluster["notified_members"]:
            grow = any(cluster["notified_members"] < s <= len(evs) for s in cfg.cluster_steps)
        if "B" not in cfg.notify_levels:
            for i in new_b:
                log("notify", "notify_suppressed", id=i, reason="level_disabled")
            continue
        if new_b or grow:
            out.append({"kind": "B", "events": [e["id"] for e in b] or [e["id"] for e in evs], "new": new_b,
                        "metric": metric, "pref": pref, "date": d, "cluster_n": len(evs) if cluster else 0,
                        "grow": grow})
        else:
            for e in b:
                log("notify", "dedupe", id=e["id"], reason="already_notified", sev=e["severity"])
    return out


def mark_notified(state: dict, n: dict, now: str):
    for eid in n["events"]:
        ev = state["events"][eid]
        ev["notified_severity"] = sev_max(ev["notified_severity"], ev["severity"])
        ev["notified_at"] = now
        if eid in n["new"]:
            ev["notify_count"] += 1
    cid = f'{n["metric"]}:{n["pref"]}:{n["date"]}'
    if cid in state["clusters"]:
        state["clusters"][cid]["notified_members"] = len(state["clusters"][cid]["members"])
        state["clusters"][cid]["notified_at"] = now


def confirm(state: dict, ru_obs: list, yday: str) -> list:
    """前日の更新状況ページと突き合わせ。載っていれば CONFIRMED、1位のはずが無ければ REVISED。"""
    present = {}
    for o in ru_obs:
        if o.station_id:
            present.setdefault((o.metric, o.station_id), set()).add("alltime" if o.flag == 13 else "monthly")
            if o.muni:
                present.setdefault(("muni", o.station_id), o.muni)
    revised = []
    for ev in state["events"].values():
        if ev["date"] != yday or ev["status"] != "PROVISIONAL":
            continue
        secs = present.get((ev["metric"], ev["station"]), set())
        tags = set(ev["tags"])
        want_alltime = bool(tags & {"ALL_TIME_1ST", "ALL_TIME_1ST_TIE"})
        want_monthly = bool(tags & {"MONTHLY_1ST", "MONTHLY_1ST_TIE"})
        if (want_alltime and "alltime" not in secs) or (want_monthly and not secs):
            ev["status"] = "REVISED"
            log("confirm", "revision", id=ev["id"], sev=ev["severity"], notified=ev["notified_severity"])
            if ev["notified_severity"] != "NONE":
                revised.append(ev)
        elif secs:
            ev["status"] = "CONFIRMED"
            ev["muni"] = ev["muni"] or present.get(("muni", ev["station"]))
    return revised
