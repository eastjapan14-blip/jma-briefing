"""Shorts 候補の判定。通知に1行足し、`python3 -m record_hunter shorts` で一覧にする。

判定は3つの材料の点数で決める（State にある値だけを使い、新しい取得はしない）。
  記録の種類: 観測史上1位 +3 ／ 1位タイ +1 ／ 月の1位 +1（通年でも5位以内なら さらに +1）
  従来記録からの年数: 50年以上 +2 ／ 20年以上 +1 ／ 5年未満 -1
  同じ日に記録級（要素は問わない）の地点が半径 150km 内に: 3地点以上 +2（地図の場面が成立）／ 2地点 +1
    県境で切らないのは、九州北部のように県をまたいで広がる日を拾うため。座標が無いイベントは同じ県で数える
  統計10年未満: -2
  ◎ 4点以上（作る）／ ○ 2〜3点（ほかに無ければ）／ × 1点以下（見送り）
"""
import math

from .metrics import METRICS, fmt

GRADES = [(4, "◎"), (2, "○")]
NEAR_KM = 150


def _km(a: dict, b: dict) -> float:
    p1, p2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dl = math.radians(b["longitude"] - a["longitude"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def _live(state: dict, dates) -> list:
    return [e for e in state.get("events", {}).values()
            if e.get("date") in dates and e.get("notifiable", True) and e.get("severity") in ("A", "B")]


def nearby(state: dict, ev: dict, km: float = NEAR_KM) -> int:
    """同じ日に記録級のイベントがある地点の数（自分を含む、要素は問わない）。"""
    near = set()
    for e in _live(state, {ev["date"]}):
        if ev.get("latitude") is not None and e.get("latitude") is not None:
            ok = _km(ev, e) <= km
        else:
            ok = e.get("pref") == ev.get("pref")
        if ok:
            near.add(e["station"])
    return max(len(near), 1)


def _age(ev: dict, monthly: bool):
    prev = (ev.get("prev_monthly") if monthly else ev.get("prev")) or {}
    d = prev.get("date")
    if not d:
        return None
    return int(ev["date"][:4]) - int(str(d)[:4])


def judge(ev: dict, cluster_n: int = 1) -> dict:
    """1イベントの判定。cluster_n は nearby() の地点数（自分を含む）。"""
    tags = set(ev.get("tags", []))
    month = int(ev["date"][5:7])
    score, why = 0, []
    monthly = False
    if "ALL_TIME_1ST" in tags:
        score += 3
        kind = "観測史上1位"
    elif "ALL_TIME_1ST_TIE" in tags:
        score += 1
        kind = "観測史上1位タイ"
    elif "MONTHLY_1ST" in tags or "MONTHLY_1ST_TIE" in tags:
        monthly = True
        tie = "MONTHLY_1ST_TIE" in tags
        score += 0 if tie else 1
        kind = f"{month}月の1位" + ("タイ" if tie else "")
    else:
        kind = f"観測史上{ev.get('local_rank')}位" if ev.get("local_rank") else "記録級"
    why.append(kind)
    rank = ev.get("local_rank")
    if monthly and rank and rank <= 5:
        score += 1
        why.append(f"通年{rank}位")
    elif monthly:
        why[-1] += "のみ"
    age = _age(ev, monthly)
    if age is not None:
        if age >= 50:
            score += 2
        elif age >= 20:
            score += 1
        elif age < 5:
            score -= 1
        why.append(f"{age}年ぶり" if age >= 5 else f"従来記録は{age}年前")
    n = max(cluster_n, 1)
    if n >= 3:
        score += 2
        why.append(f"周辺{NEAR_KM}kmで{n}地点")
    elif n == 2:
        score += 1
        why.append(f"周辺{NEAR_KM}kmで2地点")
    else:
        why.append("単独地点")
    if ev.get("short_stats"):
        score -= 2
        why.append("統計10年未満")
    grade = next((g for s, g in GRADES if score >= s), "×")
    m = METRICS[ev["metric"]]
    hook = (f"{age}年ぶり " if age and age >= 20 else "") + kind
    plan = "導入→順位→地図→CTA" if n >= 3 else "導入→順位→天気図→階級→CTA"
    return {"grade": grade, "score": score, "why": why, "hook": hook, "plan": plan,
            "value": f"{fmt(m, ev['value'])}{m.unit}", "label": m.label}


def line(j: dict) -> str:
    """通知に足す1行。"""
    return f"🎬 Shorts {j['grade']} " + "・".join(j["why"])


def best(events: list, state: dict) -> tuple:
    """まとめ通知用: いちばん点の高いイベントとその判定。"""
    js = [(judge(e, nearby(state, e)), e) for e in events]
    return max(js, key=lambda x: x[0]["score"])


def candidates(state: dict, dates: set) -> list:
    """State から指定日の候補を判定し、地点ごとに最も点の高い要素へまとめて、点の高い順に返す。
    返り値: [{"judge", "event", "others": 同じ地点のほかの要素, "near": 同じ日に周辺で記録級だった地点のイベント}]"""
    per = {}
    for e in _live(state, dates):
        j = judge(e, nearby(state, e))
        per.setdefault((e["station"], e["date"]), []).append((j, e))
    tops = []
    for rows in per.values():
        rows.sort(key=lambda x: -x[0]["score"])
        j, e = rows[0]
        tops.append({"judge": j, "event": e, "others": [METRICS[x["metric"]].label for _, x in rows[1:]], "near": []})
    tops.sort(key=lambda x: (-x["judge"]["score"], -(x["event"]["value"] or 0)))
    # 同じ日・半径 NEAR_KM 内の地点は、点の高い（同点なら値の大きい）地点にまとめる。1つの気象現象を1件として見せる
    out = []
    for t in tops:
        e = t["event"]
        host = next((o for o in out if o["event"]["date"] == e["date"] and _close(o["event"], e)), None)
        if host:
            host["near"].append(e)
        else:
            out.append(t)
    return sorted(out, key=lambda x: (-x["judge"]["score"], x["event"]["date"], x["event"]["pref"], x["event"]["name"]))


def _close(a: dict, b: dict) -> bool:
    if a.get("latitude") is not None and b.get("latitude") is not None:
        return _km(a, b) <= NEAR_KM
    return a.get("pref") == b.get("pref")
