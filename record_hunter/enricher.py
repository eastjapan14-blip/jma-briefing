"""候補地点だけ順位ページを取得し（Sparse Cache）、歴代順位・TOP3・「○年以来」を付ける。

全地点の順位表を常時把握しようとしない。1実行あたり cfg.max_enrich 件まで、直列、間隔つき。
"""
from datetime import date

from . import state as st
from .log import log
from .metrics import METRICS, cmp
from .models import ParserError
from .events import compute_severity
from .sources import station_rank


def rank_against(m, value: float, entries: list, obs_date: str) -> dict:
    """value を順位表（最大10件）に当てて順位・タイ・上回る最新起日を求める。
    起日が観測日と同じエントリは除外する（速報値が既に表に載っている場合）。"""
    valid = [e for e in entries if e.get("value") is not None and (e.get("date") or "") != obs_date]
    if not valid:
        return {"rank": None, "tie": False, "last_stricter_date": None, "years_since": None, "top": []}
    stricter = [e for e in valid if cmp(m, e["value"], value) > 0]
    tie = any(cmp(m, e["value"], value) == 0 for e in valid)
    full = len(entries) >= 10 and len(valid) >= 10
    rank = None if (full and len(stricter) >= len(valid)) else len(stricter) + 1
    last = max((e["date"] for e in stricter if e.get("date")), default=None)
    years = None
    if last:
        years = int(obs_date[:4]) - int(last[:4])
    return {"rank": rank, "tie": tie, "last_stricter_date": last, "years_since": years,
            "top": [[e["rank"], e["value"], e["date"]] for e in valid[:3]]}


def _page(fetcher, stations, cfg, sid, month):
    name = f"{sid}_m{month:02d}" if month else sid
    cached = st.cache_get(cfg.state_dir, name, cfg.cache_ttl_days)
    if cached:
        log("enrich", "cache_hit", station=sid, month=month or 0)
        return cached
    log("enrich", "cache_miss", station=sid, month=month or 0)
    url = stations.rank_url(sid, month)
    r = fetcher.get(url)
    if not r.ok:
        return None
    try:
        parsed = station_rank.parse(r.body.decode("utf-8", errors="replace"))
    except ParserError as e:
        log("enrich", "parser_warning", station=sid, error=str(e))
        return None
    parsed["url"] = url
    st.cache_put(cfg.state_dir, name, parsed)
    return parsed


def enrich(events: list, stations, fetcher, cfg, budget=None) -> int:
    budget = cfg.max_enrich if budget is None else budget
    done = 0
    for ev in events:
        if not ev.get("enrich_pending"):
            continue
        m = METRICS[ev["metric"]]
        sid = ev["station"]
        if not m.rank_row or not stations.etrn(sid):
            log("enrich", "skip", station=sid, reason="no_index" if m.rank_row else "no_rank_row")
            ev["enrich_pending"] = False
            continue
        if done >= budget:
            log("enrich", "deferred", station=sid, reason="budget")
            continue
        done += 1
        month = int(ev["date"][5:7])
        year_page = _page(fetcher, stations, cfg, sid, None)
        month_page = _page(fetcher, stations, cfg, sid, month)
        ev["enrich_pending"] = False
        tags = set(ev["tags"])
        if year_page:
            row = station_rank.find_row(year_page, m.rank_row)
            if row:
                r = rank_against(m, ev["value"], row["entries"], ev["date"])
                ev.update(local_rank=r["rank"], local_tie=r["tie"], top3=r["top"],
                          last_stricter_date=r["last_stricter_date"], years_since=r["years_since"],
                          stats_period=row.get("period"))
                if r["rank"] == 1 and not tags & {"ALL_TIME_1ST", "ALL_TIME_1ST_TIE"}:
                    tags.add("ALL_TIME_1ST_TIE" if r["tie"] else "ALL_TIME_1ST")
                elif r["rank"] and 2 <= r["rank"] <= cfg.rank_threshold:
                    tags.add("ALL_TIME_TOP3")
                if r["years_since"] and r["rank"] and r["rank"] >= 2:
                    tags.add(f"SINCE_{r['last_stricter_date'][:4]}")
            ev["source_ref"] = year_page.get("url") or ev.get("source_ref")
        if month_page:
            row = station_rank.find_row(month_page, m.rank_row)
            if row:
                r = rank_against(m, ev["value"], row["entries"], ev["date"])
                ev.update(monthly_rank=r["rank"], monthly_tie=r["tie"], monthly_top3=r["top"],
                          monthly_years_since=r["years_since"], monthly_last_stricter_date=r["last_stricter_date"])
                if r["rank"] == 1 and not tags & {"MONTHLY_1ST", "MONTHLY_1ST_TIE"}:
                    tags.add("MONTHLY_1ST_TIE" if r["tie"] else "MONTHLY_1ST")
                elif r["rank"] and 2 <= r["rank"] <= cfg.rank_threshold:
                    tags.add("MONTHLY_TOP3")
        ev["tags"] = sorted(tags)
        compute_severity(ev)
        ev["enriched_at"] = st.now_iso()
        log("enrich", "done", station=sid, metric=m.id, local_rank=ev.get("local_rank"),
            monthly_rank=ev.get("monthly_rank"), years_since=ev.get("years_since"))
    return done
