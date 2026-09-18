"""永続 State と Sparse Cache。

State（state.json）  通知済み・現在重要度・source timestamp。消えると重複通知が起きるので必ず永続化する。
Cache（cache/rank/*.json）  地点順位表。気象庁から再取得できる。TTL 切れやイベント発生で無効化する。
どちらも tmp → rename の atomic 書き込み。
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def default_state() -> dict:
    return {"schema": SCHEMA, "last_run": None, "runs": 0, "sources": {}, "events": {}, "clusters": {},
            "confirm_checked": {}}


def _write_atomic(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def load(state_dir) -> dict:
    p = Path(state_dir) / "state.json"
    if not p.exists():
        return default_state()
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise RuntimeError(f"state.json が壊れています: {e}")
    base = default_state()
    for k, v in base.items():
        s.setdefault(k, v)
    return s


def save(state_dir, state: dict):
    state["schema"] = SCHEMA
    _write_atomic(Path(state_dir) / "state.json", state)


def prune(state: dict, today: str, days: int):
    cutoff = (datetime.fromisoformat(today) - timedelta(days=days)).date().isoformat()
    for key in ("events", "clusters"):
        for k in list(state[key]):
            if state[key][k].get("date", "9999") < cutoff:
                del state[key][k]
    for d in list(state["confirm_checked"]):
        if d < cutoff:
            del state["confirm_checked"][d]


# ---- cache ----

def _cache_path(state_dir, name: str) -> Path:
    return Path(state_dir) / "cache" / "rank" / f"{name}.json"


def cache_get(state_dir, name: str, ttl_days: int):
    p = _cache_path(state_dir, name)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(obj["fetched_at"])
    except (ValueError, KeyError, OSError):
        return None
    if datetime.now(JST) - fetched > timedelta(days=ttl_days):
        return None
    return obj


def cache_put(state_dir, name: str, obj: dict):
    obj["fetched_at"] = now_iso()
    _write_atomic(_cache_path(state_dir, name), obj)


def cache_invalidate(state_dir, station_id: str):
    d = Path(state_dir) / "cache" / "rank"
    if not d.exists():
        return
    for p in d.glob(f"{station_id}*.json"):
        p.unlink()
