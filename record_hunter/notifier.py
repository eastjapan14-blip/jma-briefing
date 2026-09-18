"""通知文面と ntfy 送信。文章を過度に自動生成しない。数字・順位・年代・公式リンクを優先する。

ntfy の POST は scripts/notify.py の publish() と同じ JSON 形式（title/message/priority/tags/click）。
既存トピックを共用するので、タイトル先頭に [記録] を付けて区別する。
"""
import json
import urllib.request

from .log import log
from .metrics import METRICS, fmt

RANK_UPDATE = "https://www.data.jma.go.jp/stats/data/mdrr/rank_update"
PRIORITY = {"A": 4, "B": 3, "R": 3}
TAGS = {"A": ["trophy"], "B": ["bar_chart"], "R": ["warning"]}


def _d(iso):
    """"1978-08-03" → "1978/8/3"（原文どおりの起日表記に寄せる）"""
    if not iso:
        return "?"
    p = iso.split("-")
    return "/".join(str(int(x)) for x in p)


def rank_update_url(obs_date: str) -> str:
    return f"{RANK_UPDATE}/d{obs_date[5:7]}{obs_date[8:10]}.html"


def describe(ev: dict, cfg) -> list:
    """1イベントの本文行。順位 → 従来記録 → 更新幅/記録年齢 → TOP3/○年以来 → 注記。"""
    m = METRICS[ev["metric"]]
    tags = set(ev["tags"])
    month = int(ev["date"][5:7])
    L = []
    prev, pm = ev.get("prev") or {}, ev.get("prev_monthly") or {}
    v = lambda x: f"{fmt(m, x)}{m.unit}"
    if "ALL_TIME_1ST" in tags:
        L.append(f"観測史上1位を更新（従来 {v(prev.get('value'))} {_d(prev.get('date'))}）" if prev else "観測史上1位を更新")
        if ev.get("margin_abs") is not None:
            s = f"従来記録を{fmt(m, ev['margin_abs'])}{m.unit}上回る"
            if ev.get("margin_pct") is not None:
                s += f"（+{ev['margin_pct']}%）"
            if ev.get("record_age_years") and ev["record_age_years"] >= 2:
                s += f"、{ev['record_age_years']}年ぶりの更新"
            L.append(s)
    elif "ALL_TIME_1ST_TIE" in tags:
        L.append(f"観測史上1位タイ（{_d(prev.get('date'))} と同値）" if prev else "観測史上1位タイ")
    elif ev.get("local_rank") and ev["local_rank"] <= cfg.rank_threshold:
        L.append(f"観測史上{ev['local_rank']}位" + ("タイ" if ev.get("local_tie") else ""))
    if "MONTHLY_1ST" in tags and "ALL_TIME_1ST" not in tags:
        L.append(f"{month}月の1位を更新（従来 {v(pm.get('value'))} {_d(pm.get('date'))}）" if pm else f"{month}月の1位を更新")
    elif "MONTHLY_1ST_TIE" in tags:
        L.append(f"{month}月の1位タイ（{_d(pm.get('date'))} と同値）" if pm else f"{month}月の1位タイ")
    elif "MONTHLY_1ST" in tags:
        L.append(f"{month}月の1位も更新")
    if ev.get("local_rank") and ev["local_rank"] >= 2 and ev.get("top3"):
        for r, val, d in ev["top3"]:
            if r < ev["local_rank"]:
                L.append(f" {r}位 {v(val)}（{_d(d)}）")
        if ev.get("years_since"):
            L.append(f"→ これを上回る値は{ev['last_stricter_date'][:4]}年以来{ev['years_since']}年ぶり")
    if ev.get("stats_start"):
        L.append(f"統計開始 {ev['stats_start']}年" + ("（10年未満）" if ev.get("short_stats") else ""))
    return L


def format_single(ev: dict, cfg, cluster_n: int = 0, stations=None):
    m = METRICS[ev["metric"]]
    val = f"{fmt(m, ev['value'])}{m.unit}"
    title = f"[記録] {ev['name']} {val} {m.label}"
    head = f"{m.emoji} {ev['pref']}{('・' + ev['muni']) if ev.get('muni') else ''} {ev['name']} {m.label} {val}"
    if ev.get("time"):
        head += f"（{ev['time']}）"
    L = [head] + describe(ev, cfg)
    if cluster_n >= 2:
        L.append(f"{ev['pref']}内ではほか{cluster_n - 1}地点も{m.label}が記録級")
    L.append("※速報値")
    click = ev.get("source_ref") or (stations.rank_url(ev["station"], int(ev["date"][5:7])) if stations else None) \
        or rank_update_url(ev["date"])
    return title, "\n".join(L), click


def format_group(events: list, new_ids: list, cfg):
    m = METRICS[events[0]["metric"]]
    pref, d = events[0]["pref"], events[0]["date"]
    month = int(d[5:7])
    kind = "観測史上1位級" if any("ALL_TIME" in t for e in events for t in e["tags"]) else f"{month}月1位級"
    title = f"[記録] {pref} {m.label} {len(events)}地点が{kind}"
    L = [f"{m.emoji} {pref} {m.label}（{_d(d)}）"]
    for e in sorted(events, key=lambda e: (e["id"] not in new_ids, e["name"]))[:cfg.max_group_lines]:
        tag = ("★" if e["id"] in new_ids else "・")
        L.append(f"{tag}{e['name']} {fmt(m, e['value'])}{m.unit}")
        for line in describe(e, cfg)[:2]:
            L.append(f"   {line}")
    if len(events) > cfg.max_group_lines:
        L.append(f"…ほか{len(events) - cfg.max_group_lines}地点")
    L.append("※速報値（★=新規）")
    return title, "\n".join(L), rank_update_url(d)


def format_revised(ev: dict, cfg):
    m = METRICS[ev["metric"]]
    title = f"[記録・訂正] {ev['name']} {m.label}"
    msg = (f"{_d(ev['date'])} の {ev['name']} {fmt(m, ev['value'])}{m.unit} は、翌日の気象庁「更新状況」に"
           f"1位更新として載っていません。値が修正された可能性があります。")
    return title, msg, rank_update_url(ev["date"])


def send(cfg, kind: str, title: str, message: str, click: str, dry: bool) -> bool:
    if dry or not cfg.ntfy_topic:
        print(f"DRY [{kind}] {title}\n{message}\n  → {click}\n")
        log("notify", "notify_dry", kind=kind, title=title)
        return dry  # dry-run は「送った」扱いで State を進める。トピック未設定は失敗扱い
    payload = {"topic": cfg.ntfy_topic, "title": title, "message": message, "priority": PRIORITY[kind],
               "tags": TAGS[kind], "click": click}
    req = urllib.request.Request(cfg.ntfy_server, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": cfg.user_agent})
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as r:
            ok = 200 <= r.status < 300
    except Exception as e:  # ntfy 失敗時はイベントを通知済みにしない
        log("notify", "notify_fail", kind=kind, title=title, error=str(e)[:100])
        return False
    log("notify", "notify_sent" if ok else "notify_fail", kind=kind, title=title)
    return ok
