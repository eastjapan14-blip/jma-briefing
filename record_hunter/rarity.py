"""記録の「珍しさ」を、統計の長さ・前回記録からの年数・歴代上位の年・同じ日の他地点から説明する。

判定はすべて State にある値だけで行う（新しい取得はしない）。段階は4つ:
  ●●● とても珍しい / ●●○ 珍しい / ●○○ やや珍しい / ○○○ 珍しくない
点数の付け方（0〜3 に丸める）
  記録の種類と統計の長さ:
    観測史上1位   … 統計30年以上 3 ／ 10年以上 2
    月の1位      … 統計30年以上 2 ／ 10年以上 1（通年でも上位5位以内なら +1）
    観測史上2〜3位 … 統計30年以上 2 ／ それ以外 1
    タイ記録      … −1
  前回の記録（同じ種類の1位）が 30年以上前 +1 ／ 2年以内 −1
  統計10年未満 → 記録が出やすいので 0（気象庁の更新状況ページにも載らない）
"""
from datetime import date

from .metrics import METRICS, fmt

LABELS = {3: ("●●●", "とても珍しい"), 2: ("●●○", "珍しい"), 1: ("●○○", "やや珍しい"), 0: ("○○○", "珍しくない")}


def _kind(ev: dict) -> str:
    tags = set(ev.get("tags", []))
    if "ALL_TIME_1ST" in tags:
        return "alltime"
    if "ALL_TIME_1ST_TIE" in tags:
        return "alltime_tie"
    if "MONTHLY_1ST" in tags:
        return "monthly"
    if "MONTHLY_1ST_TIE" in tags:
        return "monthly_tie"
    return "top"


def stats_years(ev: dict):
    """統計の年数（気象庁の数え方に合わせ、開始年を1年目とする）。"""
    s = ev.get("stats_start")
    return int(ev["date"][:4]) - int(s) + 1 if s else None


def _ago(ev: dict, d: str) -> str:
    """起日 d が観測日の何年前か。1年未満は日数で言う。"""
    if not d:
        return ""
    obs = date.fromisoformat(ev["date"])
    try:
        prev = date.fromisoformat(d[:10]) if len(d) >= 10 else date(int(d[:4]), int(d[5:7] or 1), 1)
    except ValueError:
        return ""
    days = (obs - prev).days
    if days <= 1:
        return "前日"
    if days < 60:
        return f"{days}日前"
    if days < 365:
        return f"{days // 30}か月前"
    return f"{obs.year - prev.year}年前"


def _prev(ev: dict, kind: str) -> dict:
    return (ev.get("prev") if kind.startswith("alltime") else ev.get("prev_monthly")) or {}


def score(ev: dict) -> int:
    if ev.get("short_stats") or "SHORT_STATS" in ev.get("tags", []):
        return 0
    kind = _kind(ev)
    y = stats_years(ev) or 0
    if kind.startswith("alltime"):
        s = 3 if y >= 30 else 2
    elif kind.startswith("monthly"):
        s = 2 if y >= 30 else 1
        if ev.get("local_rank") and ev["local_rank"] <= 5:
            s += 1
    else:
        s = 2 if y >= 30 else 1
    if kind.endswith("_tie"):
        s -= 1
    d = _prev(ev, kind).get("date")
    if d:
        age = int(ev["date"][:4]) - int(str(d)[:4])
        if age >= 30:
            s += 1
        elif age <= 2:
            s -= 1
    return max(0, min(3, s))


def same_day(state: dict, ev: dict) -> tuple:
    """同じ日・同じ要素で記録級（月1位以上）になった他地点の数（全国, 同じ県）。"""
    n = p = 0
    for e in (state or {}).get("events", {}).values():
        if e is ev or e.get("station") == ev.get("station") or e.get("date") != ev["date"] or e.get("metric") != ev["metric"]:
            continue
        if not set(e.get("tags", [])) & {"ALL_TIME_1ST", "ALL_TIME_1ST_TIE", "MONTHLY_1ST", "MONTHLY_1ST_TIE"}:
            continue
        if e.get("status") == "REVISED":
            continue
        n += 1
        p += e.get("pref") == ev.get("pref")
    return n, p


def explain(ev: dict, state: dict = None) -> list:
    """通知に入れる「珍しさ」の行。1行目が段階、2行目以降が理由。"""
    m = METRICS[ev["metric"]]
    kind = _kind(ev)
    month = int(ev["date"][5:7])
    mark, label = LABELS[score(ev)]
    L = [f"📊 珍しさ {mark} {label}"]
    y = stats_years(ev)
    scope = "観測史上" if kind.startswith("alltime") else f"{month}月"
    if ev.get("short_stats") or "SHORT_STATS" in ev.get("tags", []):
        L.append(f"・統計{y}年目（{ev['stats_start']}年〜）と短く、記録が出やすい地点" if y else "・統計10年未満で、記録が出やすい地点")
    elif y:
        top = "最大" if m.comparator == "max" else "最低"
        word = {"alltime": f"で観測史上{top}", "alltime_tie": f"で観測史上{top}タイ", "monthly": f"の{month}月で{top}",
                "monthly_tie": f"の{month}月で{top}タイ"}.get(kind, f"で観測史上{ev.get('local_rank') or '上位'}位")
        L.append(f"・統計{y}年（{ev['stats_start']}年〜）{word}")
    prev = _prev(ev, kind)
    if prev.get("date"):
        pv, pd, ago = f"{fmt(m, prev.get('value'))}{m.unit}", _d(prev["date"]), _ago(ev, prev["date"])
        if kind.endswith("_tie"):
            L.append(f"・{pd}（{ago}）の{pv}に並ぶ")
        elif ago.endswith("年前"):
            L.append(f"・{ago[:-2]}年ぶりの更新（前回 {pv}、{pd}）")
        elif ago:
            L.append(f"・{ago}に出た記録（{pv}、{pd}）を更新")
    tops = ev.get("top3") if kind.startswith("alltime") or kind == "top" else ev.get("monthly_top3")
    short_stats = ev.get("short_stats") or "SHORT_STATS" in ev.get("tags", [])
    years = [] if short_stats else [str(t[2])[:4] for t in (tops or []) if t and t[2]]  # 統計が短いと上位はほぼ最近なので出さない
    if years:
        recent = sum(1 for x in years if int(ev["date"][:4]) - int(x) < 10)
        L.append(f"・これまでの{'歴代' if scope == '観測史上' else scope}上位: {'・'.join(years)}年" + (f"（うち{recent}回がこの10年）" if recent >= 2 else ""))
    if kind.startswith("monthly") and ev.get("local_rank") and ev["local_rank"] <= 5:
        L.append(f"・通年でも観測史上{ev['local_rank']}位")
    n, p = same_day(state, ev)
    if n:
        L.append(f"・同じ日に全国でほか{n}地点も{m.label}が記録級" + (f"（同じ県で{p}）" if p else ""))
    return L


def short(ev: dict) -> str:
    """まとめ通知の地点行に添える短い表記（例: ●●○ 統計51年・10年ぶり）。"""
    mark, _ = LABELS[score(ev)]
    kind = _kind(ev)
    y = stats_years(ev)
    bits = [f"統計{y}年" if y else ""]
    d = _prev(ev, kind).get("date")
    if d and not kind.endswith("_tie"):
        ago = _ago(ev, d)
        bits.append(f"{ago[:-2]}年ぶり" if ago.endswith("年前") else f"{ago}の記録を更新")
    return f"{mark} " + "・".join(b for b in bits if b)


def _d(iso):
    p = str(iso).split("-")
    return "/".join(str(int(x)) for x in p if x)
