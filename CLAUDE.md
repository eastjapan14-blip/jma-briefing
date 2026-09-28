# jma-briefing 運用ルール

気象庁の発表（記者会見・防災気象情報）を、防災YouTube向けの台本とスライドに変換するプロジェクト。

## 絶対に守る線（気象業務法）

- 主張は気象庁の発表内容の範囲に収める。発表にない量的・地域的な見立て（「私は〇〇mmと予想」「この地域は大丈夫」）は書かない。
- 許される表現: 発表の引用、用語や仕組みの一般説明、発表に基づく行動の呼びかけ、発表文の「どこを読むべきか」の解説。
- 数値・地名・時刻は必ず `source.md` の原文どおりにする。丸めや言い換えをしない。
- 不確実性の表現（「可能性がある」「見込み」）は原文のニュアンスを落とさず残す。

## 台本の型（script.md）

- 書式は `scripts/build_pptx.py` の冒頭コメントを参照。`## 見出し` が1枚、`- ` がスライド文、`> ` がナレーション。表は `| a | b |`、図は `![出典](images/x.png)`、定義表は `[ref: rain 30]`。
- スライドの種別を `[type: ...]` で分ける。`jma`（発表内容）と `action`（行動指針）を視覚的に必ず区別する。
- 文字は本文・表・帯ラベルとも 28pt 以上（出典と注記のみ小さくてよい）。箇条書きは1枚4項目まで。足りなければ枚数を増やす。
- 数値の羅列は表にする。発表文をそのまま箇条書きにしない。
- 図を積極的に使う。台風なら「いま」に実況天気図、「進路」に台風経路図は必須。大雨なら雨雲レーダー。`scripts/fetch_images.py` で取得する。
- 発表値がどの段階かを定義表で示す（雨 `rain`、風 `wind`、波 `wave`、台風の強さ `typhoon_strength`、大きさ `typhoon_size`）。該当行が強調される。
- 最後の1枚は「今後の情報は気象庁の発表を確認してください」。気象庁の次回発表時刻は伝えるが、動画の続報は約束しない。
- 構成の基本: 表紙 → 結論（誰が・いつまでに・何をする）→ 発表の要点 → 行動指針 → 次の更新タイミング。
- ナレーションは話し言葉。1枚あたり40〜90秒（120〜270文字）を目安に、尺は情報量に合わせる。
- 記者会見（段階A）の質疑は、視聴者の行動に関わる質問だけ採用する。的を外した質問は入れない。
- 台本の末尾に `---` 行を置き、その下に「照合チェック表」（数値・地名・時刻を原文と並べた表）を付ける。`---` より下はスライドにならない。

## 段階

| 段階 | トリガー | 型 |
|---|---|---|
| A | 記者会見（報道発表資料＋公式YouTube） | 本編 |
| B | 線状降水帯の半日前予測、台風、警報級の可能性 | 速報テンプレ |
| C | 特別警報、気象防災速報、記録的短時間大雨 | 一言動画 |
| D | 長期予報（全般1か月・3か月・暖候期・寒候期予報） | 定例解説 |

段階Dの型（8枚）: 表紙 → 結論（地方ごとのカード図 `conclusion.png`。気温・降水量・日照時間の札と天気アイコン）→ 天気の傾向（発表文をアイコンの並びで示す `weather.png`）→ 地方ごとの見通し（気温・降水量・日照時間の帯グラフ `summary.png`）→ 期間ごとの気温（マス目 `weekly_grid.png` と地方別パネル `weekly_region.png`。1か月予報は週ごと、3か月予報は月ごと）→ 生活・防災の観点（アイコン付きカード `life.png`。発表文にある範囲で）→ 次回発表。確率表のスライドは置かない（図に数値が入る）。確率の意味（平年の3区分が各33%で、それより高い階級に注目）は結論のナレーションで一度だけ説明する。図は `scripts/plot_seasonal.py` で生成し、カードの文言は `figures.json` に書く。色は気象庁の平年偏差図に合わせる（気温=橙/青、降水量=青緑/茶、日照=黄/灰）。

## コマンド

```bash
python3 scripts/fetch_feed.py                 # 候補一覧（未確認のみ）
python3 scripts/fetch_report.py <URL>... --slug <名前>   # 素材化
python3 scripts/fetch_press.py <報道発表URL> --out material/<dir>   # 報道資料（PDF全文）→ press.md
python3 scripts/transcribe.py <YouTube URL> --out material/<dir>   # 記者会見の文字起こし → transcript.md
python3 scripts/fetch_images.py --out material/<dir>/images weather_map typhoon radar  # 図の取得
python3 scripts/plot_seasonal.py material/<dir>/source.md --out material/<dir>/images --periods "9/26〜10/2,..." --cards material/<dir>/figures.json  # 季節予報の図
python3 scripts/build_pptx.py material/<dir>/script.md   # pptx生成
python3 scripts/render_map.py --points <lat,lon>... --pref <県名> --out material/<dir>/images/map.png   # ショート用の地形図（地理院 標高タイル）
python3 scripts/build_short.py material/<dir>/short.json   # ショート用の縦型 HTML＋ナレーション台本（書式はスクリプト冒頭）
python3 scripts/fetch_surface.py --time 2026-09-28T06:00 --out material/<dir>/raw   # 地上実況図 XML → 前線・等圧線の JSON（ショートの天気図場面 synoptic 用。3時間ごと、数日分のみ取得可）
python3 scripts/render_map.py --bbox 24.0,122.9,45.6,146.2 --size 1080x900 --inner 60,40,900,860 --no-borders --regions --out material/<dir>/images/japan.png   # 長期予報ショート用の全国図（地方区分入り）
python3 scripts/seasonal_short.py material/<dir>/source.md --out material/<dir_short>/short.json --periods "9/26〜10/2,..."   # 長期予報ショートの short.json 骨組み（TODO を埋める）
python3 -m record_hunter dry-run                # アメダス記録候補の確認（通知しない）
python3 -m record_hunter shorts [--date YYYY-MM-DD]   # Shorts 候補の一覧（◎○×・理由・型。State ブランチを読む）
python3 -m pytest -q tests                      # Record Hunter のテスト
```
