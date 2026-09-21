# jma-briefing

気象庁の発表を、防災YouTube向けの台本と pptx にする。

```
scripts/fetch_feed.py    防災情報XMLフィードを監視し、動画候補を段階(A/B/C)つきで一覧
scripts/fetch_report.py  発表XMLを素材Markdown(source.md)に変換
scripts/fetch_images.py  実況天気図PNG・台風経路図・雨雲レーダーを取得（Chrome headless）
scripts/fetch_press.py   報道発表資料（本文＋PDF全文）を press.md に。--list で最近の一覧
scripts/transcribe.py    公式YouTubeの記者会見を mlx-whisper で文字起こし（transcript.md）
scripts/notify.py        新着候補（XML・報道発表・記者会見動画）を ntfy へ通知
scripts/deliver.py       pptx と台本を iCloud Drive/jma-briefing へコピー（iPhone の Keynote 用）
scripts/build_pptx.py    台本(script.md)から16:9のpptxを生成（ナレーションはノート欄）
record_hunter/           アメダス Record Hunter（記録級の観測値を検出して ntfy へ候補通知）
tools/build_etrn_index.py  地点索引（record_hunter/data/etrn_index.json）を一度だけ生成
tests/                   pytest（Fixture は tests/fixtures/<日付>/）
material/                素材・台本・pptx（日付_slug ごと）
state/seen.json          確認済み候補
.claude/commands/briefing.md   Claude Codeの /briefing コマンド
```

## 監視と通知（GitHub Actions + ntfy）

- `.github/workflows/watch.yml` が10分ごとに `scripts/notify.py` を実行し、新しい候補を ntfy.sh のトピックへ送る。Mac の起動は不要。
- iPhone の ntfy アプリでトピック（GitHub の Secret `NTFY_TOPIC`）を購読する。通知本文に `/briefing <URL>` が入っているので、Claude Code に貼るだけで制作に入れる。
- 通知は2種類。即時（段階A/C/D、全般気象情報、地方単位の線状降水帯）は1件1通、地方・府県気象情報や土砂災害警戒情報は1回の実行分を事象ごとにまとめて1通。
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

## アメダス Record Hunter（X 投稿候補の発見）

気象庁「最新の気象データ」CSV の極値更新フラグから、観測史上1位・月別1位・歴代TOP3級の観測値を拾い、既存の ntfy トピックへ `[記録]` 付きで通知する。判定はすべてコードで行い、自動投稿はしない。設計は `アメダス Record Hunter 開発引き継ぎ書.md`。

- `.github/workflows/record_hunter.yml` が20分ごとに `python3 -m record_hunter run` を実行。緊急XML監視（`watch.yml`）とは workflow・timeout・State を分離している。
- State（通知済み・順位キャッシュ）は `record-hunter-state` ブランチに Actions が自動 commit する。ローカル実行時は `state/record_hunter/`（gitignore）。
- 気象庁へのアクセスは CSV 数本＋今日の「更新状況」ページ＋候補地点の順位ページだけ。全地点をクロールしない。
- 通知レベル: A=観測史上1位更新（即時・個別）、B=月別1位・1位タイ・歴代2〜3位・都道府県クラスター（都道府県×要素でまとめ）。同じ格では再通知しない。

```bash
python3 -m record_hunter dry-run                       # 通知せず、何を通知するかを表示
python3 -m record_hunter snapshot --out tests/fixtures  # 今日の CSV・更新状況ページを Fixture 化
python3 -m record_hunter replay --date 2026-09-14       # Fixture から再生（通知しない）
python3 -m pytest -q tests
```

## セッション構成

| セッション | 役割 |
|---|---|
| 監視 | GitHub Actions（Claude 不要） |
| 制作 | 動画1本ごとに新規セッションで `/briefing <URL>` |
| 改善 | スクリプトやルールの修正 |

## 1本作る流れ

1. `/briefing 候補` で候補を見る（または `python3 scripts/fetch_feed.py`）
2. `/briefing <XMLのURL> ...` で素材化 → 図の取得 → 台本 → pptx まで自動
3. 台本末尾の照合チェック表で数値・地名・時刻を確認する
4. iPhone の「ファイル」→ iCloud Drive → jma-briefing の pptx を Keynote で開き、ノート欄を読みながら録音して動画に書き出す

依存: Python 3.9+、python-pptx、Pillow、mlx-whisper（`pip3 install --user python-pptx pillow mlx-whisper`）、yt-dlp、ffmpeg、poppler（pdftotext）、Google Chrome（図の取得）
