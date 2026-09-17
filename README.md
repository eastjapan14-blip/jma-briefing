# jma-briefing

気象庁の発表を、防災YouTube向けの台本と pptx にする。

```
scripts/fetch_feed.py    防災情報XMLフィードを監視し、動画候補を段階(A/B/C)つきで一覧
scripts/fetch_report.py  発表XMLを素材Markdown(source.md)に変換
scripts/fetch_images.py  実況天気図PNG・台風経路図・雨雲レーダーを取得（Chrome headless）
scripts/build_pptx.py    台本(script.md)から16:9のpptxを生成（ナレーションはノート欄）
material/                素材・台本・pptx（日付_slug ごと）
state/seen.json          確認済み候補
.claude/commands/briefing.md   Claude Codeの /briefing コマンド
```

## 監視と通知（GitHub Actions + ntfy）

- `.github/workflows/watch.yml` が10分ごとに `scripts/notify.py` を実行し、新しい候補を ntfy.sh のトピックへ送る。Mac の起動は不要。
- iPhone の ntfy アプリでトピック（GitHub の Secret `NTFY_TOPIC`）を購読する。通知本文に `/briefing <URL>` が入っているので、Claude Code に貼るだけで制作に入れる。
- 重複防止は ntfy の履歴（24時間）で行うため、状態ファイルは不要。
- GitHub の混雑時は実行が数分〜数十分遅れることがある。

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
4. pptx を Keynote（iPhone可）または PowerPoint で開き、ノート欄を読みながら録音して動画に書き出す

依存: Python 3.9+、python-pptx、Pillow（`pip3 install --user python-pptx pillow`）、Google Chrome（図の取得）
