"""設定。すべて環境変数で上書きできる（引き継ぎ書 §40）。"""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(v, default=False):
    if v is None or v == "":
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    dry_run: bool = False
    state_dir: Path = ROOT / "state" / "record_hunter"
    user_agent: str = "jma-briefing record-hunter (github.com/eastjapan14-blip/jma-briefing)"
    timeout: int = 30
    fetch_sleep: float = 1.5          # 詳細ページ取得の最小間隔（秒）
    max_enrich: int = 15              # 1実行あたりの順位ページ取得上限
    cache_ttl_days: int = 30
    cluster_min: int = 2              # 都道府県クラスターの最小地点数
    cluster_steps: tuple = (2, 4, 8)  # クラスター再通知の地点数閾値
    rank_threshold: int = 3           # 歴代この順位以内を候補にする
    old_record_years: int = 30        # これ以上古い記録の更新を「古い記録」と注記
    notify_levels: tuple = ("A", "B")
    enabled_metrics: tuple = ("tmax", "tmin", "pre1h", "pre24h", "preday", "snowdepth", "snow24h")
    enable_enrich: bool = True
    enable_rank_update: bool = True
    enable_confirm: bool = True
    prune_days: int = 7
    max_group_lines: int = 8          # まとめ通知に載せる最大地点数
    a_batch_min: int = 3              # 同じ県・要素で A がこの数以上同時に出たら1通にまとめる（§21 短時間batch）

    @classmethod
    def from_env(cls, env=os.environ):
        c = cls()
        c.ntfy_topic = env.get("NTFY_TOPIC", "")
        c.ntfy_server = env.get("NTFY_SERVER", c.ntfy_server).rstrip("/")
        c.dry_run = _bool(env.get("RH_DRY_RUN"), False)
        c.state_dir = Path(env.get("RH_STATE_DIR", str(c.state_dir)))
        c.fetch_sleep = float(env.get("RH_FETCH_SLEEP", c.fetch_sleep))
        c.max_enrich = int(env.get("RH_MAX_ENRICH", c.max_enrich))
        c.cache_ttl_days = int(env.get("RH_CACHE_TTL_DAYS", c.cache_ttl_days))
        c.cluster_min = int(env.get("RH_CLUSTER_MIN", c.cluster_min))
        c.rank_threshold = int(env.get("RH_RANK_THRESHOLD", c.rank_threshold))
        c.old_record_years = int(env.get("RH_OLD_RECORD_YEARS", c.old_record_years))
        c.notify_levels = tuple(x for x in env.get("RH_NOTIFY_LEVELS", "A,B").split(",") if x)
        if env.get("RH_METRICS"):
            c.enabled_metrics = tuple(x.strip() for x in env["RH_METRICS"].split(",") if x.strip())
        c.enable_enrich = _bool(env.get("RH_ENABLE_ENRICH"), True)
        c.enable_rank_update = _bool(env.get("RH_ENABLE_RANK_UPDATE"), True)
        c.enable_confirm = _bool(env.get("RH_ENABLE_CONFIRM"), True)
        c.a_batch_min = int(env.get("RH_A_BATCH_MIN", c.a_batch_min))
        return c
