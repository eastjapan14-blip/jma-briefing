#!/usr/bin/env python3
"""国土地理院の標高タイルから、ショート動画用の暗色の地形図 PNG を描く。

出典: 国土地理院「標高タイル（基盤地図情報数値標高モデル）」を加工。動画の出典欄に「地図: 国土地理院 標高タイルを加工」と書く。
境界: scripts/data/japan_pref.json（dataofjapan/land の TopoJSON を簡略化。元データは国土数値情報 行政区域）。

使い方:
  python3 scripts/render_map.py --points 35.3967,140.1483 35.235,140.0983 ... --pref 千葉県 \
      --out material/<dir>/images/map.png [--size 1080x830] [--inner 80,70,860,640] [--exag 2.5]
  → map.png と map.json（投影パラメータ。build_short.py が地点の画素位置と縮尺を計算する）

--center lat,lon --at x,y --km-across N で「この地点をこの画素に、横幅 N km で」描ける（ズーム導入の層に使う）。
--points で与えた地点が --inner の矩形（左,上,右,下 px）に収まるように縮尺を決める。右と下は Shorts の UI と
見出しの重なりを避けるため余白を大きめにとる。タイルは ~/.cache/jma-briefing/gsi にキャッシュする。
"""
import argparse, io, json, math, sys, time, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TILE = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png"
CACHE = Path.home() / ".cache" / "jma-briefing" / "gsi" / "dem_png"
PREF = Path(__file__).resolve().parent / "data" / "japan_pref.json"

SEA = np.array([9, 14, 22], float)
LAND = np.array([30, 38, 48], float)
COAST_GLOW = np.array([26, 52, 70], float)
COAST_LINE = np.array([150, 190, 210], float)


def merc(lat, lon):
    """緯度経度 → 世界座標（0..1）。"""
    p = math.radians(lat)
    return (lon + 180) / 360, (1 - math.log(math.tan(p) + 1 / math.cos(p)) / math.pi) / 2


def fetch_tile(z, x, y):
    p = CACHE / str(z) / str(x) / f"{y}.png"
    if p.exists():
        data = p.read_bytes()
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(TILE.format(z=z, x=x, y=y), timeout=30) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            data = b""
        p.write_bytes(data)
        time.sleep(0.05)
    if not data:
        return np.full((256, 256), np.nan)
    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.int64)
    v = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    h = np.where(v > 2 ** 23, v - 2 ** 24, v) * 0.01
    return np.where(v == 2 ** 23, np.nan, h)


def dilate(m, k):
    out = m.copy()
    for _ in range(k):
        o = out.copy()
        o[1:] |= out[:-1]; o[:-1] |= out[1:]; o[:, 1:] |= out[:, :-1]; o[:, :-1] |= out[:, 1:]
        out = o
    return out


def shade_rgb(E, cell_m, exag, az=315.0, alt=45.0):
    """標高配列 → RGB float 配列（暗色の陰影段彩）。"""
    sea = np.isnan(E)
    Z = np.where(sea, 0.0, E)
    dzdy, dzdx = np.gradient(Z, cell_m)
    zen = math.radians(90 - alt)
    azm = math.radians(360 - az + 90)
    slope = np.arctan(exag * np.hypot(dzdx, dzdy))
    aspect = np.arctan2(dzdy, -dzdx)
    hs = np.clip(math.cos(zen) * np.cos(slope) + math.sin(zen) * np.sin(slope) * np.cos(azm - aspect), 0, 1)
    f = 0.45 + 1.1 * hs
    tint = np.sqrt(np.clip(Z / 2000.0, 0, 1))[..., None] * np.array([46, 50, 44], float)
    rgb = LAND[None, None, :] * f[..., None] + tint
    rgb = np.where(sea[..., None], SEA[None, None, :], rgb)
    # 海岸の淡い光: 陸から 1〜7px の海
    land = ~sea
    prev = land
    for k in range(1, 8):
        d = dilate(prev, 1)
        ring = d & ~prev & sea
        a = 0.55 * (1 - k / 8)
        rgb[ring] = rgb[ring] * (1 - a) + COAST_GLOW * a
        prev = d
    # 海岸線
    edge = land & ~(land & dilate(sea, 1) == False)  # 陸のうち海に接する画素
    edge = land & dilate(sea, 1)
    rgb[edge] = rgb[edge] * 0.35 + COAST_LINE * 0.65
    # 等高線（100m ごと）
    lvl = np.floor(np.where(sea, -1, Z) / 100.0)
    c = np.zeros_like(sea)
    c[:, 1:] |= (lvl[:, 1:] != lvl[:, :-1]) & land[:, 1:] & land[:, :-1]
    c[1:, :] |= (lvl[1:, :] != lvl[:-1, :]) & land[1:, :] & land[:-1, :]
    rgb[c] = rgb[c] * 0.8 + np.array([120, 140, 150], float) * 0.2
    return np.clip(rgb, 0, 255)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", nargs="*", default=[], help="lat,lon ...")
    ap.add_argument("--bbox", help="S,W,N,E（--points の代わり）")
    ap.add_argument("--pref", nargs="*", default=[], help="強調する都道府県名")
    ap.add_argument("--size", default="1080x830")
    ap.add_argument("--inner", default="80,70,860,640", help="地点を収める矩形 左,上,右,下（px）")
    ap.add_argument("--exag", type=float, default=3.5, help="陰影の起伏強調")
    ap.add_argument("--min-span-km", type=float, default=40.0)
    ap.add_argument("--center", help="lat,lon: この地点を --at の画素に置く（--km-across と併用。--points/--bbox の代わり）")
    ap.add_argument("--at", help="x,y px（--center の置き場所。既定は画像中央）")
    ap.add_argument("--km-across", type=float, help="画像の横幅の実距離 km（--center と併用）")
    ap.add_argument("--no-borders", action="store_true", help="県境線を描かない（全国スケール用。--pref の塗りは残る）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    W, H = (int(v) for v in a.size.lower().split("x"))
    ix0, iy0, ix1, iy1 = (int(v) for v in a.inner.split(","))
    if a.center:
        if not a.km_across:
            sys.exit("--center には --km-across が必要")
        lat_c, lon_c = (float(v) for v in a.center.split(","))
        world_m = 40075016.686 * math.cos(math.radians(lat_c))
        s = W / (a.km_across * 1000 / world_m)
        ax, ay = (float(v) for v in a.at.split(",")) if a.at else (W / 2, H / 2)
        mx_c, my_c = merc(lat_c, lon_c)
        wx0, wy0 = mx_c - ax / s, my_c - ay / s
    else:
        if a.bbox:
            s_, w_, n_, e_ = (float(v) for v in a.bbox.split(","))
            pts = [(s_, w_), (n_, e_)]
        else:
            pts = [tuple(float(v) for v in p.split(",")) for p in a.points]
        if not pts:
            sys.exit("--points か --bbox か --center が必要")
        ws = [merc(lat, lon) for lat, lon in pts]
        lat_c = sum(p[0] for p in pts) / len(pts)
        mx0, mx1 = min(w[0] for w in ws), max(w[0] for w in ws)
        my0, my1 = min(w[1] for w in ws), max(w[1] for w in ws)
        world_m = 40075016.686 * math.cos(math.radians(lat_c))   # 1 世界単位の実距離（この緯度）
        min_span = a.min_span_km * 1000 / world_m
        dmx, dmy = max(mx1 - mx0, min_span), max(my1 - my0, min_span)
        s = min((ix1 - ix0) / dmx, (iy1 - iy0) / dmy)               # px / 世界単位
        cx, cy = (mx0 + mx1) / 2, (my0 + my1) / 2
        wx0 = cx - ((ix0 + ix1) / 2) / s
        wy0 = cy - ((iy0 + iy1) / 2) / s
    wx1, wy1 = wx0 + W / s, wy0 + H / s
    z = int(min(14, max(5, math.ceil(math.log2(s / 256)))))
    n = 2 ** z
    tx0, tx1 = int(wx0 * n), int(wx1 * n)
    ty0, ty1 = int(wy0 * n), int(wy1 * n)
    print(f"zoom {z}, tiles {(tx1-tx0+1)*(ty1-ty0+1)}, scale {s:.0f} px/world, {1000*world_m/(s*1000):.0f} m/px")
    E = np.full(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.nan)
    done = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            E[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = fetch_tile(z, tx, ty)
            done += 1
            if done % 40 == 0:
                print(f"  tiles {done}", flush=True)
    cell_m = world_m / (256 * n)
    rgb = shade_rgb(E, cell_m, a.exag)
    img = Image.fromarray(rgb.astype(np.uint8))
    # 画像の世界座標範囲を切り出して出力サイズへ
    px0, py0 = (wx0 * n - tx0) * 256, (wy0 * n - ty0) * 256
    px1, py1 = (wx1 * n - tx0) * 256, (wy1 * n - ty0) * 256
    box = (int(px0), int(py0), int(math.ceil(px1)), int(math.ceil(py1)))
    img = img.crop(box).resize((W, H), Image.LANCZOS)
    near_sea = Image.fromarray((np.isnan(E) * 255).astype(np.uint8)).crop(box).resize((W, H), Image.BILINEAR)
    near_sea = near_sea.filter(ImageFilter.MaxFilter(21)).point(lambda v: 255 if v > 8 else 0)

    # 都道府県境界
    def to_px(lon, lat):
        x, y = merc(lat, lon)
        return ((x - wx0) * s, (y - wy0) * s)
    prefs = json.loads(PREF.read_text(encoding="utf-8"))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for name, rings in prefs.items():
        for r in rings:
            pp = [to_px(x, y) for x, y in r]
            if not any(-50 <= x <= W + 50 and -50 <= y <= H + 50 for x, y in pp):
                continue
            hi = name in a.pref
            if hi:
                m = Image.new("L", (W, H), 0)
                ImageDraw.Draw(m).polygon(pp, fill=255)
                lift = Image.new("RGBA", (W, H), (255, 255, 255, 14))
                overlay.paste(lift, (0, 0), m)
    lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for name, rings in ({} if a.no_borders else prefs).items():
        for r in rings:
            pp = [to_px(x, y) for x, y in r]
            if not any(-50 <= x <= W + 50 and -50 <= y <= H + 50 for x, y in pp):
                continue
            hi = name in a.pref
            ImageDraw.Draw(lines).line(pp + [pp[0]], fill=(255, 255, 255, 150 if hi else 55), width=3 if hi else 2, joint="curve")
    # 海岸から離れた内陸の県境だけ残す
    la = np.asarray(lines)
    keep = (np.asarray(near_sea) == 0)
    la = la.copy(); la[..., 3] = np.where(keep, la[..., 3], 0)
    lines = Image.fromarray(la)
    img = Image.alpha_composite(Image.alpha_composite(img.convert("RGBA"), overlay), lines).convert("RGB")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    meta = {"w": W, "h": H, "wx0": wx0, "wy0": wy0, "s": s, "z": z, "lat_c": lat_c,
            "px_per_km": s * 1000 / world_m,
            "credit": "地図: 国土地理院 標高タイルを加工"}
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out, out.with_suffix(".json"))


if __name__ == "__main__":
    main()
