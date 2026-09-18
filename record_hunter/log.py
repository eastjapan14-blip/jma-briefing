"""1行構造化ログ。`RH <stage> <code> k=v ...` を stderr に出す。

問題が起きたとき「データが無かった／Parserが壊れた／判定で除外した／Dedupeした」を区別できるよう、
code は固定語彙にする（fetch_ok fetch_fail fetch_skip parse_n parser_warning candidate reject enrich
cache_hit cache_miss dedupe notify_sent notify_suppressed notify_fail quality_reject revision）。
公開リポジトリの Actions ログに出るので、トピック名を含む URL は書かない。
"""
import sys
from collections import Counter

COUNTS = Counter()


def log(stage: str, code: str, **kv):
    COUNTS[f"{stage}.{code}"] += 1
    body = " ".join(f"{k}={_s(v)}" for k, v in kv.items())
    print(f"RH {stage} {code} {body}".rstrip(), file=sys.stderr)


def _s(v):
    s = str(v)
    return s if " " not in s else '"' + s.replace('"', "'") + '"'


def summary():
    items = ", ".join(f"{k}={v}" for k, v in sorted(COUNTS.items()))
    print(f"RH summary {items}", file=sys.stderr)
