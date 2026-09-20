#!/usr/bin/env python3
"""気象庁防災情報XMLのAtomフィードを取得し、動画トリガー候補を一覧する。

使い方:
  python3 scripts/fetch_feed.py            # 未確認の候補だけ表示
  python3 scripts/fetch_feed.py --all      # 直近7日分をすべて表示
  python3 scripts/fetch_feed.py --mark     # 表示した候補を確認済みにする

出力: 1行1候補。段階(A/B/C)、日時、種別、発表官署、見出し、XMLのURL。
"""
import argparse, json, sys, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

FEEDS = {
    "extra": "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml",    # 警報・気象情報など（随時）
    "regular": "https://www.data.jma.go.jp/developer/xml/feed/regular_l.xml",  # 定時
}
NS = {"a": "http://www.w3.org/2005/Atom"}
STATE = Path(__file__).resolve().parent.parent / "state" / "seen.json"

# 段階判定。上から順に評価し、最初に一致した段階を採用する。
# C: 即時の一言動画  B: 速報テンプレ  A: 本編（記者会見級）  D: 定例（長期予報）
SEASONAL = ("全般１か月予報", "全般３か月予報", "全般暖候期予報", "全般寒候期予報")
RULES = [
    ("C", lambda t, c: t == "気象特別警報・警報・注意報" and "特別警報" in c and "解除" not in c),
    ("C", lambda t, c: t == "府県気象防災速報"),
    ("C", lambda t, c: t == "記録的短時間大雨情報"),
    ("B", lambda t, c: "線状降水帯" in c),
    ("B", lambda t, c: t == "全般気象情報"),
    ("B", lambda t, c: t == "地方気象情報" and any(k in c for k in ("台風", "警報級", "大雨", "大雪", "暴風"))),
    ("B", lambda t, c: t == "府県気象情報" and any(k in c for k in ("台風", "警報級の大雨", "警報級の大雪", "暴風"))),
    ("B", lambda t, c: t == "土砂災害警戒情報"),
    ("B", lambda t, c: t == "指定河川洪水予報"),
]


# 解除・見込み低下の情報は動画の対象外
NEGATIVE = ("解除", "可能性は低くなりました", "おそれはなくなりました", "解消し", "警戒解除")
# 「〜気象解説情報」は「〜気象情報」と同じ本文が別電文（VPFJ51 等）で流れる完全な重複なので読まない
DUPLICATE_TITLES = ("全般気象解説情報", "地方気象解説情報", "府県気象解説情報")
# 1件ずつ通知せず、1回の実行分をまとめて1通にする種別（台風時は府県ごとに十数件出るため）
DIGEST_TITLES = ("地方気象情報", "府県気象情報", "土砂災害警戒情報", "指定河川洪水予報")


def classify(title, content):
    if title in DUPLICATE_TITLES:
        return None
    if title in SEASONAL:
        return "D"
    if any(k in content for k in NEGATIVE):
        return None
    for tier, fn in RULES:
        if fn(title, content):
            return tier
    return None


def load_feed(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        root = ET.fromstring(r.read())
    for e in root.findall("a:entry", NS):
        yield {
            "id": e.findtext("a:id", "", NS),
            "updated": e.findtext("a:updated", "", NS),
            "title": e.findtext("a:title", "", NS),
            "content": (e.findtext("a:content", "", NS) or "").strip(),
            "author": e.find("a:author", NS).findtext("a:name", "", NS),
            "url": e.find("a:link", NS).get("href"),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="確認済みも含めて表示")
    ap.add_argument("--mark", action="store_true", help="表示した候補を確認済みにする")
    ap.add_argument("--json", action="store_true", help="JSONで出力")
    args = ap.parse_args()

    seen = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    found = []
    for name, url in FEEDS.items():
        for e in load_feed(url):
            tier = classify(e["title"], e["content"])
            if not tier:
                continue
            if not args.all and e["id"] in seen:
                continue
            e["tier"] = tier
            found.append(e)
    found.sort(key=lambda x: (x["tier"], x["updated"]), reverse=False)

    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
    else:
        for e in found:
            head = e["content"].splitlines()[0][:70] if e["content"] else ""
            print(f'{e["tier"]} {e["updated"]} {e["title"]} / {e["author"]} | {head} | {e["url"]}')
        print(f"\n候補 {len(found)} 件", file=sys.stderr)

    if args.mark:
        seen |= {e["id"] for e in found}
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
