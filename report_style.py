"""Self-contained report styling, including the same offline fonts as the app."""
import base64
from functools import lru_cache
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def css():
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets'
    fonts = ''
    for family, filename in (('Inter', 'Inter.ttf'), ('JetBrains Mono', 'JetBrainsMono.ttf')):
        path = assets / 'fonts' / filename
        if path.exists():
            encoded = base64.b64encode(path.read_bytes()).decode()
            fonts += f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{encoded}) format('truetype');font-weight:100 900}}"
    return fonts + """body{font:14px/1.65 Inter,Arial,sans-serif;margin:0;background:#F2F1EC;color:#0E0E10}
.page{background:#FAFAF7;max-width:1250px;margin:32px auto;padding:48px;box-shadow:0 20px 50px #0001}
header{display:flex;justify-content:space-between;gap:30px;align-items:end;border-bottom:2px solid #0E0E10;padding-bottom:25px;margin-bottom:28px}
.brand{font-size:22px;font-weight:900;letter-spacing:-.04em}.brand span{font-weight:300}
.eyebrow{font:11px 'JetBrains Mono',monospace;letter-spacing:.14em;color:#6b6b68}
h1{font-size:48px;font-weight:900;letter-spacing:-.05em;line-height:1;margin:12px 0 0}h1 span{color:#E11D2A}
h2{font-size:22px;letter-spacing:-.03em;margin-top:30px}pre{white-space:pre-wrap;font:13px/1.8 Inter,Arial,sans-serif}
table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}th{background:#0E0E10;color:white;font:10px 'JetBrains Mono',monospace;text-transform:uppercase;text-align:left}td,th{padding:10px 8px;overflow-wrap:anywhere;border-bottom:1px solid #deded8;vertical-align:top}td{font:10px/1.6 'JetBrains Mono',monospace}
.toolbar{max-width:1250px;margin:20px auto;color:#6b6b68;font-size:12px}
@media print{@page{size:A4 landscape;margin:15mm}body{background:white}.page{margin:0;padding:0;box-shadow:none;max-width:none}.toolbar{display:none}tr{break-inside:avoid}thead{display:table-header-group}h2{break-after:avoid}}
"""
