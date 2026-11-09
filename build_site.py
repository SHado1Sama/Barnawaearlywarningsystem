"""
Build the public Barnawa EWS site: reads dashboard_template.html, splices in
the fonts (from ./fonts/*.woff2), the historical ews_data.json, and the live
live_data.json (if present), and writes dist/index.html for GitHub Pages.
Also places the visitor site guide in dist/ so the download link on the
page resolves: the deck is stored in the repo base64-encoded as
Barnawa_EWS_Site_Walkthrough.pptx.b64 (the repo's file pipeline is
text-only), and this build decodes it back to the .pptx.

Pure standard library, so CI needs nothing beyond a Python interpreter.
"""
import base64
import json
import os

import forecast

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def b64_of(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


template = open("dashboard_template.html", encoding="utf-8").read()
# Historical data, plus the forecast replay of each stored case study with and without the
# wet-season floor (forecast.py). The replay is computed here from the stored rainfall, so the
# numbers on the page always come from the code and nothing is typed in by hand.
_data = json.load(open("ews_data.json", encoding="utf-8"))
for _cs in _data["case_studies"]:
    _cs["model_check"] = forecast.replay_case(_cs, _data["thresholds"])
data_json = json.dumps(_data, separators=(",", ":"))
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

_guide_b64 = os.path.join(HERE, "Barnawa_EWS_Site_Walkthrough.pptx.b64")
_guide_out = os.path.join("dist", "Barnawa_EWS_Site_Walkthrough.pptx")
if os.path.exists(_guide_b64):
    with open(_guide_b64, encoding="ascii") as f:
        _guide_bytes = base64.b64decode(f.read())
    with open(_guide_out, "wb") as f:
        f.write(_guide_bytes)
    print("decoded site guide into dist/, bytes:", len(_guide_bytes))
