# jma-briefing

気象庁の発表（防災情報XML・報道発表・公式YouTubeの記者会見）とアメダスの観測記録を見張り、新着を ntfy で iPhone に通知する。全体像は `docs/notify-overview.html`。

2026-11 に動画・スライド制作の機能は削除し、通知だけを残した（過去の制作用スクリプトは git の履歴にある）。

```
scripts/fetch_feed.py    防災情報XMLフィードを読み、段階（A〜D）を判定する
scripts/fetch_press.py   報道発表の一覧（notify.py が使う）
scripts/notify.py        新着候補（XML・報道発表・記者会見動画）を ntfy へ通知
record_hunter/           アメダス Record Hunter（記録級の観測値を検出して ntfy へ通知）
tools/build_etrn_index.py  地点索引（record_hunter/data/etrn_index.json）を一度だけ生成
tests/                   pytest（Fixture は tests/fixtures/<日付>/）
docs/notify-overview.html  通知システムの概略図
```

公開リポジトリにしているのは、GitHub Actions を無料で10分ごとに動かすため。秘密の値（ntfy のトピック名など）は GitHub の Secrets に置き、リポジトリには書かない。

## 監視と通知（GitHub Actions + ntfy）

- `.github/workflows/watch.yml` が10分ごとに `scripts/notify.py` を実行し、新しい候補を ntfy.sh のトピックへ送る。Mac の起動は不要。
- iPhone の ntfy アプリでトピック（GitHub の Secret `NTFY_TOPIC`）を購読する。通知本文の末尾に気象庁の原文 URL が入る。
- 通知の振り分け（`scripts/notify.py`）
  - **即時・1件1通**: 段階A/C/D、全般気象情報、局地的な事象の府県・地方気象情報（例: 1県だけの大雨）
  - **即時・同時分を1通**: 段階Cが同じ実行で同じ事象に複数（線状降水帯直前予測が3県同時など）
  - **広域まとめ**: 台風、または3時間以内に同じ事象で4つ以上の府県・地方が出たとき。波が落ち着く（最後の追加から20分新着なし）か、最初から90分たった時点で1通にする。地域ごとに ◎厳重に警戒 ○警戒 △注意 と災害の種類を1行で示し、呼びかけの強い地域を上に並べる
  - **1時間ごとの束**: 土砂災害警戒情報・指定河川洪水予報（補足情報で繰り返し出るため）
  - 閾値は環境変数 `WIDE_REGIONS` `DIGEST_QUIET_MIN` `DIGEST_MAX_HOLD_MIN` `ALWAYS_HOLD_MIN` で変えられる
- 府県気象情報として流れる「気象防災速報」の写しは、府県気象防災速報と重複するので読まない。
- 「〜気象解説情報」は「〜気象情報」と同じ本文の重複電文なので読まない。
- 送信済みURLは `watch-state` ブランチの `watch_seen.json` に保存（保険として ntfy 履歴も参照）。
- 特別警報は電文の Status を読み、新規「発表」のときだけ通知する（継続中は同じ見出しが繰り返し流れるため）。段階Cは本文が同じ別電文（記録的短時間大雨情報と気象防災速報など）も1回にまとめる。
- GitHub の定期実行は混雑時に大きく遅れる（実測で1日3〜6回しか動かない）。通知本文に発表時刻と経過分数を出しているので、古い情報かどうかはそこで判断する。

### 実行間隔を確実に10分にする（外部 cron から起動）

GitHub の schedule に頼らず、外部の cron サービスから `workflow_dispatch` を叩く。

1. GitHub → Settings → Developer settings → Fine-grained personal access tokens で、対象リポジトリを `jma-briefing` に限定し、Repository permissions の **Actions: Read and write** だけを付けたトークンを作る。
2. cron-job.org（無料）などで10分ごとのジョブを作る。
   - URL: `https://api.github.com/repos/eastjapan14-blip/jma-briefing/actions/workflows/watch.yml/dispatches`
   - Method: POST
   - Headers: `Authorization: Bearer <トークン>` / `Accept: application/vnd.github+json`
   - Body: `{"ref":"main"}`
3. GitHub の schedule はそのまま残す（外部 cron が止まったときの保険）。

## アメダス Record Hunter（観測記録の発見）

気象庁「最新の気象データ」CSV の極値更新フラグから、観測史上1位・月別1位・歴代TOP3級の観測値を拾い、既存の ntfy トピックへ `[記録]` 付きで通知する。判定はすべてコードで行い、自動投稿はしない。設計は `アメダス Record Hunter 開発引き継ぎ書.md`。

- `.github/workflows/record_hunter.yml` が20分ごとに `python3 -m record_hunter run` を実行。緊急XML監視（`watch.yml`）とは workflow・timeout・State を分離している。
- State（通知済み・順位キャッシュ）は `record-hunter-state` ブランチに Actions が自動 commit する。ローカル実行時は `state/record_hunter/`（gitignore）。
- 気象庁へのアクセスは CSV 数本＋今日の「更新状況」ページ＋候補地点の順位ページだけ。全地点をクロールしない。
- 通知レベル: A=観測史上1位更新（即時・個別）、B=月別1位・1位タイ・歴代2〜3位・都道府県クラスター（都道府県×要素でまとめ）。同じ格では再通知しない。

実行間隔: GitHub の schedule（20分ごと）は混雑時に数時間遅れる。`watch.yml` と同じく cron-job.org から `workflow_dispatch` を叩くと10分間隔になる（URL は `.../actions/workflows/record_hunter.yml/dispatches`、トークン・ヘッダ・Body は下の「実行間隔を確実に10分にする」と同じ。CSV は要素ごとの更新周期（気温60分・降水10分）より短い間隔では再取得しない）。

```bash
python3 -m record_hunter dry-run                       # 通知せず、何を通知するかを表示
python3 -m record_hunter snapshot --out tests/fixtures  # 今日の CSV・更新状況ページを Fixture 化
python3 -m record_hunter replay --date 2026-09-14       # Fixture から再生（通知しない）
python3 -m pytest -q tests
```

## 依存

Python 3.12（標準ライブラリのみ）。テストは pytest。`fetch_press.py` の PDF 本文取得を手元で使うときだけ poppler（pdftotext）が要る。
