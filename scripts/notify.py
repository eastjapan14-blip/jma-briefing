#!/usr/bin/env python3
"""新しい候補を ntfy.sh 経由で iPhone に通知する（GitHub Actions から10分ごとに実行）。

重複防止:
  - WATCH_STATE_DIR/watch_seen.json（GitHub Actions では watch-state ブランチ）に送信済みURLを保存
  - 保険として ntfy のトピック履歴（直近24時間）も見る
  - 直近 FRESH_HOURS 時間以内に更新された候補だけを対象にする
通知の分け方:
  - 即時（1件1通）: 段階A/C/D、全般気象情報、線状降水帯を含むもの
  - まとめ（1回の実行で1通）: 地方・府県気象情報、土砂災害警戒情報、洪水予報。事象ごとに件数と地域を列挙

環境変数:
  NTFY_TOPIC       必須。購読しているトピック名
  NTFY_SERVER      既定 https://ntfy.sh
  FRESH_HOURS      既定 12
  WATCH_STATE_DIR  watch_seen.json を置く場所（既定 state/）
使い方:
  NTFY_TOPIC=xxx python3 scripts/notify.py [--dry-run]
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_feed import DIGEST_TITLES, FEEDS, classify, load_feed  # noqa: E402
from fetch_press import recent as recent_press  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

YT_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id=UCajQ4ZQJrgwSxkF6xaCfrRw"  # 気象庁/JMA


def youtube_conferences():
    """公式YouTubeのRSSから記者会見（ライブ配信のアーカイブ）を拾う。"""
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    root = None
    for attempt in range(3):  # GitHub のランナーからは時々 404 が返る
        try:
            req = urllib.request.Request(YT_RSS, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                root = ET.fromstring(r.read())
            break
        except Exception as e:
            err = e
    if root is None:
        print(f"YouTube RSS 取得失敗（3回）: {err}", file=sys.stderr)
        return
    for e in root.findall("a:entry", ns):
        title = e.findtext("a:title", "", ns)
        if "会見" not in title:
            continue
        vid = e.findtext("yt:videoId", "", ns)
        yield {"updated": e.findtext("a:published", "", ns), "title": "記者会見（YouTube）", "content": title,
               "author": "気象庁/JMA", "url": f"https://www.youtube.com/watch?v={vid}", "tier": "A"}


def press_releases():
    """報道発表資料のうち記者会見に対応するもの（見通し・影響について等）。日付しか無いので当日と前日を対象にする。"""
    for e in recent_press(days=1):
        if e["tier"] != "A":
            continue
        yield {"updated": f'{e["date"].isoformat()}T00:00:00+00:00', "title": "報道発表（記者会見資料）", "content": e["title"],
               "author": "気象庁", "url": e["url"], "tier": "A"}

SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
TOPIC = os.environ.get("NTFY_TOPIC", "")
FRESH_HOURS = float(os.environ.get("FRESH_HOURS", "12"))
STATE_DIR = Path(os.environ.get("WATCH_STATE_DIR", str(Path(__file__).resolve().parent.parent / "state")))
STATE = STATE_DIR / "watch_seen.json"
JST = timezone(timedelta(hours=9))
PRIORITY = {"C": 5, "B": 4, "A": 4, "D": 3}
# 広域事象（台風など）のまとめ方
WIDE_REGIONS = int(os.environ.get("WIDE_REGIONS", "4"))      # 3時間以内に同じ事象でこの数の府県・地方が出たら広域扱い
QUIET_MIN = int(os.environ.get("DIGEST_QUIET_MIN", "20"))    # 最後の追加からこの分数、新着が無ければ送る
MAX_HOLD_MIN = int(os.environ.get("DIGEST_MAX_HOLD_MIN", "90"))  # 最初の保留からこの分数たったら必ず送る（台風の波は全般→地方→府県で約80分）
ALWAYS_HOLD = ("土砂災害警戒情報", "指定河川洪水予報")          # 補足情報で繰り返し出るので常に束ねる
ALWAYS_HOLD_MIN = int(os.environ.get("ALWAYS_HOLD_MIN", "60"))  # それらは最初の保留からこの分数で送る（1時間ごとの束）
TAGS = {"C": ["rotating_light"], "B": ["warning"], "A": ["studio_microphone"], "D": ["calendar"]}


def now_utc():
    """WATCH_NOW（ISO時刻）でテスト用に現在時刻を差し替えられる。"""
    v = os.environ.get("WATCH_NOW")
    return datetime.fromisoformat(v) if v else datetime.now(timezone.utc)


def load_state():
    """state の構成:
      urls    {url: 処理時刻}           一度処理した電文（通知済み・保留中・除外を含む）
      bodies  {本文キー: 送信時刻}      段階Cの同一本文の重複除去
      pending {url: 電文}               広域事象として保留中の電文（まとめ通知待ち）
      topics  {事象: {地域: 時刻}}      広域判定用。3時間で捨てる
    """
    try:
        d = json.loads(STATE.read_text())
    except Exception:
        d = {}
    if "urls" not in d:  # 旧形式（url: 時刻 のみ）
        d = {"urls": d}
    now = now_utc()
    c72 = (now - timedelta(hours=72)).isoformat()
    c24 = (now - timedelta(hours=24)).isoformat()
    c3 = (now - timedelta(hours=3)).isoformat()
    st = {k: {u: t for u, t in d.get(k, {}).items() if t >= c72} for k in ("urls", "bodies")}
    st["pending"] = {u: e for u, e in d.get("pending", {}).items() if e.get("held", "") >= c24}
    st["topics"] = {}
    for topic, regions in d.get("topics", {}).items():
        r = {k: t for k, t in regions.items() if t >= c3}
        if r:
            st["topics"][topic] = r
    return st


def save_state(d):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=0, sort_keys=True))


def already_sent():
    """ntfy の履歴から送信済みURLを集める（state が消えたときの保険）。"""
    try:
        req = urllib.request.Request(f"{SERVER}/{TOPIC}/json?poll=1&since=24h")
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
    except Exception as e:  # 履歴が取れなくても通知は止めない
        print(f"履歴取得失敗: {e}", file=sys.stderr)
        return set()
    urls = set()
    for line in body.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("click"):
            urls.add(m["click"])
    return urls


def send(payload):
    payload["topic"] = TOPIC
    req = urllib.request.Request(SERVER, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def when(e):
    return datetime.fromisoformat(e["updated"].replace("Z", "+00:00"))


def stamp(e):
    """発表時刻（JST）。60分以上前なら遅延を明記して、古い情報だと分かるようにする。"""
    t = when(e).astimezone(JST)
    late = int((now_utc() - when(e)).total_seconds() // 60)
    s = f"{t.month}/{t.day} {t.hour:02d}:{t.minute:02d}発表"
    return s + (f"（{late}分前）" if late >= 60 else "")


def publish(e):
    head = e["content"].splitlines()[0][:140] if e["content"] else ""
    return send({
        "title": f'[{e["tier"]}] {e["title"]}／{e["author"]}',
        "message": f'{stamp(e)}\n{head}\n\n/briefing {e["url"]}',
        "priority": PRIORITY[e["tier"]],
        "tags": TAGS[e["tier"]],
        "click": e["url"],
    })


def body_key(e):
    """C段階の重複判定キー。先頭の【…】を除いた本文＋発表官署。同じ事象の別電文（記録雨の情報と速報など）を1回にする。"""
    body = re.sub(r"^(【[^】]*】)+", "", e["content"]).strip()
    body = re.sub(r"\s+", "", body)[:120]
    return f'{e["author"]}|{body}'


def new_special_warnings(url):
    """気象特別警報・警報・注意報の電文を読み、Status が「発表」の特別警報だけを返す。継続なら空。取得失敗は None。"""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"電文取得失敗: {e}", file=sys.stderr)
        return None
    found = []
    for w in root.iter():
        if not w.tag.endswith("}Warning") or not w.get("type", "").startswith("気象警報・注意報（市町村等"):
            continue
        for item in w.findall("{*}Item"):
            area = item.findtext("{*}Area/{*}Name", "")
            for k in item.findall("{*}Kind"):
                name, status = k.findtext("{*}Name", ""), k.findtext("{*}Status", "")
                if "特別警報" in name and status == "発表":
                    found.append(f"{area}：{name}")
    return found


def topic_of(e):
    """本文の【福島県気象解説情報（台風第２５号）】から事象名（台風第２５号）を取り出す。
    【奄美地方（鹿児島県）気象解説情報（台風第２６号）】のような入れ子でも、最後の（…）を採る。"""
    m = re.match(r"【([^】]*)】", e["content"])
    if m:
        inner = re.findall(r"[（(]([^（()）]+)[）)]", m.group(1))
        if inner and not re.search(r"[都道府県]$|を含む", inner[-1]):
            return inner[-1]
    return e["title"]


def region_of(e):
    """本文冒頭の【…】から府県名（予報区）か地方名を取り出す。"""
    c = e["content"]
    if e["title"] == "地方気象情報":
        m = re.match(r"【([^】]*?地方)", c)
        if m:
            return m.group(1).replace("地方", "") or m.group(1)
    m = re.match(r"【(北海道|[^】]{1,3}?[都府県])", c)
    if m:
        name = m.group(1)
        return name if name == "北海道" else re.sub(r"[都府県]$", "", name)
    m = re.match(r"【([^】]*?地方)", c)  # 沖縄本島地方、宗谷地方など
    if m:
        return m.group(1).replace("地方", "")
    return re.sub(r"(地方気象台|管区気象台|気象台|河川事務所|気象庁)", "", e["author"]).strip() or e["author"]


HAZARDS = [("線状降水帯", "線状降水帯"), ("土砂災害", "土砂"), ("浸水", "浸水"), ("氾濫", "河川"), ("増水", "河川"),
           ("暴風", "暴風"), ("強風", "強風"), ("高潮", "高潮"), ("高波", "高波"), ("大雪", "大雪"),
           ("竜巻", "竜巻"), ("突風", "突風"), ("落雷", "落雷")]
LEVELS = [("厳重に警戒", 3), ("警戒", 2), ("注意", 1)]
MARK = {3: "◎", 2: "○", 1: "△"}


def hazards_of(text):
    """見出し文から「災害の種類 → 呼びかけの強さ（◎厳重に警戒 ○警戒 △注意）」を取り出す。"""
    text = re.sub(r"^(【[^】]*】)+", "", text)
    out = {}
    for clause in re.split(r"。|(?<=警戒し)、|(?<=注意し)、|(?<=警戒して)、", text):
        if "線状降水帯" in clause:  # 「発生する可能性」のように警戒・注意の語が無くても最上位で示す
            out["線状降水帯"] = 3
        lv = next((v for k, v in LEVELS if k in clause), 0)
        if not lv:
            continue
        for key, label in HAZARDS:
            if key in clause:
                out[label] = max(out.get(label, 0), lv)
    return out


def hazard_line(es):
    """同じ地域の電文（最新を優先）から ◎土砂・暴風 ○浸水 の形の1行を作る。"""
    latest = max(es, key=when)
    hz = hazards_of(latest["content"].splitlines()[0] if latest["content"] else "")
    if not hz:
        return ""
    parts = []
    for lv in (3, 2, 1):
        names = [k for k, v in hz.items() if v == lv]
        if names:
            parts.append(MARK[lv] + "・".join(names))
    return " ".join(parts)


def label_of(e):
    m = re.match(r"【([^】]+)】", e["content"])
    return m.group(1) if m else e["title"]


def publish_digest(topic, items, click):
    """広域事象のまとめ通知（1事象1通）。地方→府県の順に、地域ごとの呼びかけの強さを1行で示す。"""
    by_kind = {}
    for e in items:
        by_kind.setdefault(e["title"], []).append(e)
    lines = []
    for kind in ("地方気象情報", "府県気象情報"):
        es = by_kind.pop(kind, [])
        if not es:
            continue
        regions = {}
        for e in es:
            regions.setdefault(region_of(e), []).append(e)
        def strength(r):
            hz = hazards_of(max(regions[r], key=when)["content"])
            return (max(hz.values(), default=0), sum(1 for v in hz.values() if v == 3))
        order = sorted(regions, key=strength, reverse=True)  # 呼びかけの強い地域を上に
        lines.append(f"〔{kind.replace('気象情報', '')} {len(regions)}〕")
        for r in order:
            hl = hazard_line(regions[r])
            lines.append(f"{r} {hl}".rstrip())
    for kind, es in by_kind.items():  # 土砂災害警戒情報・洪水予報など
        counts = {}
        for e in es:
            counts[label_of(e)] = counts.get(label_of(e), 0) + 1
        lines.append(f"〔{kind} {len(es)}件〕")
        lines += [f"{k}" + (f" ×{n}" if n > 1 else "") for k, n in counts.items()]
    newest = max(items, key=when)
    n_pref = len({region_of(e) for e in items if e["title"] == "府県気象情報"})
    title_tail = f"（府県{n_pref}）" if n_pref else f"（{len(items)}件）"
    legend = "◎厳重に警戒 ○警戒 △注意" if any("◎" in l or "○" in l or "△" in l for l in lines) else ""
    return send({
        "title": f"[B] まとめ {topic}{title_tail}",
        "message": "\n".join(x for x in [f"{len(items)}件 〜{stamp(newest)}", legend] if x) + "\n" + "\n".join(lines) + "\n\n/briefing 候補",
        "priority": 3,
        "tags": ["page_facing_up"],
        "click": click,
    })


def publish_c_group(title, topic, es):
    """段階Cが同じ実行で同じ事象に複数（線状降水帯直前予測が3県同時など）→ 待たずに1通で送る。"""
    regions = "・".join(dict.fromkeys(region_of(e) for e in es))
    body = "\n".join("・" + re.sub(r"^(【[^】]*】)+", "", e["content"].splitlines()[0])[:90] for e in es)
    newest = max(es, key=when)
    return send({
        "title": f"[C] {topic}／{regions}",
        "message": f"{len(es)}件 {stamp(newest)}\n{body}\n\n/briefing " + " ".join(e["url"] for e in es),
        "priority": PRIORITY["C"],
        "tags": TAGS["C"],
        "click": newest["url"],
    })


def is_wide(topic, state):
    return "台風" in topic or len(state["topics"].get(topic, {})) >= WIDE_REGIONS


def main():
    dry = "--dry-run" in sys.argv
    if not TOPIC and not dry:
        sys.exit("NTFY_TOPIC が未設定")
    now = now_utc()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    state = load_state()
    sent = set(state["urls"]) | (already_sent() if TOPIC else set())
    body_cutoff = (now - timedelta(hours=12)).isoformat()
    bodies_seen = {k for k, t in state["bodies"].items() if t >= body_cutoff}
    new, seen_now, skipped = [], set(), []
    for url in FEEDS.values():
        for e in load_feed(url):
            tier = classify(e["title"], e["content"])
            if not tier:
                continue
            if when(e) < cutoff or e["url"] in sent or e["url"] in seen_now:
                continue
            seen_now.add(e["url"])
            if e["title"] == "気象特別警報・警報・注意報":
                # 特別警報が継続中は同じ見出しの電文が繰り返し流れる。新規「発表」のときだけ通知する
                fresh = new_special_warnings(e["url"])
                if fresh == []:
                    skipped.append(e)
                    continue
                if fresh:
                    e["content"] = "／".join(fresh) + "\n" + e["content"]
            if tier == "C":
                k = body_key(e)
                if k in bodies_seen:
                    skipped.append(e)
                    continue
                bodies_seen.add(k)
                e["body_key"] = k
            e["tier"] = tier
            new.append(e)
    for e in list(youtube_conferences()) + list(press_releases()):
        if e["title"].startswith("記者会見") and when(e) < cutoff:
            continue
        if e["url"] in sent or e["url"] in seen_now:
            continue
        seen_now.add(e["url"])
        new.append(e)
    new.sort(key=lambda x: x["updated"])
    now_s = now.isoformat()

    # 振り分け: 即時（1件1通） / 保留（広域事象としてまとめる）
    single, held = [], []
    for e in new:
        if e["title"] not in DIGEST_TITLES:
            single.append(e)
            continue
        topic = topic_of(e)
        if e["title"] in ("府県気象情報", "地方気象情報"):
            state["topics"].setdefault(topic, {})[region_of(e)] = now_s
        if e["title"] == "地方気象情報" and "線状降水帯" in e["content"] and not is_wide(topic, state):
            single.append(e)  # 線状降水帯は地方単位なら即時（台風など広域事象のときはまとめに ◎線状降水帯 で入る）
            continue
        if e["title"] in ALWAYS_HOLD or is_wide(topic, state):
            held.append(e)
        else:
            single.append(e)  # 局地的な事象の府県情報は個別に届ける
    for e in held:
        state["pending"][e["url"]] = {k: e[k] for k in ("url", "title", "author", "content", "updated", "tier")} | {"held": now_s, "topic": topic_of(e)}

    groups_c = {}
    for e in single:
        if e["tier"] == "C":
            groups_c.setdefault((e["title"], topic_of(e)), []).append(e)
    for e in single:
        if e["tier"] == "C" and len(groups_c[(e["title"], topic_of(e))]) > 1:
            continue
        line = f'[{e["tier"]}] {e["updated"]} {e["title"]}／{e["author"]} {e["url"]}'
        print("DRY" if dry else publish(e), line)
    for (title, topic), es in groups_c.items():
        if len(es) > 1:
            print("DRY" if dry else publish_c_group(title, topic, es), f"[C] 同時 {topic} {len(es)} 件")

    # 保留分の送信判定: 事象ごとに、最後の追加から QUIET_MIN 分新着が無いか、最初の保留から MAX_HOLD_MIN 分たったら送る
    by_topic = {}
    for e in state["pending"].values():
        by_topic.setdefault(e["topic"], []).append(e)
    zenpan = {topic_of(e): e["url"] for e in single if e["title"] == "全般気象情報"}
    flushed = 0
    for topic, es in by_topic.items():
        first = min(datetime.fromisoformat(e["held"]) for e in es)
        last = max(datetime.fromisoformat(e["held"]) for e in es)
        if topic in ALWAYS_HOLD:
            quiet, overdue = False, (now - first) >= timedelta(minutes=ALWAYS_HOLD_MIN)
        else:
            quiet = (now - last) >= timedelta(minutes=QUIET_MIN)
            overdue = (now - first) >= timedelta(minutes=MAX_HOLD_MIN)
        if not (quiet or overdue):
            print(f"保留 {topic} {len(es)}件（最初 {int((now-first).total_seconds()//60)}分前 / 最後 {int((now-last).total_seconds()//60)}分前）", file=sys.stderr)
            continue
        click = zenpan.get(topic, "https://www.jma.go.jp/bosai/information/")
        print("DRY" if dry else publish_digest(topic, es, click), f"まとめ {topic} {len(es)} 件（{'静穏' if quiet else '上限'}）")
        for e in es:
            state["pending"].pop(e["url"], None)
        flushed += len(es)

    if not dry:
        for e in new + skipped:
            state["urls"][e["url"]] = now_s
        for e in new:
            if e.get("body_key"):
                state["bodies"][e["body_key"]] = now_s
        save_state(state)
    print(f"即時 {len(single)} 件、保留追加 {len(held)} 件、まとめ送信 {flushed} 件、保留中 {len(state['pending'])} 件、"
          f"継続・重複で除外 {len(skipped)} 件（送信済み {len(sent)} 件を除外）", file=sys.stderr)


if __name__ == "__main__":
    main()
