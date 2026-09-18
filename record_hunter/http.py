"""HTTP 取得。気象庁への負荷を抑える（直列・間隔・条件付きGET・バックオフ・高速Retryなし）。

Fetcher        実網。state["sources"][key] に ETag / Last-Modified を保存し、未更新なら 304 で本文を取らない。
FixtureFetcher replay / テスト用。URL をファイル名に写像して fixtures ディレクトリから読む。
"""
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .log import log


@dataclass
class FetchResult:
    status: int
    body: Optional[bytes]
    not_modified: bool = False
    error: str = ""

    @property
    def ok(self):
        return self.status == 200 and self.body is not None


def fixture_name(url: str) -> str:
    """URL → fixture ファイル名。snapshot と replay で同じ関数を使う。"""
    m = re.search(r"/alltable/([a-z0-9]+)_(?:rct|\d{12})\.csv$", url)
    if m:
        return f"{m.group(1)}.csv"
    m = re.search(r"/rank_update/(d\d{4})\.html$", url)
    if m:
        return f"rank_update_{m.group(1)}.html"
    m = re.search(r"/view/rank_([as])\.php\?prec_no=(\d+)&block_no=(\d+)&year=&month=(\d*)&", url)
    if m:
        kind, prec, block, month = m.groups()
        return f"rank_{kind}_{prec}_{block}" + (f"_m{int(month):02d}" if month else "") + ".html"
    if url.endswith("amedastable.json"):
        return "amedastable.json"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("//", 1)[-1])[:120]


class Fetcher:
    def __init__(self, cfg, state: Optional[dict] = None, sleep=time.sleep):
        self.cfg = cfg
        self.state = state if state is not None else {"sources": {}}
        self._sleep = sleep
        self._last = 0.0
        self.count = 0

    def _throttle(self):
        wait = self.cfg.fetch_sleep - (time.monotonic() - self._last)
        if self._last and wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()

    def get(self, url: str, key: Optional[str] = None, retries: int = 2) -> FetchResult:
        src = self.state.setdefault("sources", {}).setdefault(key, {}) if key else {}
        headers = {"User-Agent": self.cfg.user_agent}
        if src.get("etag"):
            headers["If-None-Match"] = src["etag"]
        if src.get("last_modified"):
            headers["If-Modified-Since"] = src["last_modified"]
        delay = 2.0
        for attempt in range(retries + 1):
            self._throttle()
            self.count += 1
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.cfg.timeout) as r:
                    body = r.read()
                    if key:
                        src["etag"] = r.headers.get("ETag", "")
                        src["last_modified"] = r.headers.get("Last-Modified", "")
                        src["fail_count"] = 0
                    log("fetch", "fetch_ok", key=key or fixture_name(url), bytes=len(body))
                    return FetchResult(200, body)
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    log("fetch", "fetch_skip", key=key, reason="not_modified")
                    return FetchResult(304, None, not_modified=True)
                if e.code == 404:
                    log("fetch", "fetch_fail", key=key or fixture_name(url), status=404)
                    return FetchResult(404, None, error="404")
                err = f"HTTP {e.code}"
                if e.code < 500:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                err = str(e)[:120]
            if attempt < retries:
                self._sleep(delay)
                delay *= 2
        if key:
            src["fail_count"] = src.get("fail_count", 0) + 1
        log("fetch", "fetch_fail", key=key or fixture_name(url), error=err)
        return FetchResult(0, None, error=err)


class FixtureFetcher:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.count = 0
        self.requested = []

    def get(self, url: str, key: Optional[str] = None, retries: int = 0) -> FetchResult:
        self.count += 1
        name = fixture_name(url)
        self.requested.append(name)
        p = self.dir / name
        if not p.exists() and (self.dir.parent / name).exists():
            p = self.dir.parent / name          # 日付をまたいで共有する fixture（amedastable.json など）
        if not p.exists():
            log("fetch", "fetch_fail", key=name, status=404, fixture=str(self.dir))
            return FetchResult(404, None, error="fixture missing")
        log("fetch", "fetch_ok", key=name, fixture=1)
        return FetchResult(200, p.read_bytes())
