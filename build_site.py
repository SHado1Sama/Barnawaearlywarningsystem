"""
Build the public Barnawa EWS site: reads dashboard_template.html, splices in
the fonts (from ./fonts/*.woff2), the historical ews_data.json, and the live
live_data.json (if present), and writes dist/index.html for GitHub Pages.

Pure standard library, so CI needs nothing beyond a Python interpreter.
"""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def b64_of(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


template = open("dashboard_template.html", encoding="utf-8").read()
data_json = open("ews_data.json", encoding="utf-8").read()
live_json = open("live_data.json", encoding="utf-8").read() if os.path.exists("live_data.json") else "null"
history_json = open("history.json", encoding="utf-8").read() if os.path.exists("history.json") else "[]"

replacements = {
    "__ARCHIVO_B64__": b64_of("fonts/archivo.woff2"),
    "__PUBLICSANS_B64__": b64_of("fonts/publicsans.woff2"),
    "__PLEXMONO400_B64__": b64_of("fonts/plexmono400.woff2"),
    "__PLEXMONO500_B64__": b64_of("fonts/plexmono500.woff2"),
    "__PLEXMONO600_B64__": b64_of("fonts/plexmono600.woff2"),
    "__MAP_OVERVIEW_B64__": b64_of("maps/overview.png"),
    "__EWS_DATA_JSON__": data_json,
    "__LIVE_DATA_JSON__": live_json,
    "__HISTORY_DATA_JSON__": history_json,
}

out = template
for k, v in replacements.items():
    if k not in out:
        raise SystemExit(f"placeholder missing: {k}")
    out = out.replace(k, v)

os.makedirs("dist", exist_ok=True)
with open("dist/index.html", "w", encoding="utf-8") as f:
    f.write(out)

print("wrote dist/index.html, bytes:", len(out.encode("utf-8")))
