"""Observation → Candidate。判定はすべてコードで確定させる（AIは使わない）。

候補になる条件（どれか）:
  極値更新フラグ 13            → ALL_TIME_1ST（従来1位と同値なら ALL_TIME_1ST_TIE）
  極値更新フラグ 1–12          → MONTHLY_1ST（同値なら MONTHLY_1ST_TIE）
  フラグ無しでも従来1位以上     → 同上（CSV の従来値は前日までなので、当日更新後のラグを吸収）
  従来1位に near 以内          → タグ無し。順位ページで歴代TOP3か確認する（enrich）
却下: 欠測・資料不足・季節外。準正常は候補にするが通知しない（quality_reject）。
"""
from .log import log
from .metrics import METRICS, active, cmp, near
from .models import Candidate, Quality


def _rank_tags(m, value, rec, one, tie):
    if rec is None or rec.value is None:
        return []
    c = cmp(m, value, rec.value)
    if c > 0:
        return [one]
    if c == 0:
        return [tie]
    return []


def detect(obs_list, cfg) -> list:
    out = []
    for o in obs_list:
        m = METRICS.get(o.metric)
        if m is None:
            continue
        if not active(m, int(o.obs_date[5:7])):
            log("detect", "reject", reason="season", metric=o.metric, station=o.station_id)
            continue
        if o.value is None or o.quality == Quality.MISSING:
            continue
        if o.quality == Quality.INSUFFICIENT:
            if o.flag:
                log("detect", "quality_reject", reason="insufficient", metric=o.metric, station=o.station_id,
                    name=o.name, value=o.value)
            continue
        tags = []
        if o.flag == 13 or o.prev_alltime:
            t = _rank_tags(m, o.value, o.prev_alltime, "ALL_TIME_1ST", "ALL_TIME_1ST_TIE")
            if not t and o.flag == 13 and o.prev_alltime is None:
                t = ["ALL_TIME_1ST"]   # フラグはあるが従来値が無い: 気象庁の判定を信じる
            tags += t
        if (o.flag and 1 <= o.flag <= 12) or o.prev_monthly:
            t = _rank_tags(m, o.value, o.prev_monthly, "MONTHLY_1ST", "MONTHLY_1ST_TIE")
            if not t and o.flag and 1 <= o.flag <= 12 and o.prev_monthly is None:
                t = ["MONTHLY_1ST"]
            tags += t
        if "ALL_TIME_1ST" in tags and o.prev_monthly is None and "MONTHLY_1ST" not in tags:
            tags.append("MONTHLY_1ST")   # 観測史上1位なら当月1位でもある
        if o.remark and "タイ" in o.remark:
            tags = [t if t.endswith("_TIE") else t + "_TIE" for t in tags if t in ("ALL_TIME_1ST", "MONTHLY_1ST")] \
                + [t for t in tags if t not in ("ALL_TIME_1ST", "MONTHLY_1ST")]
        if o.short_stats:
            tags.append("SHORT_STATS")
        enrich = False
        if m.rank_row and o.prev_alltime and o.prev_alltime.value is not None:
            enrich = bool(tags) or near(m, o.value, o.prev_alltime.value)
        if not tags and not enrich:
            continue
        notifiable = o.quality == Quality.NORMAL
        if not notifiable:
            log("detect", "quality_reject", reason="caution", metric=o.metric, station=o.station_id, name=o.name,
                value=o.value, tags=",".join(tags))
        reasons = ["near_alltime"] if enrich and not tags else []
        log("detect", "candidate", metric=o.metric, station=o.station_id, name=o.name, value=o.value,
            tags=",".join(tags) or "-", enrich=int(enrich), src=o.source)
        out.append(Candidate(o, sorted(set(tags)), notifiable, enrich, reasons))
    return out
