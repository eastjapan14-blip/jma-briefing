#!/usr/bin/env python3
"""気象庁公式YouTubeの記者会見を文字起こしする（段階A）。

使い方:
  python3 scripts/transcribe.py <YouTubeのURLまたはID> --out material/<dir> [--section 00:00-10:00]
出力:
  <out>/raw/conference.m4a   音声
  <out>/transcript.md        [mm:ss] 付きの文字起こし（質疑の位置を探しやすい）
mlx-whisper（Apple Silicon）を使う。75分の会見で6分前後。
"""
import argparse, re, subprocess, sys
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"
PROMPT = "気象庁の記者会見。台風、梅雨前線、大雨、線状降水帯、特別警報、警戒レベル、暴風域、予報円、キキクル、土砂災害、高潮。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="例 00:00-10:00（試し用）")
    a = ap.parse_args()
    out = Path(a.out); (out / "raw").mkdir(parents=True, exist_ok=True)
    vid = a.video if a.video.startswith("http") else f"https://www.youtube.com/watch?v={a.video}"
    audio = out / "raw" / "conference.m4a"
    cmd = ["yt-dlp", "-q", "-x", "--audio-format", "m4a", "-o", str(audio.with_suffix(".%(ext)s")), vid]
    if a.section:
        cmd[1:1] = ["--download-sections", f"*{a.section}"]
    title = subprocess.run(["yt-dlp", "--print", "%(title)s|%(upload_date)s|%(duration)s", vid], capture_output=True, text=True).stdout.strip()
    subprocess.run(cmd, check=True)
    import mlx_whisper
    r = mlx_whisper.transcribe(str(audio), path_or_hf_repo=MODEL, language="ja", initial_prompt=PROMPT)
    lines = [f"# 記者会見の文字起こし", f"- 動画: {vid}", f"- タイトル|投稿日|秒数: {title}", "", "自動文字起こしのため固有名詞・数値は誤りがある。台本に使う数値は必ず報道資料（press.md）か素材（source.md）で照合する。", ""]
    for seg in r["segments"]:
        t = int(seg["start"])
        lines.append(f"[{t//60:02d}:{t%60:02d}] {seg['text'].strip()}")
    (out / "transcript.md").write_text("\n".join(lines), encoding="utf-8")
    print(f'{out / "transcript.md"}  {len(r["segments"])} 区間 / {len(r["text"])} 文字')


if __name__ == "__main__":
    main()
