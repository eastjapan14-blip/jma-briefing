# jma-briefing 運用ルール

気象庁の発表とアメダスの観測記録を見張り、新着を ntfy で iPhone に通知するプロジェクト。動画・スライド制作の機能は 2026-11 に削除した。

## 守ること

- 公開リポジトリ。ntfy のトピック名・トークン・個人のメールアドレスやパスなど、知られて困る値はファイルにもコミットメッセージにも書かない。トピック名は GitHub の Secret `NTFY_TOPIC` から読む。
- コミットのメールは GitHub の匿名アドレス（users.noreply.github.com）を使う（このリポジトリの git config に設定済み）。
- 気象庁へのアクセスは、各データの更新周期より短い間隔で取り直さない。全地点のクロールはしない。
- 通知は人が読むためのもの。自動投稿はしない。

## コマンド

```bash
NTFY_TOPIC=xxx python3 scripts/notify.py --dry-run   # 防災情報の通知内容を確認（送らない）
python3 scripts/fetch_feed.py                 # 候補一覧
python3 scripts/fetch_press.py --list         # 最近の報道発表
python3 -m record_hunter dry-run              # アメダス記録候補の確認（通知しない）
python3 -m record_hunter recent [--days 3]    # 最近の記録を珍しさの順に一覧（State ブランチを読む）
python3 -m pytest -q tests                    # テスト
```
