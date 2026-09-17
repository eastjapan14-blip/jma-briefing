#!/usr/bin/env python3
"""生成物を iCloud Drive にコピーし、iPhone の「ファイル」→ Keynote で開けるようにする。

使い方:
  python3 scripts/deliver.py material/<dir>
コピー先: iCloud Drive/jma-briefing/<dir名>.pptx と <dir名>_台本.md
"""
import shutil, sys
from pathlib import Path

ICLOUD = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/jma-briefing"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).resolve()
    pptx, script = src / "slides.pptx", src / "script.md"
    if not pptx.exists():
        sys.exit(f"pptx がありません: {pptx}")
    ICLOUD.mkdir(parents=True, exist_ok=True)
    out = ICLOUD / f"{src.name}.pptx"
    shutil.copy2(pptx, out)
    if script.exists():
        shutil.copy2(script, ICLOUD / f"{src.name}_台本.md")
    print(f"iCloud Drive/jma-briefing/{out.name} にコピーしました。iPhone の「ファイル」アプリ → iCloud Drive → jma-briefing から Keynote で開けます")


if __name__ == "__main__":
    main()
