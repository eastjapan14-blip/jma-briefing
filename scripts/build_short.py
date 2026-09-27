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
   "title": "...", "date": "2026-09-21",
   "source": {"label": "気象庁 観測史上1位の値 更新状況", "url": "https://..."},
   "footer": "速報値。確定値は気象庁の発表で確認してください",   ← 全場面の下部に小さく出る
   "scenes": [
     {"type": "hook",  "tone": "jma", "dur": 8,
      "kicker": "9月21日 千葉県市原市", "place": "牛久（うしく）", "value": 341.0, "unit": "mm",
      "label": "日降水量", "badge": "観測史上1位", "narration": "..."},
     {"type": "rank",  "heading": "観測史のどこに刺さった？", "sub": "牛久 日降水量 歴代（統計開始 1978年）",
      "bars": [{"rank": 1, "value": 341.0, "date": "2026/9/21", "today": true}, {"rank": 2, ...}],
      "unit": "mm", "note": "従来1位（1996年）を 20.0mm 上回る", "narration": "..."},
     {"type": "cards", "heading": "同じ日、千葉県では",
      "cards": [{"title": "船橋", "value": "290.0mm", "sub": "観測史上1位"}, ...], "narration": "..."},
     {"type": "text",  "heading": "...", "lines": ["...", "..."], "narration": "..."},
     {"type": "close", "heading": "今後の情報は気象庁で", "lines": ["..."], "narration": "..."}
   ],
   "check": [["項目", "動画の値", "原文の値"], ...]   ← 照合チェック表（任意。無ければ数値から自動生成）
  }
tone: jma（気象庁の発表・観測値。青）/ action（行動指針。橙）/ fun（気象の楽しみ。緑）。省略時は jma。
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
.place{font-size:84px;font-weight:800;line-height:1.1;letter-spacing:.01em}
.place small{display:block;font-size:40px;font-weight:600;color:var(--muted);margin-bottom:10px;letter-spacing:.02em}
.label{margin-top:56px;font-size:44px;font-weight:600;color:var(--muted);display:flex;align-items:center;gap:20px}
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
.tag span{padding:22px 34px;font-size:40px;font-weight:600;color:var(--muted);display:flex;align-items:center}
.in .tag{opacity:1;transform:none}
.heading{font-size:76px;font-weight:800;line-height:1.2;letter-spacing:.01em}
.sub{margin-top:22px;font-family:var(--mono);font-size:28px;color:var(--muted);letter-spacing:.03em;line-height:1.5}
.rows{margin-top:56px;display:flex;flex-direction:column}
.row{display:grid;grid-template-columns:110px 1fr 250px;align-items:center;gap:20px;padding:22px 0;border-top:1px solid var(--line);
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.row:last-child{border-bottom:1px solid var(--line)}
.in .row{opacity:1;transform:none}
.s-cards .row{grid-template-columns:200px 1fr 250px;padding:16px 0}
.s-cards .rows{margin-top:40px}
.s-cards .row .d{margin-top:10px}
.row .rk{font-family:var(--num);font-size:56px;font-weight:600;color:var(--muted);letter-spacing:.02em}
.row .rk small{font-size:30px;margin-left:2px}
.row .nm{font-size:44px;font-weight:700}
.row .bar{position:relative;height:10px;background:rgba(255,255,255,.08)}
.row .bar i{position:absolute;left:0;top:0;bottom:0;width:100%;background:#4A5563;transform:scaleX(0);transform-origin:left;transition:transform 1s var(--ease)}
.in .row .bar i{transform:scaleX(var(--pct))}
.row .d{font-family:var(--mono);font-size:30px;color:var(--muted);margin-top:14px;letter-spacing:.03em}
.row .v{font-family:var(--num);font-size:64px;font-weight:800;text-align:right;letter-spacing:.01em;font-variant-numeric:tabular-nums}
.row .v small{font-size:32px;color:var(--muted);font-weight:600;margin-left:4px}
.row.today .rk,.row.today .v{color:var(--accent)}
.row.today .bar i{background:var(--accent)}
.row.today .nm:after,.row.today .rk:after{content:""}
.row .new{font-family:var(--num);font-size:26px;letter-spacing:.14em;color:var(--bg);background:var(--accent);padding:4px 10px;margin-left:16px;vertical-align:middle;font-weight:800}
.note{margin-top:52px;padding:30px 36px;border-left:4px solid var(--accent);background:rgba(255,255,255,.04);font-size:42px;line-height:1.45;font-weight:600;
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease) .9s,transform .6s var(--ease) .9s}
.in .note{opacity:1;transform:none}
.lines{margin-top:56px;display:flex;flex-direction:column}
.line{display:grid;grid-template-columns:90px 1fr;gap:20px;padding:34px 0;border-top:1px solid var(--line);font-size:50px;line-height:1.4;font-weight:700;
 opacity:0;transform:translateY(18px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.line:last-child{border-bottom:1px solid var(--line)}
.line .n{font-family:var(--num);font-size:56px;font-weight:600;color:var(--accent);line-height:1.25}
.in .line{opacity:1;transform:none}
/* 結論の一行（音を出さない視聴者向け） */
.take{position:absolute;left:80px;right:200px;bottom:632px;font-size:64px;font-weight:800;line-height:1.25;letter-spacing:.01em;
 opacity:0;transform:translateY(16px);transition:opacity .5s var(--ease),transform .6s var(--ease)}
.take:before{content:"";display:block;width:64px;height:4px;background:var(--accent);margin-bottom:18px}
.in .take{opacity:1;transform:none}
/* 順位: 従来1位の位置に破線。今回の棒が遅れて伸びて越える */
.row .bar .mark{position:absolute;top:-16px;bottom:-16px;left:var(--mk);border-left:3px dashed rgba(255,255,255,.55);opacity:0;transition:opacity .4s var(--ease) .7s}
.in .row .bar .mark{opacity:1}
.s-rank .row.today .bar i{transition-duration:1.4s}
/* 地図 */
.s-map .heading{font-size:68px}
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
.pt .lb{position:absolute;left:24px;top:0;transform:translateY(-50%);white-space:nowrap;font-size:34px;font-weight:700;line-height:1;
 text-shadow:0 2px 10px #000,0 0 4px #000}
.pt .lb b{font-family:var(--num);font-size:42px;font-weight:800;margin-left:12px;letter-spacing:.01em}
.pt .lb em{font-style:normal;font-family:var(--mono);font-size:24px;color:var(--muted);margin-left:12px}
.pt.left .lb{left:auto;right:24px}
.pt.hero .lb{font-size:38px}
.scalebar{position:absolute;left:80px;top:24px;height:10px;border:2px solid rgba(255,255,255,.6);border-top:none;font-family:var(--mono);font-size:22px;color:var(--muted)}
.scalebar span{position:absolute;left:0;top:-32px;white-space:nowrap}
/* プロンプター（収録範囲の外） */
#pr{flex:none;width:460px;height:100%;max-height:960px;display:flex;flex-direction:column;gap:18px;padding:24px;background:#15191F;color:#D6DBE2;
 font:16px/1.7 -apple-system,"Hiragino Sans",sans-serif;border:1px solid #2a2f36;overflow:auto}
#pr.hidden{display:none}
#pr .k{font:12px/1.4 var(--mono);letter-spacing:.1em;color:#7A8593;text-transform:uppercase}
#pr .cur{font-size:22px;line-height:1.75;color:#fff;font-weight:600}
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
    const sc=scenes[n];sc.classList.add('active');void sc.offsetWidth;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      sc.classList.add('in');
      sc.querySelectorAll('.dg .strip').forEach((st,k)=>{st.style.transitionDelay=(0.12*k)+'s';st.style.transform=`translateY(-${st.dataset.d}em)`});
    }));
    i=n;
    document.getElementById('pr-idx').textContent=`${n+1} / ${scenes.length}  ${sc.dataset.title||''}`;
    document.getElementById('pr-cur').textContent=sc.dataset.narration||'';
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
  document.fonts&&document.fonts.ready.then(()=>show(0))||show(0);
  setTimeout(()=>{if(i<0)show(0)},1500);
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


def scene_html(sc, data, idx):
    tone = TONE.get(sc.get("tone", "jma"), TONE["jma"])
    t = sc["type"]
    top = (f'<div class="top"><span class="tone"><i></i>{esc(sc.get("band", tone["label"]))}</span>'
           f'<span><b>{esc(data.get("brand", "気象予報士なべ"))}</b>　{esc(data.get("date_label", data.get("date", "")))}</span></div>')
    parts = [top]
    take_delay = sc.get("takeaway_delay", 0.8)
    if t == "hook":
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
            side = pt.get("side") or ("left" if px > meta["w"] * 0.6 else "right")
            cls = "pt " + side + (" hero" if pt.get("hero") else "")
            val = f'<b>{esc(pt["value"])}</b>' if pt.get("value") else ""
            rk = f'<em>{esc(pt["rank"])}</em>' if pt.get("rank") else ""
            pts.append(f'<div class="{cls}" style="left:{px:.0f}px;top:{py:.0f}px;transition-delay:{0.3+0.45*k:.2f}s">'
                       f'<i></i><span class="lb">{esc(pt["name"])}{val}{rk}</span></div>')
        sb = f'<div class="scalebar" style="width:{meta["px_per_km"]*10:.0f}px"><span>10 km</span></div>'
        parts.append(f'<div class="mapwrap"><img src="data:image/png;base64,{b64}">{"".join(pts)}{sb}<div class="mapfade"></div></div>')
        take_delay = sc.get("takeaway_delay", 0.3 + 0.45 * len(sc["points"]) + 0.5)
        data.setdefault("_credits", []).append(meta.get("credit", ""))
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
    credits = [src.get("label", "")] + [c for c in data.get("_credits", []) if c and t == "map"]
    credits = [c for c in credits if c]
    if credits:
        foot.append(f'<span class="src">出典: {esc("　".join(credits))}</span>')
    if foot:
        parts.append('<div class="foot">' + "<br>".join(foot) + "</div>")
    title = sc.get("heading") or sc.get("headline") or sc.get("place") or t
    return (f'<section class="scene s-{t}" data-dur="{sc.get("dur", 8)}" data-title="{esc(title)}" '
            f'data-narration="{esc(sc.get("narration", ""))}" style="--accent:{tone["accent"]}">{"".join(parts)}</section>')


def merc(lat, lon):
    p = math.radians(lat)
    return (lon + 180) / 360, (1 - math.log(math.tan(p) + 1 / math.cos(p)) / math.pi) / 2


def build_html(data):
    body = "".join(scene_html(sc, data, k) for k, sc in enumerate(data["scenes"]))
    pr = ('<aside id="pr"><div class="k">Prompter — 収録範囲の外です</div><div id="pr-idx" class="k"></div>'
          '<div id="pr-cur" class="cur"></div><div id="pr-nx" class="nx"></div>'
          '<div class="ctl">Space / → 次　← 前　R 最初から　P この欄を隠す<br>'
          '収録: Cmd+Shift+5 → 「選択部分を収録」で左の枠を囲む → マイクを選ぶ</div></aside>')
    return (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>{esc(data["title"])}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>'
            f'<body><div id="wrap"><div id="frame"><div id="stage">{isobars()}{body}</div></div>{pr}</div><script>{JS}</script></body></html>')


def build_narration(data):
    out = [f'# {data["title"]}', "", f'発表・観測日: {data.get("date", "")}', ""]
    total = 0
    for k, sc in enumerate(data["scenes"], 1):
        n = sc.get("narration", "")
        total += len(n)
        out += [f'## {k}. {sc.get("heading") or sc.get("place") or sc["type"]}（{sc.get("dur", 8)}秒目安・{len(n)}文字）', "", n, ""]
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
    out = Path(a.out) if a.out else p.with_name("short.html")
    out.write_text(build_html(data), encoding="utf-8")
    nar = out.with_name(out.stem + "_narration.md")
    nar.write_text(build_narration(data), encoding="utf-8")
    print(out)
    print(nar)


if __name__ == "__main__":
    main()
