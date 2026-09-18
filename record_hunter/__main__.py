#!/usr/bin/env python3
"""Record Hunter CLI。

使い方:
  python3 -m record_hunter run [--dry-run] [--date YYYY-MM-DD]      本番（GitHub Actions から実行）
  python3 -m record_hunter dry-run                                    通知せず「何を通知するか」を表示
  python3 -m record_hunter replay --date YYYY-MM-DD [--fixtures DIR] [--state DIR] [--notify]
                                                                      Fixture から再生（既定は通知しない）
  python3 -m record_hunter snapshot --out DIR [--date YYYY-MM-DD]     今日の CSV・更新状況ページを Fixture 化
環境変数: NTFY_TOPIC NTFY_SERVER RH_STATE_DIR RH_DRY_RUN RH_MAX_ENRICH RH_FETCH_SLEEP RH_CACHE_TTL_DAYS
          RH_CLUSTER_MIN RH_RANK_THRESHOLD RH_NOTIFY_LEVELS RH_METRICS RH_ENABLE_ENRICH RH_ENABLE_RANK_UPDATE
"""
import argparse
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import state as st
from .config import Config, ROOT
from .http import Fetcher, FixtureFetcher, fixture_name
from .metrics import METRICS, active
from .pipeline import run
from .sources.stations import AMEDAS_TABLE_URL
from .notifier import rank_update_url

JST = timezone(timedelta(hours=9))


def _today(s):
    return date.fromisoformat(s) if s else datetime.now(JST).date()


def cmd_run(args, dry):
    cfg = Config.from_env()
    dry = dry or cfg.dry_run
    if not dry and not cfg.ntfy_topic:
        sys.exit("NTFY_TOPIC が未設定（dry-run なら --dry-run）")
    state = st.load(cfg.state_dir)
    fetcher = Fetcher(cfg, state)
    r = run(cfg, fetcher, state, _today(args.date), dry)
    print(f"観測 {r['observations']} 件, 候補 {r['candidates']} 件, 通知 {r['notifications']} 件, "
          f"HTTP {r['requests']} 回", file=sys.stderr)


def cmd_replay(args):
    cfg = Config.from_env()
    day = date.fromisoformat(args.date)
    fx = Path(args.fixtures) / args.date
    if not fx.exists():
        sys.exit(f"Fixture がありません: {fx}")
    cfg.state_dir = Path(args.state) if args.state else Path(tempfile.mkdtemp(prefix="rh-replay-"))
    state = st.load(cfg.state_dir)
    r = run(cfg, FixtureFetcher(fx), state, day, dry=not args.notify)
    print(f"replay {args.date}: 観測 {r['observations']} 件, 候補 {r['candidates']} 件, 通知 {r['notifications']} 件"
          f"（State: {cfg.state_dir}）", file=sys.stderr)


def cmd_snapshot(args):
    cfg = Config.from_env()
    day = _today(args.date)
    out = Path(args.out) / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    f = Fetcher(cfg)
    urls = [m.csv_url for m in METRICS.values() if active(m, day.month)]
    urls += [rank_update_url(day.isoformat()), rank_update_url((day - timedelta(days=1)).isoformat()), AMEDAS_TABLE_URL]
    for u in urls:
        r = f.get(u)
        if r.ok:
            (out / fixture_name(u)).write_bytes(r.body)
    print(f"snapshot → {out}", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(prog="record_hunter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run"); a.add_argument("--dry-run", action="store_true"); a.add_argument("--date")
    sub.add_parser("dry-run").add_argument("--date")
    a = sub.add_parser("replay"); a.add_argument("--date", required=True)
    a.add_argument("--fixtures", default=str(ROOT / "tests" / "fixtures")); a.add_argument("--state")
    a.add_argument("--notify", action="store_true")
    a = sub.add_parser("snapshot"); a.add_argument("--out", default=str(ROOT / "tests" / "fixtures")); a.add_argument("--date")
    args = p.parse_args(argv)
    if args.cmd == "run":
        cmd_run(args, args.dry_run)
    elif args.cmd == "dry-run":
        cmd_run(args, True)
    elif args.cmd == "replay":
        cmd_replay(args)
    elif args.cmd == "snapshot":
        cmd_snapshot(args)


if __name__ == "__main__":
    main()
