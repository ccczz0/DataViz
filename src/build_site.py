"""
Build the static site for GitHub Pages / Vercel / any static host.

dashboard/*.html are page bodies (no <!doctype>/<head>), so this script wraps each
one in a full HTML document (charset, mobile viewport, safe-area reset) and copies
data.js next to them. Output goes to docs/ (GitHub Pages: Settings → Pages →
Deploy from a branch → main /docs).

Usage:
    python src/build_site.py
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard"
OUT = ROOT / "docs"

HEAD = """<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231d1d1f'/%3E%3Crect x='7' y='16' width='4' height='9' rx='1.5' fill='%232a78d6'/%3E%3Crect x='14' y='10' width='4' height='15' rx='1.5' fill='%232a78d6'/%3E%3Crect x='21' y='6' width='4' height='19' rx='1.5' fill='%23eb6834'/%3E%3C/svg%3E">
<style>
:root { padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
body { margin: 0; font-size: 14px; }
img { max-width: 100%; }
[hidden] { display: none !important; }
</style>
"""


def build():
    OUT.mkdir(exist_ok=True)
    for page in sorted(SRC.glob("*.html")):
        body = page.read_text(encoding="utf-8")
        # <title>/<meta>/<link>/<style> at the top of the body file stay valid inside <body>,
        # but move everything before the first real content block into <head> for tidiness.
        cut = body.find("</style>")
        head_part, rest = (body[: cut + 8], body[cut + 8:]) if cut != -1 else ("", body)
        html = HEAD + head_part + "\n</head>\n<body>\n" + rest.strip() + "\n</body>\n</html>\n"
        (OUT / page.name).write_text(html, encoding="utf-8")
        print("built", OUT / page.name)
    shutil.copy2(SRC / "data.js", OUT / "data.js")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print("copied data.js")


if __name__ == "__main__":
    build()
