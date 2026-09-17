---
description: 気象庁発表のURL（XML／報道発表／YouTube。または「候補」）から台本とpptxを作る
---
引数: $ARGUMENTS （URLを1つ以上。空または「候補」なら候補一覧を出して止まる）

URLの種類で素材化の手順が変わる。複数あれば同じ出力フォルダにまとめる。
- `data.jma.go.jp/developer/xml/...`（発表XML）→ `python3 scripts/fetch_report.py <URL>... --out <フォルダ>`
- `jma.go.jp/jma/press/...`（報道発表）→ `python3 scripts/fetch_press.py <URL> --out <フォルダ>`（PDF全文が press.md に入る）
- `youtube.com/watch?v=...`（記者会見）→ `python3 scripts/transcribe.py <URL> --out <フォルダ>`（数分かかる。transcript.md ができる）

手順:
1. 引数が空か「候補」なら `python3 scripts/fetch_feed.py` と `python3 scripts/fetch_press.py --list` を実行し、候補を段階つきで一覧して終了する。
2. 出力フォルダ名は `material/YYYYMMDD_<内容を表す短い英字>`。上の表に従って素材化し、`source.md` / `press.md` / `transcript.md` を読む。
3. 図を取る。台風なら `python3 scripts/fetch_images.py --out <フォルダ>/images weather_map typhoon --center <台風中心の緯度,経度> --zoom 6`、大雨・線状降水帯なら `weather_map radar --center <対象地域> --zoom 7`。段階Cは図なしでもよい。出典は `images/images.md` に出る。
4. CLAUDE.md のルールに従い、同じフォルダに `script.md` を書く。図・表・定義表（[ref: ...]）を使い、28pt で収まるよう1枚4項目までにする。
   - 段階A（記者会見）: 報道資料の要点 → 会見での強調点 → 質疑のうち視聴者の行動に関わるもの（transcript.md の [mm:ss] を照合表に残す）→ 行動指針。尺は内容量に合わせる。数値は必ず press.md か source.md で照合し、文字起こしだけを根拠にしない。
   - 段階B: 表紙、結論、発表の要点（図・表）、定義表、行動指針、今後の情報、の8〜12枚。
   - 段階C: 表紙、発表内容（定義表）、行動指針、の3枚。
5. `python3 scripts/build_pptx.py <フォルダ>/script.md` を実行し、「注意:」が出たら台本を直して再実行する。
6. YouTube用のタイトル案3つと概要欄の文面を `meta.md` に書く。
7. `python3 scripts/deliver.py <フォルダ>` で iCloud Drive にコピーする（iPhone の Keynote で開くため）。
8. 台本末尾の照合チェック表、ナレーションの目安時間、iCloud 上のファイル名を報告する。
