#!/usr/bin/env python3
"""新しい候補を ntfy.sh 経由で iPhone に通知する（GitHub Actions から10分ごとに実行）。

状態ファイルを持たない設計:
  - 直近 FRESH_HOURS 時間以内に更新された候補だけを対象にする
  - ntfy のトピック履歴（直近24時間）に同じURLがあれば送らない（重複防止）

環境変数:
  NTFY_TOPIC   必須。購読しているトピック名
  NTFY_SERVER  既定 https://ntfy.sh
  FRESH_HOURS  既定 12
使い方:
  NTFY_TOPIC=xxx python3 scripts/notify.py [--dry-run]
"""
import json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_feed import FEEDS, classify, load_feed  # noqa: E402
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
PRIORITY = {"C": 5, "B": 4, "A": 4, "D": 3}
TAGS = {"C": ["rotating_light"], "B": ["warning"], "A": ["studio_microphone"], "D": ["calendar"]}


def already_sent():
    """ntfy の履歴から送信済みURLを集める。"""
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


def publish(e):
    head = e["content"].splitlines()[0][:140] if e["content"] else ""
    payload = {
        "topic": TOPIC,
        "title": f'[{e["tier"]}] {e["title"]}／{e["author"]}',
        "message": f'{head}\n\n/briefing {e["url"]}',
        "priority": PRIORITY[e["tier"]],
        "tags": TAGS[e["tier"]],
        "click": e["url"],
    }
    req = urllib.request.Request(SERVER, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def main():
    dry = "--dry-run" in sys.argv
    if not TOPIC and not dry:
        sys.exit("NTFY_TOPIC が未設定")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    sent = already_sent() if TOPIC else set()
    new = []
    for url in FEEDS.values():
        for e in load_feed(url):
            tier = classify(e["title"], e["content"])
            if not tier:
                continue
            upd = datetime.fromisoformat(e["updated"].replace("Z", "+00:00"))
            if upd < cutoff or e["url"] in sent:
                continue
            e["tier"] = tier
            new.append(e)
    for e in list(youtube_conferences()) + list(press_releases()):
        upd = datetime.fromisoformat(e["updated"].replace("Z", "+00:00"))
        if e["title"].startswith("記者会見") and upd < cutoff:
            continue
        if e["url"] in sent:
            continue
        new.append(e)
    new.sort(key=lambda x: x["updated"])
    for e in new:
        line = f'[{e["tier"]}] {e["updated"]} {e["title"]}／{e["author"]} {e["url"]}'
        if dry:
            print("DRY", line)
        else:
            print(publish(e), line)
    print(f"新規 {len(new)} 件（送信済み {len(sent)} 件を除外）", file=sys.stderr)


if __name__ == "__main__":
    main()
