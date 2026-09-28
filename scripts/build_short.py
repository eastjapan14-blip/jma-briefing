#!/usr/bin/env python3
"""ショート動画用の縦型 HTML（1080x1920）と ナレーション台本を short.json から生成する。

使い方:
  python3 scripts/build_short.py material/<dir>/short.json
    → material/<dir>/short.html          ブラウザで開き、Space/→/クリックで進める。画面収録しながら読む
    → material/<dir>/short_narration.md  ナレーション（場面ごと）＋照合チェック表

操作: Space / → / クリック = 次の場面、← = 前、R = 最初から。
      URL に ?auto=1 を付けると各場面の dur 秒で自動送り（将来の mp4 自動生成用）。

short.json の書式:
  {
   "title": "...", "date": "2026-09-21", "date_label": "2026.09.21", "brand": "気象予報士なべ",
   "source": {"label": "気象庁 アメダス 観測史上1位の値 更新状況（9月21日）", "url": "https://..."},
   "footer": "アメダスの速報値です。最新の値は気象庁で確認してください",   ← 全場面の注記欄に出る
   "scenes": [
     {"type": "intro", "dur": 13,                         ← ズーム導入（表紙）。全国 → 地方 → 局地の地形図に寄ってから文字が出る
      "layers": ["images/zoom_japan.png", "images/zoom_kanto.png", "images/zoom_local.png"],   ← render_map.py で同じ注目点を --at に置いて描く
      "focus": {"lat": 35.3967, "lon": 140.1483, "label": "牛久（うしく）", "sub": "千葉県市原市"},
      "hold": 0.6, "zoom_sec": 3.4, "cue": "プロンプターに出す合図",
      "kicker": "...", "headline": "...", "label": "日降水量", "value": 341.0, "unit": "mm", "badge": "...", "badge_sub": "...", "narration": "..."},
     {"type": "hook", "dur": 10,                          ← 地図なしの表紙 "kicker": "9月21日 千葉県市原市", "place": "牛久（うしく）",
      "headline": "30年ぶりの記録更新",          ← いちばん強い一言。無ければ place が大きく出る
      "label": "日降水量", "value": 341.0, "unit": "mm",
      "badge": "観測史上1位", "badge_sub": "統計開始 1978年", "meta": "任意の等幅1行", "narration": "..."},
     {"type": "rank", "heading": "1996年の記録を越えた", "sub": "...", "unit": "mm",
      "bars": [{"rank": 1, "value": 341.0, "date": "2026/9/21", "today": true}, {"rank": 2, ...}],
      "takeaway": "＋20.0mm、30年ぶりの更新", "narration": "..."},
        ← today 以外の棒が先に伸び、従来1位の位置に破線。today の棒が遅れて伸びて越え、takeaway が出る
     {"type": "map", "heading": "同じ日、千葉県では", "map": "images/map.png",
      "points": [{"name": "牛久", "lat": 35.3967, "lon": 140.1483, "value": "341.0", "rank": "1位", "hero": true, "side": "left"}, ...],   ← side: left/right/above/below
      "takeaway": "県内7地点で観測史上1位", "narration": "..."},
        ← map.png と同名の map.json（scripts/render_map.py が出力）から地点の画素位置と縮尺を計算。地点は順に点灯
     {"type": "track", "heading": "予想進路", "map": "images/track.png", "scale_km": 500,   ← 台風の進路図（地形図＋SVG）
      "past": [[lat, lon], ...], "current": {"lat":.., "lon":.., "label": "27日23時", "sub": "945hPa", "storm_km": 85, "gale": {"lat":.., "lon":.., "km": 222}},
      "points": [{"lat":.., "lon":.., "r_km": 46, "storm_km": 140, "label": "28日9時", "side": "below"}, ...],   ← 予報円 r_km、暴風警戒域 = r_km+storm_km
      "takeaway": "...", "narration": "..."},
     {"type": "synoptic", "heading": "...", "map": "images/synoptic.png", "surface": "raw/surface_2026092806.json",   ← 天気図（地上実況図）
      "time_label": "28日6時 地上実況図", "front_label": {"text": "停滞前線", "lat": .., "lon": .., "side": "below"},
      "arrows": [{"path": [[lat, lon], ...], "label": "暖かく湿った空気"}],      ← 気象庁の解説にある流れだけを模式的に描く
      "focus": {"lat": .., "lon": .., "label": "呉", "sub": "68.0mm", "side": "left"}, "takeaway": "...", "narration": "..."},
        ← surface は scripts/fetch_surface.py の出力。等圧線 → 前線（西から描き出す）→ 矢印 → 地点の順に出る
     {"type": "scale", "heading": "...", "ref": "typhoon_strength" | "typhoon_size" | "rain", "value": 50,   ← 気象庁の階級の帯に発表値の印
      "stats": [{"k": "中心気圧", "v": "945", "u": "hPa"}, ...], "narration": "..."},
     {"type": "figure", "heading": "...", "image": "images/typhoon_map.png", "caption": "...", "credit": "気象庁 台風経路図"},   ← 気象庁の図をそのまま
     {"type": "cards", "heading": "...", "cards": [{"title": "船橋", "value": "290.0mm", "sub": "1位"}, ...]},   ← 一覧（行＋棒）
     {"type": "text" | "close", "heading": "...", "lines": ["...", "..."], "narration": "..."}
   ],
   "check": [["項目", "動画の値", "原文の値", "確認"], ...],   ← 照合チェック表（任意。無ければ数値から自動生成）
   "cta": {"next": "28日5時頃", "lines_before": ["..."], "narration_before": "..."}   ← 共通CTA（scripts/short_cta.json）を最後に付ける。false で付けない
  }
  takeaway: 音を出さずに見る人向けの結論の一行。どの場面にも付けられる（下部に大きく出る）。
  tone: jma（気象庁の発表・観測値。シアン）/ action（行動指針。橙）/ fun（気象の楽しみ。緑）。省略時は jma。
  安全域: 上 200 / 下 500 / 右 200 px は Shorts・TikTok の UI が重なるので本文を置かない（見出しだけ右に食い込める）。
"""
import argparse, base64, html, json, math, re, sys
from pathlib import Path

TONE = {
    "jma":    {"accent": "#5EE7FF", "label": "気象庁の観測値"},
    "action": {"accent": "#FF7A45", "label": "今すぐの行動"},
    "fun":    {"accent": "#8CF5B0", "label": "きょうの数字"},
}

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=IBM+Plex+Mono:wght@500&display=swap');
:root{--w:1080px;--h:1920px;--bg:#0B0F14;--fg:#F3F5F7;--muted:#8B95A3;--line:rgba(255,255,255,.14);
 --jp:"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
 --num:"Barlow Condensed","Helvetica Neue",Arial,sans-serif;
 --mono:"IBM Plex Mono","SF Mono",Menlo,monospace;
 --ease:cubic-bezier(.16,1,.3,1)}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#000;overflow:hidden;font-family:var(--jp);color:var(--fg)}
#wrap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:24px;padding:16px}
#frame{position:relative;flex:none;outline:1px solid #2a2f36}
#stage{position:absolute;left:0;top:0;width:var(--w);height:var(--h);transform-origin:top left;overflow:hidden;background:var(--bg)}
#iso{position:absolute;inset:-10%;width:120%;height:120%;opacity:.55;animation:drift 60s linear infinite alternate}
@keyframes drift{from{transform:translate(0,0)}to{transform:translate(-60px,40px)}}
.scene{position:absolute;inset:0;display:none;flex-direction:column;padding:300px 200px 0 80px}
.scene.active{display:flex}
/* 安全域: 上 200 / 下 500 / 右 200 は Shorts・TikTok の UI が重なるため空ける。本文は y=300〜1300、注記は 1316〜1400 */
.top{position:absolute;left:80px;right:200px;top:200px;display:flex;justify-content:space-between;align-items:flex-end;
 font-family:var(--mono);font-size:26px;letter-spacing:.06em;color:var(--muted);padding-bottom:16px;border-bottom:1px solid var(--line)}
.top b{color:var(--fg);font-weight:500}
.top .tone{display:inline-flex;align-items:center;gap:14px}
.top .tone i{width:12px;height:12px;background:var(--accent)}
.foot{position:absolute;left:80px;right:200px;top:1316px;padding-top:16px;border-top:1px solid var(--line);
 font-family:var(--mono);font-size:26px;line-height:1.6;color:var(--muted);letter-spacing:.02em}
.foot .src{color:#5E6875}
.meta{font-family:var(--mono);font-size:28px;color:var(--muted);letter-spacing:.04em;margin-bottom:28px}
.place{font-size:80px;font-weight:800;line-height:1.15;letter-spacing:.01em;margin-right:-120px}
.place small{display:block;font-size:46px;font-weight:600;color:var(--muted);margin-bottom:10px;letter-spacing:.02em}
.label{margin-top:48px;font-size:50px;font-weight:600;color:var(--muted);display:flex;align-items:center;gap:20px}
.label:before{content:"";width:40px;height:2px;background:var(--accent)}
.big{display:flex;align-items:baseline;gap:14px;margin-top:8px;font-family:var(--num);font-weight:800;line-height:1;color:var(--fg)}
.big .num{font-size:340px;letter-spacing:-.01em;display:inline-flex}
.big .unit{font-size:96px;font-weight:600;color:var(--muted);letter-spacing:.02em}
.dg{display:inline-block;height:1em;overflow:hidden;vertical-align:top}
.dg .strip{display:flex;flex-direction:column;transform:translateY(0);transition:transform .9s var(--ease)}
.dg .strip span{height:1em;line-height:1;display:block}
.tag{margin-top:48px;display:inline-flex;align-items:stretch;border:2px solid var(--accent);font-size:56px;font-weight:800;line-height:1;
 opacity:0;transform:translateY(20px);transition:opacity .5s var(--ease) .9s,transform .6s var(--ease) .9s}
.tag b{background:var(--accent);color:#0B0F14;padding:22px 30px;font-size:44px;font-weight:800;letter-spacing:.04em;display:flex;align-items:center}
.tag span{padding:22px 34px;font-size:44px;font-weight:600;color:var(--muted);display:flex;align-items:center}
.in .tag{opacity:1;transform:none}
.heading{font-size:76px;font-weight:800;line-height:1.2;letter-spacing:.01em;margin-right:-120px}
.sub{margin-top:22px;font-family:var(--mono);font-size:36px;color:var(--muted);letter-spacing:.03em;line-height:1.5}
.rows{margin-top:56px;display:flex;flex-direction:column}
.row{display:grid;grid-template-columns:110px 1fr 250px;align-items:center;gap:20px;padding:22px 0;border-top:1px solid var(--line);
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.row:last-child{border-bottom:1px solid var(--line)}
.in .row{opacity:1;transform:none}
.s-cards .row{grid-template-columns:200px 1fr 250px;padding:16px 0}
.s-cards .rows{margin-top:40px}
.s-cards .row .d{margin-top:10px}
.row .rk{font-family:var(--num);font-size:62px;font-weight:600;color:var(--muted);letter-spacing:.02em}
.row .rk small{font-size:34px;margin-left:2px}
.row .nm{font-size:44px;font-weight:700}
.row .bar{position:relative;height:10px;background:rgba(255,255,255,.08)}
.row .bar i{position:absolute;left:0;top:0;bottom:0;width:100%;background:#4A5563;transform:scaleX(0);transform-origin:left;transition:transform 1s var(--ease)}
.in .row .bar i{transform:scaleX(var(--pct))}
.row .d{font-family:var(--mono);font-size:36px;color:var(--muted);margin-top:14px;letter-spacing:.03em}
.row .v{font-family:var(--num);font-size:70px;font-weight:800;text-align:right;letter-spacing:.01em;font-variant-numeric:tabular-nums}
.row .v small{font-size:36px;color:var(--muted);font-weight:600;margin-left:4px}
.row.today .rk,.row.today .v{color:var(--accent)}
.row.today .bar i{background:var(--accent)}
.row.today .nm:after,.row.today .rk:after{content:""}
.row .new{font-family:var(--num);font-size:26px;letter-spacing:.14em;color:var(--bg);background:var(--accent);padding:4px 10px;margin-left:16px;vertical-align:middle;font-weight:800}
.note{margin-top:52px;padding:30px 36px;border-left:4px solid var(--accent);background:rgba(255,255,255,.04);font-size:42px;line-height:1.45;font-weight:600;
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease) .9s,transform .6s var(--ease) .9s}
.in .note{opacity:1;transform:none}
.lines{margin-top:56px;display:flex;flex-direction:column}
.line{display:grid;grid-template-columns:90px 1fr;gap:20px;padding:34px 0;border-top:1px solid var(--line);font-size:54px;line-height:1.4;font-weight:700;
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.line:last-child{border-bottom:1px solid var(--line)}
.line .n{font-family:var(--num);font-size:56px;font-weight:600;color:var(--accent);line-height:1.25}
.in .line{opacity:1;transform:none}
/* 結論の一行（音を出さない視聴者向け） */
.take{position:absolute;left:80px;right:200px;bottom:632px;font-size:60px;font-weight:800;line-height:1.25;letter-spacing:.01em;
 opacity:0;transform:translateY(16px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.take:before{content:"";display:block;width:64px;height:4px;background:var(--accent);margin-bottom:18px}
.in .take{opacity:1;transform:none}
/* 順位: 従来1位の位置に破線。今回の棒が遅れて伸びて越える */
.row .bar .mark{position:absolute;top:-16px;bottom:-16px;left:var(--mk);border-left:3px dashed rgba(255,255,255,.55);opacity:0;transition:opacity .4s var(--ease) .7s}
.in .row .bar .mark{opacity:1}
.s-rank .row.today .bar i{transition-duration:1.4s}
/* 地図 */
.s-map .heading,.s-track .heading{font-size:68px;white-space:nowrap}
.mapwrap{position:absolute;left:0;right:0;top:470px;height:830px;overflow:hidden}
.mapwrap img{position:absolute;left:0;top:0;width:1080px;height:830px;display:block}
.mapfade{position:absolute;left:0;right:0;bottom:0;height:240px;background:linear-gradient(rgba(11,15,20,0),var(--bg) 78%);pointer-events:none}
.pt{position:absolute;width:0;height:0;opacity:0;transition:opacity .35s var(--ease)}
.in .pt{opacity:1}
.pt i{position:absolute;left:-11px;top:-11px;width:22px;height:22px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 5px rgba(11,15,20,.85)}
.pt.hero i{left:-15px;top:-15px;width:30px;height:30px;background:#fff;box-shadow:0 0 0 6px rgba(11,15,20,.85),0 0 24px rgba(255,255,255,.5)}
.pt:after{content:"";position:absolute;left:-11px;top:-11px;width:22px;height:22px;border-radius:50%;border:2px solid var(--accent);opacity:0;transform:scale(1)}
.in .pt:after{animation:ping 1.1s var(--ease) forwards;animation-delay:inherit}
@keyframes ping{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(4.5)}}
.pt .lb{position:absolute;left:26px;top:0;transform:translateY(-50%);white-space:nowrap;font-size:44px;font-weight:700;line-height:1;
 text-shadow:0 2px 10px #000,0 0 4px #000}
.pt .lb b{font-family:var(--num);font-size:54px;font-weight:800;margin-left:12px;letter-spacing:.01em}
.pt .lb em{font-style:normal;font-family:var(--mono);font-size:34px;color:#C9D1DA;margin-left:12px}
.pt.above .lb{left:50%;top:-28px;transform:translate(-50%,-100%)}
.pt.below .lb{left:50%;top:30px;transform:translate(-50%,0)}
.pt.left .lb{left:auto;right:26px}
.pt.hero .lb{font-size:50px}
.scalebar{position:absolute;left:80px;top:24px;height:10px;border:2px solid rgba(255,255,255,.6);border-top:none;font-family:var(--mono);font-size:28px;color:var(--muted)}
.scalebar span{position:absolute;left:0;top:-40px;white-space:nowrap}
/* ズーム導入: 全面の地図 → 注目点へ寄る → 影を掛けて文字 */
.s-intro{padding:0}
.s-intro .top,.s-intro .foot{z-index:3}
.zoom{position:absolute;inset:0;overflow:hidden}
.zoomw{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0;will-change:transform;animation-timing-function:linear;animation-fill-mode:forwards;animation-play-state:paused}
.in .zoomw{animation-play-state:running}
.ly{position:absolute;display:block;animation-timing-function:linear;animation-fill-mode:forwards;animation-play-state:paused}
.in .ly{animation-play-state:running}
.ly.lf{animation-duration:inherit;animation-delay:inherit}
.focus{position:absolute;width:0;height:0;z-index:2;opacity:0;transition:opacity .3s var(--ease) var(--t)}
.in .focus{opacity:1}
.focus i{position:absolute;left:-16px;top:-16px;width:32px;height:32px;border-radius:50%;background:#fff;box-shadow:0 0 0 6px rgba(11,15,20,.85),0 0 30px rgba(255,255,255,.6)}
.focus:before,.focus:after{content:"";position:absolute;left:-16px;top:-16px;width:32px;height:32px;border-radius:50%;border:3px solid var(--accent);opacity:0}
.in .focus:before{animation:ping 1.4s var(--ease) var(--t) forwards}
.in .focus:after{animation:ping 1.4s var(--ease) calc(var(--t) + .5s) forwards}
.focus .lb{position:absolute;right:30px;top:0;transform:translateY(-50%);white-space:nowrap;font-size:52px;font-weight:800;line-height:1.15;text-align:right;text-shadow:0 2px 12px #000,0 0 6px #000}
.focus .lb em{display:block;font-style:normal;font-size:34px;font-weight:600;color:#C9D1DA}
.shade{position:absolute;inset:0;z-index:1;opacity:0;transition:opacity .9s var(--ease);
 background:linear-gradient(180deg,var(--bg) 0%,rgba(11,15,20,.96) 40%,rgba(11,15,20,.6) 55%,rgba(11,15,20,0) 66%,rgba(11,15,20,0) 80%,var(--bg) 96%)}
.in .shade{opacity:1}
.itext{position:absolute;left:80px;right:80px;top:300px;z-index:2}
.itext>*{opacity:0;transform:translateY(22px);transition:opacity .6s var(--ease),transform .7s var(--ease)}
.in .itext>*{opacity:1;transform:none}
.itext .place{font-size:84px}
.itext .big .num{font-size:260px}
/* 進路図 */
.mapwrap svg{position:absolute;left:0;top:0;width:1080px;overflow:visible}
.tr-past{fill:none;stroke:rgba(255,255,255,.35);stroke-width:3;stroke-dasharray:2 10;stroke-linecap:round}
.tr-fc{fill:none;stroke:#fff;stroke-width:4;stroke-linejoin:round;transition:stroke-dashoffset 2.6s linear .6s}
.in .tr-fc{stroke-dashoffset:0!important}
.tr-storm{fill:rgba(255,92,92,.25);stroke:#FF5C5C;stroke-width:3}
.tr-gale{fill:rgba(242,177,52,.14);stroke:#F2B134;stroke-width:3}
.tr-prob{fill:rgba(255,255,255,.07);stroke:#fff;stroke-width:2.5;stroke-dasharray:12 9}
.tr-warn{fill:none;stroke:#FF5C5C;stroke-width:2;stroke-dasharray:5 9;opacity:.85}
.tr-pt{fill:#fff}
.tr-cur{fill:#fff;stroke:#0B0F14;stroke-width:5}
.fg{opacity:0;transition:opacity .45s var(--ease) var(--d)}
/* 天気図 */
.syn-iso{fill:none;stroke:rgba(255,255,255,.26);stroke-width:2}
.syn-isolbl{font-family:var(--num);font-size:30px;font-weight:600;fill:rgba(255,255,255,.55)}
.syn-fr{clip-path:inset(0 100% 0 0);transition:clip-path 2s cubic-bezier(.45,0,.55,1) .5s}
.in .syn-fr{clip-path:inset(0 0 0 0)}
.syn-arrow{fill:none;stroke:rgba(255,138,76,.9);stroke-width:18;stroke-linecap:round;stroke-linejoin:round;transition:stroke-dashoffset 1.2s var(--ease) 2.4s}
.in .syn-arrow{stroke-dashoffset:0!important}
.syn-head{fill:rgba(255,138,76,.95);opacity:0;transition:opacity .3s var(--ease) 3.3s}
.in .syn-head{opacity:1}
.syn-time{position:absolute;left:80px;top:22px;font-family:var(--mono);font-size:28px;color:#C9D1DA}
.pt.warm .lb{color:#FFB08A}
.in .fg{opacity:1}
.pt.nodot i,.pt.nodot:after{display:none}
.pt .lb em{display:inline}
.pt.nodot .lb em{display:block;margin:6px 0 0;font-size:30px}
.legend{position:absolute;right:200px;top:22px;display:flex;gap:26px;font-family:var(--mono);font-size:28px;color:#C9D1DA}
.legend span{display:inline-flex;align-items:center;gap:10px}
.legend i{width:26px;height:26px;border-radius:50%;border:3px solid var(--c);background:var(--bg-c)}
.ring{position:absolute;z-index:0;border-radius:50%;border:3px solid #fff;transform:translate(-50%,-50%);opacity:0;transition:opacity .5s var(--ease)}
.in .ring{opacity:1}
/* 階級の帯 */
.stats{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:36px}
.stat{padding:18px 26px;border:1px solid var(--line);opacity:0;transform:translateY(16px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.in .stat{opacity:1;transform:none}
.stat .k{font-size:34px;color:var(--muted);font-weight:600}
.stat .v{font-family:var(--num);font-size:84px;font-weight:800;line-height:1.05;letter-spacing:.01em}
.stat .v small{font-size:38px;color:var(--muted);margin-left:8px;font-weight:600;font-family:var(--num)}
.bandlbl{margin-top:44px;font-size:34px;color:var(--muted);font-weight:600}
.band{position:relative;margin-top:100px;height:112px;display:flex}
.seg{position:relative;flex:var(--f);border:1px solid var(--line);border-left:none;display:flex;align-items:center;justify-content:center;font-size:34px;font-weight:700;color:var(--muted);white-space:nowrap}
.seg:first-child{border-left:1px solid var(--line)}
.seg span{text-align:center;line-height:1.15}
.seg b{position:absolute;left:0;top:-46px;font-family:var(--num);font-size:34px;color:var(--muted);font-weight:600;transform:translateX(-50%)}
.seg.on{background:var(--accent);color:var(--bg)}
.mk{position:absolute;top:-92px;bottom:-24px;left:0;width:0;border-left:4px solid #fff;transition:left 1.3s var(--ease) .7s}
.mk span{position:absolute;left:14px;top:-6px;font-family:var(--num);font-size:60px;font-weight:800;white-space:nowrap;line-height:1}
.mk span small{font-size:32px;color:var(--muted);margin-left:6px}
.in .mk{left:var(--x)}
/* 気象庁の図 */
.figwrap{position:absolute;left:0;right:0;top:470px;height:830px;display:flex;align-items:center;justify-content:center;background:#000}
.figwrap img{max-width:100%;max-height:100%;object-fit:contain}
.figcap{position:absolute;left:80px;bottom:16px;font-family:var(--mono);font-size:28px;color:#C9D1DA;text-shadow:0 2px 8px #000}
/* プロンプター（収録範囲の外） */
#pr{flex:none;width:460px;height:100%;max-height:960px;display:flex;flex-direction:column;gap:18px;padding:24px;background:#15191F;color:#D6DBE2;
 font:16px/1.7 -apple-system,"Hiragino Sans",sans-serif;border:1px solid #2a2f36;overflow:auto}
#pr.hidden{display:none}
#pr .k{font:12px/1.4 var(--mono);letter-spacing:.1em;color:#7A8593;text-transform:uppercase}
#pr .cur{font-size:22px;line-height:1.75;color:#fff;font-weight:600}
#pr .cue{font-size:15px;line-height:1.6;color:#F2B134;border-left:3px solid #F2B134;padding-left:10px}
#pr .cue:empty{display:none}
#pr .nx{color:#8B95A3}
#pr .ctl{margin-top:auto;font:12px/1.8 var(--mono);color:#7A8593;border-top:1px solid #2a2f36;padding-top:12px}
"""

JS = r"""
(function(){
  const stage=document.getElementById('stage'),frame=document.getElementById('frame'),pr=document.getElementById('pr');
  const q=new URLSearchParams(location.search),auto=q.get('auto')==='1';
  let manual=null;  // P キーで切り替えたら自動判定をやめる
  function fit(){
    const hide=manual!==null?manual:(q.get('prompter')==='0'||auto||innerWidth<innerHeight*0.9||innerWidth<900);
    pr.classList.toggle('hidden',hide);
    const prw=pr.classList.contains('hidden')?0:pr.offsetWidth+24;
    const s=Math.min((innerWidth-32-prw)/1080,(innerHeight-32)/1920);
    stage.style.transform=`scale(${s})`;frame.style.width=1080*s+'px';frame.style.height=1920*s+'px';
  }
  addEventListener('resize',fit);fit();
  const scenes=[...document.querySelectorAll('.scene')];let i=-1,timer=null;
  function show(n){
    if(n<0||n>=scenes.length)return;
    scenes.forEach(s=>{s.classList.remove('active','in');s.querySelectorAll('.dg .strip').forEach(st=>st.style.transform='translateY(0)')});
    void document.body.offsetWidth;  // display:none を一度確定させ、遷移とアニメーションを最初から
    const sc=scenes[n];sc.classList.add('active');void sc.offsetWidth;
    sc.querySelectorAll('.zoomw,.ly').forEach(el=>{const nm=el.style.animationName;el.style.animationName='none';void el.offsetWidth;el.style.animationName=nm});
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      sc.classList.add('in');
      const rd=parseFloat(sc.dataset.rollDelay||'0');
      sc.querySelectorAll('.dg .strip').forEach((st,k)=>{st.style.transitionDelay=(rd+0.12*k)+'s';st.style.transform=`translateY(-${st.dataset.d}em)`});
    }));
    i=n;
    document.getElementById('pr-idx').textContent=`${n+1} / ${scenes.length}  ${sc.dataset.title||''}`;
    document.getElementById('pr-cur').textContent=sc.dataset.narration||'';
    document.getElementById('pr-cue').textContent=sc.dataset.cue||'';
    const nx=scenes[n+1];document.getElementById('pr-nx').textContent=nx?('次: '+(nx.dataset.title||'')+' — '+(nx.dataset.narration||'').slice(0,60)+'…'):'（最後の場面）';
    if(auto){clearTimeout(timer);const d=parseFloat(sc.dataset.dur||'8')*1000;if(n<scenes.length-1)timer=setTimeout(()=>show(n+1),d)}
  }
  addEventListener('keydown',e=>{
    if(e.code==='Space'||e.key==='ArrowRight'||e.key==='Enter'){e.preventDefault();show(i+1)}
    else if(e.key==='ArrowLeft'){show(i-1)}
    else if(e.key==='r'||e.key==='R'){show(0)}
    else if(e.key==='p'||e.key==='P'){manual=!pr.classList.contains('hidden');fit()}
  });
  frame.addEventListener('click',()=>show(i+1));
  function start(){if(i<0)show(0)}
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(start);else start();
  setTimeout(start,1500);
})();
"""


def esc(s):
    return html.escape(str(s))


def fmt_val(v, unit=""):
    s = f"{v:.1f}" if isinstance(v, float) else str(v)
    return s + unit


def digits(v):
    """数字を1桁ずつ縦にロールする HTML。"""
    out = []
    for ch in str(v):
        if ch.isdigit():
            strip = "".join(f"<span>{d}</span>" for d in range(10))
            out.append(f'<span class="dg"><span class="strip" data-d="{ch}">{strip}</span></span>')
        else:
            out.append(f'<span>{ch}</span>')
    return "".join(out)


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(s):
    m = _NUM.search(str(s))
    return float(m.group()) if m else 0.0


def isobars():
    """背景の等圧線風パターン（SVG）。決定的に生成する。"""
    import math
    paths = []
    for k in range(9):
        y0 = 120 + k * 230
        pts = []
        for x in range(-100, 1400, 40):
            y = y0 + 70 * math.sin((x + k * 137) / 260) + 35 * math.sin((x * 1.7 + k * 61) / 190) - k * 12
            pts.append(f"{x},{y:.0f}")
        paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="2"/>')
    return f'<svg id="iso" viewBox="0 0 1300 2300" preserveAspectRatio="none">{"".join(paths)}</svg>'


REF = {
    "typhoon_strength": ("台風の強さ", "中心付近の最大風速", "m/s",
                         [("台風", 17.2, 33), ("強い", 33, 44), ("非常に強い", 44, 54), ("猛烈な", 54, 64)]),
    "typhoon_size": ("台風の大きさ", "強風域の半径", "km",
                     [("台風", 0, 500), ("大型", 500, 800), ("超大型", 800, 1000)]),
    # 雨は刻みが 10〜30mm と不揃いで比例幅だと細い枠に文字が入らないので等幅（even）。名前の \n は改行
    "rain": ("雨の強さ", "1時間雨量", "mm",
             [("やや\n強い雨", 10, 20), ("強い雨", 20, 30), ("激しい雨", 30, 50), ("非常に\n激しい雨", 50, 80), ("猛烈な雨", 80, 100)], "even"),
}
WORLD_M = 40075016.686
CTA_FILE = Path(__file__).resolve().parent / "short_cta.json"


def _proj(meta):
    def px(lat, lon):
        wx, wy = merc(lat, lon)
        return (wx - meta["wx0"]) * meta["s"], (wy - meta["wy0"]) * meta["s"]

    def pxr(lat, km):
        return km * 1000 * meta["s"] / (WORLD_M * math.cos(math.radians(lat)))
    return px, pxr


def track_html(sc, data):
    """台風の進路図: 地形図の上に SVG で実況（暴風域・強風域）、予報円、暴風警戒域、進路線を描く。"""
    base = data["_dir"] / sc["map"]
    meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    b64 = base64.b64encode(base.read_bytes()).decode()
    px, pxr = _proj(meta)
    W, H = meta["w"], meta["h"]
    svg, labels = [], []
    if sc.get("past"):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (px(la, lo) for la, lo in sc["past"]))
        svg.append(f'<polyline class="tr-past" points="{pts}"/>')
    cur = sc["current"]
    cx, cy = px(cur["lat"], cur["lon"])
    line = [(cx, cy)] + [px(p["lat"], p["lon"]) for p in sc["points"]]
    L = sum(math.dist(line[i], line[i + 1]) for i in range(len(line) - 1))
    # 予報円・暴風警戒域（順に現れる）
    for k, p in enumerate(sc["points"]):
        x, y = px(p["lat"], p["lon"])
        d = 0.9 + 0.45 * k
        g = []
        if p.get("storm_km"):
            g.append(f'<circle class="tr-warn" cx="{x:.1f}" cy="{y:.1f}" r="{pxr(p["lat"], p["r_km"] + p["storm_km"]):.1f}"/>')
        g.append(f'<circle class="tr-prob" cx="{x:.1f}" cy="{y:.1f}" r="{pxr(p["lat"], p["r_km"]):.1f}"/>')
        g.append(f'<circle class="tr-pt" cx="{x:.1f}" cy="{y:.1f}" r="9"/>')
        svg.append(f'<g class="fg" style="--d:{d:.2f}s">{"".join(g)}</g>')
        if p.get("label"):
            side = p.get("side") or ("left" if x > W * 0.6 else "right")
            sub = f'<em>{esc(p["sub"])}</em>' if p.get("sub") else ""
            labels.append(f'<div class="pt nodot {side}" style="left:{x:.0f}px;top:{y:.0f}px;transition-delay:{d+.1:.2f}s"><span class="lb">{esc(p["label"])}{sub}</span></div>')
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in line)
    svg.append(f'<polyline class="tr-fc" points="{pts}" style="stroke-dasharray:{L:.0f};stroke-dashoffset:{L:.0f}"/>')
    # 実況: 強風域（中心がずれることがある）、暴風域、中心
    g = []
    if cur.get("gale"):
        ga = cur["gale"]
        gx, gy = px(ga.get("lat", cur["lat"]), ga.get("lon", cur["lon"]))
        g.append(f'<circle class="tr-gale" cx="{gx:.1f}" cy="{gy:.1f}" r="{pxr(cur["lat"], ga["km"]):.1f}"/>')
    if cur.get("storm_km"):
        g.append(f'<circle class="tr-storm" cx="{cx:.1f}" cy="{cy:.1f}" r="{pxr(cur["lat"], cur["storm_km"]):.1f}"/>')
    g.append(f'<circle class="tr-cur" cx="{cx:.1f}" cy="{cy:.1f}" r="14"/>')
    svg.append(f'<g class="fg" style="--d:.2s">{"".join(g)}</g>')
    side = cur.get("side") or ("left" if cx > W * 0.6 else "right")
    sub = f'<em>{esc(cur["sub"])}</em>' if cur.get("sub") else ""
    labels.append(f'<div class="pt nodot hero {side}" style="left:{cx:.0f}px;top:{cy:.0f}px;transition-delay:.3s"><span class="lb">{esc(cur["label"])}{sub}</span></div>')
    legend = ""
    if sc.get("legend", True):
        items = [("#FF5C5C", "rgba(255,92,92,.25)", "暴風域"), ("#F2B134", "rgba(242,177,52,.15)", "強風域"), ("#FFFFFF", "transparent", "予報円")]
        legend = '<div class="legend">' + "".join(f'<span><i style="--c:{c};--bg-c:{b}"></i>{n}</span>' for c, b, n in items) + "</div>"
    sb = f'<div class="scalebar" style="width:{meta["px_per_km"]*sc.get("scale_km", 500):.0f}px"><span>{sc.get("scale_km", 500)} km</span></div>'
    html_ = (f'<div class="mapwrap" style="height:{H}px;top:{1300-H}px"><img src="data:image/png;base64,{b64}" style="height:{H}px">'
             f'<svg viewBox="0 0 {W} {H}" style="height:{H}px">{"".join(svg)}</svg>{"".join(labels)}{legend}{sb}<div class="mapfade"></div></div>')
    data.setdefault("_credits", []).append(meta.get("credit", ""))
    return html_, 0.9 + 0.45 * len(sc["points"]) + 0.6


FRONT_COLOR = {"red": "#FF5A5A", "blue": "#5B8CFF", "purple": "#C77DFF"}


def _front_svg(pts, kind, step=66.0, r=16.0):
    """前線を画素の折れ線から描く。停滞前線は赤（半円・北側）と青（三角・南側）を交互に置く。
    寒冷・温暖・閉塞前線は線の進行方向の左側に記号を置く（XML の線の向きとの対応は未検証。出たら気象庁の図と見比べる）。"""
    segs, acc = [], 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d > 0:
            segs.append((a, b, acc, d))
            acc += d
    if not segs:
        return ""

    def at(dist):
        for a, b, s0, d in segs:
            if dist <= s0 + d:
                q = (dist - s0) / d
                return (a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q), ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
        a, b, s0, d = segs[-1]
        return b, ((b[0] - a[0]) / d, (b[1] - a[1]) / d)

    kinds = {"停滞前線": ("stat", None), "寒冷前線": ("tri", "blue"), "温暖前線": ("semi", "red"), "閉塞前線": ("alt", "purple")}
    mode, col = kinds.get(kind, ("line", "purple"))
    out, n = [], int(acc // step)
    for i in range(n):
        s0, s1 = i * step, (i + 1) * step
        if mode == "stat":
            c = FRONT_COLOR["red" if i % 2 == 0 else "blue"]
            shape = "semi" if i % 2 == 0 else "tri"
        else:
            c = FRONT_COLOR[col]
            shape = mode if mode in ("tri", "semi") else ("tri" if i % 2 else "semi")
        line = [at(s0)[0]] + [b for a, b, ss, d in segs if s0 < ss + d < s1] + [at(s1)[0]]
        out.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in line)}" fill="none" stroke="{c}" stroke-width="6" stroke-linejoin="round"/>')
        (mx, my), (tx, ty) = at(s0 + step / 2)
        nx, ny = ty, -tx                                   # 進行方向の左
        if mode == "stat":
            if ny > 0:                                     # 停滞前線: 半円は北（画面の上）、三角は南
                nx, ny = -nx, -ny
            if shape == "tri":
                nx, ny = -nx, -ny
        if shape == "semi":
            x0, y0, x1, y1 = mx - tx * r, my - ty * r, mx + tx * r, my + ty * r
            sweep = 1 if (tx * ny - ty * nx) > 0 else 0
            out.append(f'<path d="M{x0:.1f},{y0:.1f} A{r:.0f},{r:.0f} 0 0 {sweep} {x1:.1f},{y1:.1f} Z" fill="{c}"/>')
        else:
            h = r * 1.5
            out.append(f'<path d="M{mx - tx*r:.1f},{my - ty*r:.1f} L{mx + nx*h:.1f},{my + ny*h:.1f} L{mx + tx*r:.1f},{my + ty*r:.1f} Z" fill="{c}"/>')
    return "".join(out)


def synoptic_html(sc, data):
    """天気図: 地形図の上に、気象庁 地上実況図の等圧線・前線と、解説にある空気の流れ（模式）を描く。"""
    base = data["_dir"] / sc["map"]
    meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    b64 = base64.b64encode(base.read_bytes()).decode()
    sf = json.loads((data["_dir"] / sc["surface"]).read_text(encoding="utf-8"))
    px, _ = _proj(meta)
    W, H = meta["w"], meta["h"]

    def inview(x, y, m=60):
        return -m <= x <= W + m and -m <= y <= H + m

    iso, lbls = [], []
    for ib in sf["isobars"]:
        pts = [px(la, lo) for la, lo in ib["line"]]
        if not any(inview(x, y, 0) for x, y in pts):
            continue
        iso.append(f'<polyline class="syn-iso" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>')
        edge = [(x, y) for x, y in pts if 40 < x < W - 240 and 60 < y < H - 260]   # 右と下は UI・フェードに隠れる
        if edge and ib["hpa"] % 4 == 0:
            x, y = edge[len(edge) // 2]
            lbls.append(f'<text class="syn-isolbl" x="{x:.0f}" y="{y - 8:.0f}" text-anchor="middle" paint-order="stroke" stroke="#0B0F14" stroke-width="6">{ib["hpa"]}</text>')
    fronts = "".join(_front_svg([px(la, lo) for la, lo in f["line"]], f["type"]) for f in sf["fronts"])
    arrows = []
    for k, ar in enumerate(sc.get("arrows", [])):
        pts = [px(la, lo) for la, lo in ar["path"]]
        L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        d = math.dist((x0, y0), (x1, y1)) or 1
        tx, ty = (x1 - x0) / d, (y1 - y0) / d
        h, w = 46, 34
        tip = (x1 + tx * h * 0.6, y1 + ty * h * 0.6)
        head = (f'M{tip[0]:.1f},{tip[1]:.1f} L{x1 - tx*h*0.4 - ty*w:.1f},{y1 - ty*h*0.4 + tx*w:.1f} '
                f'L{x1 - tx*h*0.4 + ty*w:.1f},{y1 - ty*h*0.4 - tx*w:.1f} Z')
        arrows.append(f'<polyline class="syn-arrow" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" '
                      f'style="stroke-dasharray:{L:.0f};stroke-dashoffset:{L:.0f}"/><path class="syn-head" d="{head}"/>')
    labels = []
    for k, ar in enumerate(sc.get("arrows", [])):
        if ar.get("label"):
            x, y = px(*ar["path"][0])
            side = ar.get("side", "right")
            labels.append(f'<div class="pt nodot warm {side}" style="left:{x:.0f}px;top:{y:.0f}px;transition-delay:2.6s"><span class="lb">{esc(ar["label"])}</span></div>')
    if sc.get("front_label"):
        fl = sc["front_label"]
        x, y = px(fl["lat"], fl["lon"])
        labels.append(f'<div class="pt nodot {fl.get("side", "below")}" style="left:{x:.0f}px;top:{y:.0f}px;transition-delay:2.2s"><span class="lb">{esc(fl["text"])}</span></div>')
    if sc.get("focus"):
        fo = sc["focus"]
        x, y = px(fo["lat"], fo["lon"])
        sub = f'<em>{esc(fo["sub"])}</em>' if fo.get("sub") else ""
        labels.append(f'<div class="pt hero {fo.get("side", "left")}" style="left:{x:.0f}px;top:{y:.0f}px;transition-delay:3.6s"><i></i><span class="lb">{esc(fo["label"])}{sub}</span></div>')
    tl = f'<div class="syn-time">{esc(sc["time_label"])}</div>' if sc.get("time_label") else ""
    svg = (f'<svg viewBox="0 0 {W} {H}" style="height:{H}px"><g class="fg" style="--d:.1s">{"".join(iso)}{"".join(lbls)}</g></svg>'
           f'<svg class="syn-fr" viewBox="0 0 {W} {H}" style="height:{H}px">{fronts}</svg>'
           f'<svg viewBox="0 0 {W} {H}" style="height:{H}px">{"".join(arrows)}</svg>')
    html_ = (f'<div class="mapwrap" style="height:{H}px;top:{1300-H}px"><img src="data:image/png;base64,{b64}" style="height:{H}px">'
             f'{svg}{"".join(labels)}{tl}<div class="mapfade"></div></div>')
    data.setdefault("_credits", []).append(meta.get("credit", ""))
    data.setdefault("_credits", []).append("天気図: 気象庁 地上実況図（XML）")
    return html_, 4.2


def scale_html(sc):
    """気象庁の階級表を帯で示し、発表値の位置に印を置く。"""
    title, what, unit, bands, *mode = REF[sc["ref"]]
    even = "even" in mode
    lo, hi = bands[0][1], bands[-1][2]
    v = float(sc["value"])
    parts = []
    if sc.get("stats"):
        tiles = "".join(f'<div class="stat" style="transition-delay:{0.12*k:.2f}s"><div class="k">{esc(s["k"])}</div>'
                        f'<div class="v">{esc(s["v"])}<small>{esc(s.get("u", ""))}</small></div></div>' for k, s in enumerate(sc["stats"]))
        parts.append(f'<div class="stats">{tiles}</div>')
    parts.append(f'<div class="bandlbl">気象庁の階級「{esc(title)}」（{esc(what)}）</div>')
    segs = []
    for k, (name, a, b) in enumerate(bands):
        on = " on" if a <= v < b or (k == len(bands) - 1 and v >= a) else ""
        bound = f'<b>{a:g}</b>' if k > 0 else ""
        label = "<br>".join(esc(x) for x in name.split("\n"))
        segs.append(f'<div class="seg{on}" style="--f:{1 if even else b-a:.1f}">{bound}<span>{label}</span></div>')
    vc = min(max(v, lo), hi)
    if even:   # 等幅: 該当する帯の中で線形に置く
        k = next((k for k, (_, a, b) in enumerate(bands) if a <= vc < b), len(bands) - 1)
        _, a, b = bands[k]
        x = (k + min((vc - a) / (b - a), 1)) / len(bands) * 100
    else:
        x = (vc - lo) / (hi - lo) * 100
    parts.append(f'<div class="band">{"".join(segs)}<div class="mk" style="--x:{x:.1f}%"><span>{v:g}<small>{esc(unit)}</small></span></div></div>')
    return "".join(parts)


def figure_html(sc, data):
    base = data["_dir"] / sc["image"]
    ext = base.suffix.lstrip(".").lower().replace("jpg", "jpeg")
    b64 = base64.b64encode(base.read_bytes()).decode()
    cap = f'<div class="figcap">{esc(sc["caption"])}</div>' if sc.get("caption") else ""
    return f'<div class="figwrap"><img src="data:image/{ext};base64,{b64}">{cap}</div>'


def _smoothstep(q):
    return q * q * (3 - 2 * q)


def intro_html(sc, data, tone):
    """ズーム導入: 同じ投影で描いた地形図の層を重ね、最初の層が画面いっぱいの状態から最後の層が画面いっぱいになるまで寄る。"""
    metas, b64s = [], []
    for rel in sc["layers"]:
        base = data["_dir"] / rel
        metas.append(json.loads(base.with_suffix(".json").read_text(encoding="utf-8")))
        b64s.append(base64.b64encode(base.read_bytes()).decode())
    L = metas[-1]                      # 最終フレームの層（画面と同じ画素系）
    J = metas[0]
    fx_, fy_ = merc(sc["focus"]["lat"], sc["focus"]["lon"])
    f1 = ((fx_ - L["wx0"]) * L["s"], (fy_ - L["wy0"]) * L["s"])      # 最終フレームでの注目点
    f0 = ((fx_ - J["wx0"]) * J["s"], (fy_ - J["wy0"]) * J["s"])      # 最初の層が画面いっぱいのときの注目点
    k0 = J["s"] / L["s"]
    n = len(sc["layers"])
    hold = sc.get("hold", 0.6)
    zdur = sc.get("zoom_sec", 3.4)
    steps = 24
    kf = []
    for i in range(steps + 1):
        q = i / steps
        p = _smoothstep(q)
        k = k0 ** (1 - p)
        fx = f0[0] + (f1[0] - f0[0]) * p
        fy = f0[1] + (f1[1] - f0[1]) * p
        kf.append(f"{q*100:.1f}%{{transform:translate({fx - f1[0]*k:.1f}px,{fy - f1[1]*k:.1f}px) scale({k:.5f})}}")
    uid = f"z{abs(hash(sc['layers'][0])) % 100000}"
    css = [f"@keyframes {uid}{{{''.join(kf)}}}"]
    layers = []
    for j, (m, b) in enumerate(zip(metas, b64s)):
        left = (m["wx0"] - L["wx0"]) * L["s"]
        top = (m["wy0"] - L["wy0"]) * L["s"]
        w, h = m["w"] * L["s"] / m["s"], m["h"] * L["s"] / m["s"]
        style = f"left:{left:.1f}px;top:{top:.1f}px;width:{w:.1f}px;height:{h:.1f}px"
        cls = "ly"
        if j > 0:
            a0 = 0.25 + 0.4 * (j - 1) / max(1, n - 2) if n > 2 else 0.45
            a1 = a0 + 0.2
            css.append(f"@keyframes {uid}f{j}{{0%{{opacity:0}}{a0*100:.0f}%{{opacity:0}}{a1*100:.0f}%{{opacity:1}}100%{{opacity:1}}}}")
            style += f";opacity:0;animation-name:{uid}f{j}"
            cls += " lf"
        layers.append(f'<img class="{cls}" style="{style}" src="data:image/png;base64,{b}">')
    init = kf[0].split("{", 1)[1].rstrip("}")
    zoom = (f'<div class="zoom"><div class="zoomw" style="{init};animation-name:{uid};animation-duration:{zdur}s;animation-delay:{hold}s">'
            f'{"".join(layers)}</div></div>')
    t_end = hold + zdur
    foc = sc["focus"]
    rings = ""
    for r in foc.get("rings", []):
        rx, ry = f1
        if r.get("lat") is not None:
            wx, wy = merc(r["lat"], r["lon"])
            rx, ry = (wx - L["wx0"]) * L["s"], (wy - L["wy0"]) * L["s"]
        rp = r["km"] * 1000 * L["s"] / (WORLD_M * math.cos(math.radians(foc["lat"])))
        rings += (f'<div class="ring" style="left:{rx:.0f}px;top:{ry:.0f}px;width:{2*rp:.0f}px;height:{2*rp:.0f}px;'
                  f'border-color:{r.get("color", "#fff")};background:{r.get("fill", "transparent")};transition-delay:{t_end-0.2:.2f}s"></div>')
    focus = (rings + f'<div class="focus left" style="left:{f1[0]:.0f}px;top:{f1[1]:.0f}px;--t:{t_end-0.2:.2f}s"><i></i>'
             f'<span class="lb">{esc(foc.get("label", ""))}<em>{esc(foc.get("sub", ""))}</em></span></div>')
    t_text = t_end + 0.4
    v = sc["value"]
    head = sc.get("headline") or sc.get("place", "")
    kicker = sc.get("kicker", "")
    items = [f'<div class="place" style="transition-delay:{t_text+.1:.2f}s"><small>{esc(kicker)}</small>{esc(head)}</div>',
             f'<div class="label" style="transition-delay:{t_text+.5:.2f}s">{esc(sc.get("label", ""))}</div>',
             f'<div class="big" style="transition-delay:{t_text+.6:.2f}s"><span class="num">{digits(fmt_val(v))}</span><span class="unit">{esc(sc.get("unit", ""))}</span></div>']
    if sc.get("badge"):
        sub = f'<span>{esc(sc["badge_sub"])}</span>' if sc.get("badge_sub") else ""
        items.append(f'<div style="transition-delay:{t_text+1.8:.2f}s"><span class="tag"><b>{esc(sc["badge"])}</b>{sub}</span></div>')
    shade = f'<div class="shade" style="transition-delay:{t_end+.3:.2f}s"></div>'
    text = f'<div class="itext">{"".join(items)}</div>'
    extra = {"roll": t_text + 0.7, "css": "\n".join(css)}
    return zoom + focus + shade + text, extra


def scene_html(sc, data, idx):
    tone = TONE.get(sc.get("tone", "jma"), TONE["jma"])
    t = sc["type"]
    top = (f'<div class="top"><span class="tone"><i></i>{esc(sc.get("band", tone["label"]))}</span>'
           f'<span><b>{esc(data.get("brand", "気象予報士なべ"))}</b>　{esc(data.get("date_label", data.get("date", "")))}</span></div>')
    parts = [top]
    take_delay = sc.get("takeaway_delay", 0.8)
    roll_delay = 0.0
    if t == "intro":
        body, extra = intro_html(sc, data, tone)
        parts.append(body)
        roll_delay = extra["roll"]
        data.setdefault("_css", []).append(extra["css"])
        data.setdefault("_credits", []).append(json.loads((data["_dir"] / sc["layers"][0]).with_suffix(".json").read_text(encoding="utf-8")).get("credit", ""))
    elif t == "hook":
        v = sc["value"]
        if sc.get("meta"):
            parts.append(f'<div class="meta">{esc(sc["meta"])}</div>')
        head = sc.get("headline") or sc["place"]
        kicker = sc.get("kicker", "")
        if sc.get("headline") and sc.get("place"):
            kicker = f'{kicker}　{sc["place"]}' if kicker else sc["place"]
        parts.append(f'<div class="place"><small>{esc(kicker)}</small>{esc(head)}</div>')
        parts.append(f'<div class="label">{esc(sc.get("label", ""))}</div>')
        parts.append(f'<div class="big"><span class="num">{digits(fmt_val(v))}</span><span class="unit">{esc(sc.get("unit", ""))}</span></div>')
        if sc.get("badge"):
            sub = f'<span>{esc(sc["badge_sub"])}</span>' if sc.get("badge_sub") else ""
            parts.append(f'<div><span class="tag"><b>{esc(sc["badge"])}</b>{sub}</span></div>')
    elif t == "rank":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        if sc.get("sub"):
            parts.append(f'<div class="sub">{esc(sc["sub"])}</div>')
        bars = sc["bars"]
        mx = max(b["value"] for b in bars) or 1
        today = [b for b in bars if b.get("today")]
        prev = max((b["value"] for b in bars if not b.get("today")), default=None)
        rows, k_other = [], 0
        for b in bars:
            if b.get("today"):
                row_d, bar_d = 1.0, 1.15
            else:
                row_d, bar_d = 0.12 * k_other, 0.12 * k_other + 0.2
                k_other += 1
            cls = "row today" if b.get("today") else "row"
            new = '<span class="new">NEW</span>' if b.get("today") else ""
            mark = f'<span class="mark" style="--mk:{prev/mx*100:.1f}%"></span>' if (today and prev) else ""
            rows.append(f'<div class="{cls}" style="transition-delay:{row_d:.2f}s"><div class="rk">{b["rank"]}<small>位</small></div>'
                        f'<div><div class="bar"><i style="--pct:{b["value"]/mx:.3f};transition-delay:{bar_d:.2f}s"></i>{mark}</div>'
                        f'<div class="d">{esc(b.get("date", ""))}{new}</div></div>'
                        f'<div class="v">{fmt_val(b["value"])}<small>{esc(sc.get("unit", ""))}</small></div></div>')
        parts.append(f'<div class="rows">{"".join(rows)}</div>')
        if sc.get("note"):
            parts.append(f'<div class="note">{esc(sc["note"])}</div>')
        take_delay = sc.get("takeaway_delay", 2.6 if today else 0.8)
    elif t == "map":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        base = data["_dir"] / sc["map"]
        meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        b64 = base64.b64encode(base.read_bytes()).decode()
        pts = []
        for k, pt in enumerate(sc["points"]):
            wx, wy = merc(pt["lat"], pt["lon"])
            px, py = (wx - meta["wx0"]) * meta["s"], (wy - meta["wy0"]) * meta["s"]
            side = pt.get("side") or ("left" if px > meta["w"] * 0.6 else "right")   # left / right / above / below
            cls = "pt " + side + (" hero" if pt.get("hero") else "")
            val = f'<b>{esc(pt["value"])}</b>' if pt.get("value") else ""
            rk = f'<em>{esc(pt["rank"])}</em>' if pt.get("rank") else ""
            pts.append(f'<div class="{cls}" style="left:{px:.0f}px;top:{py:.0f}px;transition-delay:{0.3+0.45*k:.2f}s">'
                       f'<i></i><span class="lb">{esc(pt["name"])}{val}{rk}</span></div>')
        sb = f'<div class="scalebar" style="width:{meta["px_per_km"]*10:.0f}px"><span>10 km</span></div>'
        parts.append(f'<div class="mapwrap"><img src="data:image/png;base64,{b64}">{"".join(pts)}{sb}<div class="mapfade"></div></div>')
        take_delay = sc.get("takeaway_delay", 0.3 + 0.45 * len(sc["points"]) + 0.5)
        data.setdefault("_credits", []).append(meta.get("credit", ""))
    elif t == "track":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        body, td = track_html(sc, data)
        parts.append(body)
        take_delay = sc.get("takeaway_delay", td)
    elif t == "synoptic":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        body, td = synoptic_html(sc, data)
        parts.append(body)
        take_delay = sc.get("takeaway_delay", td)
    elif t == "scale":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        if sc.get("sub"):
            parts.append(f'<div class="sub">{esc(sc["sub"])}</div>')
        parts.append(scale_html(sc))
        take_delay = sc.get("takeaway_delay", 2.2)
    elif t == "figure":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        parts.append(figure_html(sc, data))
        if sc.get("credit"):
            data.setdefault("_credits", []).append(sc["credit"])
    elif t == "cards":
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        if sc.get("sub"):
            parts.append(f'<div class="sub">{esc(sc["sub"])}</div>')
        vals = [_num(c.get("value", 0)) for c in sc["cards"]]
        mx = max(vals) or 1
        rows = []
        for k, c in enumerate(sc["cards"]):
            rows.append(f'<div class="row" style="transition-delay:{0.1*k:.2f}s"><div class="nm">{esc(c["title"])}</div>'
                        f'<div><div class="bar"><i style="--pct:{vals[k]/mx:.3f};transition-delay:{0.1*k+.2:.2f}s"></i></div><div class="d">{esc(c.get("sub", ""))}</div></div>'
                        f'<div class="v">{esc(c.get("value", ""))}</div></div>')
        parts.append(f'<div class="rows">{"".join(rows)}</div>')
        if sc.get("note"):
            parts.append(f'<div class="note">{esc(sc["note"])}</div>')
    elif t in ("text", "close"):
        parts.append(f'<div class="heading">{esc(sc["heading"])}</div>')
        if sc.get("sub"):
            parts.append(f'<div class="sub">{esc(sc["sub"])}</div>')
        ls = [f'<div class="line" style="transition-delay:{0.18*k:.2f}s"><div class="n">{k+1:02d}</div><div>{esc(l)}</div></div>'
              for k, l in enumerate(sc.get("lines", []))]
        parts.append(f'<div class="lines">{"".join(ls)}</div>')
    else:
        raise SystemExit(f"unknown scene type: {t}")
    if sc.get("takeaway"):
        parts.append(f'<div class="take" style="transition-delay:{take_delay:.2f}s">{esc(sc["takeaway"])}</div>')
    foot = []
    if data.get("footer"):
        foot.append(esc(data["footer"]))
    src = data.get("source") or {}
    credits = [src.get("label", "")] + ([c for c in data.get("_credits", []) if c] if t in ("map", "intro", "track", "figure", "synoptic") else [])
    credits = list(dict.fromkeys(c for c in credits if c))
    if credits:
        foot.append(f'<span class="src">出典: {esc("　".join(credits))}</span>')
    if foot:
        parts.append('<div class="foot">' + "<br>".join(foot) + "</div>")
    title = sc.get("heading") or sc.get("headline") or sc.get("place") or t
    return (f'<section class="scene s-{t}" data-dur="{sc.get("dur", 8)}" data-title="{esc(title)}" data-roll-delay="{roll_delay:.2f}" '
            f'data-cue="{esc(sc.get("cue", ""))}" data-narration="{esc(sc.get("narration", ""))}" style="--accent:{tone["accent"]}">{"".join(parts)}</section>')


def merc(lat, lon):
    p = math.radians(lat)
    return (lon + 180) / 360, (1 - math.log(math.tan(p) + 1 / math.cos(p)) / math.pi) / 2


def build_html(data):
    body = "".join(scene_html(sc, data, k) for k, sc in enumerate(data["scenes"]))
    extra_css = "\n".join(data.get("_css", []))
    pr = ('<aside id="pr"><div class="k">Prompter — 収録範囲の外です</div><div id="pr-idx" class="k"></div>'
          '<div id="pr-cue" class="cue"></div><div id="pr-cur" class="cur"></div><div id="pr-nx" class="nx"></div>'
          '<div class="ctl">Space / → 次　← 前　R 最初から　P この欄を隠す<br>'
          '収録: Cmd+Shift+5 → 「選択部分を収録」で左の枠を囲む → マイクを選ぶ</div></aside>')
    return (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>{esc(data["title"])}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}\n{extra_css}</style></head>'
            f'<body><div id="wrap"><div id="frame"><div id="stage">{isobars()}{body}</div></div>{pr}</div><script>{JS}</script></body></html>')


def build_narration(data):
    out = [f'# {data["title"]}', "", f'発表・観測日: {data.get("date", "")}', ""]
    total = 0
    for k, sc in enumerate(data["scenes"], 1):
        n = sc.get("narration", "")
        total += len(n)
        out += [f'## {k}. {sc.get("heading") or sc.get("headline") or sc.get("place") or sc["type"]}（{sc.get("dur", 8)}秒目安・{len(n)}文字）', ""]
        if sc.get("cue"):
            out += [f'〔合図〕{sc["cue"]}', ""]
        out += [n, ""]
    out += [f'合計 {total} 文字（話速 6〜7文字/秒で約 {total // 7}〜{total // 6} 秒）', "", "---", "", "## 照合チェック表", ""]
    check = data.get("check")
    if not check:
        check = [["項目", "動画の値", "原文の値"]]
        for sc in data["scenes"]:
            if sc["type"] == "hook":
                check.append([f'{sc["place"]} {sc.get("label", "")}', fmt_val(sc["value"], sc.get("unit", "")), ""])
            for b in sc.get("bars", []):
                check.append([f'{sc.get("sub", "")} {b["rank"]}位', f'{fmt_val(b["value"], sc.get("unit", ""))} {b.get("date", "")}', ""])
            for c in sc.get("cards", []):
                check.append([c["title"], f'{c.get("value", "")} {c.get("sub", "")}', ""])
    out.append("| " + " | ".join(check[0]) + " |")
    out.append("|" + "---|" * len(check[0]))
    for row in check[1:]:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    src = data.get("source") or {}
    if src.get("url"):
        out += ["", f'出典: {src.get("label", "")} {src["url"]}']
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--out")
    a = ap.parse_args()
    p = Path(a.json)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["_dir"] = p.parent
    cta = data.get("cta", True)
    if cta is not False and (not data["scenes"] or data["scenes"][-1]["type"] != "close"):
        tmpl = json.loads(CTA_FILE.read_text(encoding="utf-8"))
        opt = cta if isinstance(cta, dict) else {}
        lines = list(opt.get("lines_before", []))
        nar = opt.get("narration_before", "")
        if opt.get("next"):
            lines.append(f'次の発表は {opt["next"]}')
            nar += f'次の発表は{opt["next"]}です。'
        tmpl["lines"] = lines + tmpl["lines"]
        tmpl["narration"] = nar + tmpl["narration"]
        tmpl.update({k: v for k, v in opt.items() if k in ("heading", "tone", "dur")})
        data["scenes"].append(tmpl)
    out = Path(a.out) if a.out else p.with_name("short.html")
    out.write_text(build_html(data), encoding="utf-8")
    nar = out.with_name(out.stem + "_narration.md")
    nar.write_text(build_narration(data), encoding="utf-8")
    print(out)
    print(nar)


if __name__ == "__main__":
    main()
