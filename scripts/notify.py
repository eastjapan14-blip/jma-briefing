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
    try:
        with urllib.request.urlopen(YT_RSS, timeout=30) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"YouTube RSS 取得失敗: {e}", file=sys.stderr)
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
TAGS = {"C": ["rotating_light"], "B": ["warning"], "A": ["studio_microphone"], "D": ["calendar"]}


def load_state():
    try:
        d = json.loads(STATE.read_text())
    except Exception:
        d = {}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    return {u: t for u, t in d.items() if t >= cutoff}


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
    late = int((datetime.now(timezone.utc) - when(e)).total_seconds() // 60)
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


def topic_of(e):
    """本文の【福島県気象解説情報（台風第２５号）】から事象名（台風第２５号）を取り出す。"""
    m = re.search(r"【[^（(】]*[（(]([^）)]+)[）)]】", e["content"])
    if m:
        return m.group(1)
    return e["title"]


def region_of(e):
    """本文冒頭の【…】から都道府県名か地方名を取り出す。"""
    c = e["content"]
    m = re.match(r"【([^】]{1,4}?[都道府県])", c) or re.match(r"【([^】]*?地方)", c)
    if m:
        return re.sub(r"(都|道|府|県)$", "", m.group(1)) if "地方" not in m.group(1) else m.group(1)
    return e["author"].replace("地方気象台", "").replace("管区気象台", "").replace("気象台", "")


def publish_digest(items, fallback_click):
    """まとめ通知: 事象 → 種別ごとに件数と地域を列挙して1通にする。"""
    groups = {}
    for e in items:
        groups.setdefault(topic_of(e), {}).setdefault(e["title"], []).append(e)
    lines = []
    for topic, kinds in groups.items():
        parts = []
        for kind, es in kinds.items():
            regions = "、".join(dict.fromkeys(region_of(x) for x in es))
            parts.append(f"{kind.replace('気象情報', '')} {len(es)}件（{regions}）")
        lines.append(f"■ {topic}: " + "／".join(parts))
    newest = max(items, key=when)
    head = f"{len(items)}件 {stamp(newest)}"
    return send({
        "title": f"[B] まとめ {'・'.join(list(groups)[:2])}",
        "message": head + "\n" + "\n".join(lines) + "\n\n/briefing 候補",
        "priority": 3,
        "tags": ["page_facing_up"],
        "click": fallback_click,
    })


def main():
    dry = "--dry-run" in sys.argv
    if not TOPIC and not dry:
        sys.exit("NTFY_TOPIC が未設定")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    state = load_state()
    sent = set(state) | (already_sent() if TOPIC else set())
    new, seen_now = [], set()
    for url in FEEDS.values():
        for e in load_feed(url):
            tier = classify(e["title"], e["content"])
            if not tier:
                continue
            if when(e) < cutoff or e["url"] in sent or e["url"] in seen_now:
                continue
            seen_now.add(e["url"])
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
    # 線状降水帯は地方単位までは即時、府県単位はまとめに入れる（台風時は府県が十数件になるため）
    single = [e for e in new if e["title"] not in DIGEST_TITLES
              or (e["title"] == "地方気象情報" and "線状降水帯" in e["content"])]
    digest = [e for e in new if e not in single]
    for e in single:
        line = f'[{e["tier"]}] {e["updated"]} {e["title"]}／{e["author"]} {e["url"]}'
        print("DRY" if dry else publish(e), line)
    if digest:
        zenpan = [e for e in single if e["title"] == "全般気象情報"]
        click = zenpan[-1]["url"] if zenpan else "https://www.jma.go.jp/bosai/information/"
        for e in digest:
            print("DRY-digest" if dry else "digest", f'{e["updated"]} {e["title"]}／{e["author"]} {topic_of(e)}')
        print("DRY" if dry else publish_digest(digest, click), f"まとめ {len(digest)} 件")
    if not dry:
        now = datetime.now(timezone.utc).isoformat()
        for e in new:
            state[e["url"]] = now
        save_state(state)
    print(f"即時 {len(single)} 件、まとめ {len(digest)} 件（送信済み {len(sent)} 件を除外）", file=sys.stderr)


if __name__ == "__main__":
    main()
