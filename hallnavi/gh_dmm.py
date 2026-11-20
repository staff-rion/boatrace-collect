"""DMMぱちタウンの1週間分取材予定(全県)を dmm_week.json に保存。XサーバーからはDMMが403のためGitHubで取る。"""
import datetime, json
from prefs import PREF_JA
import src_week as W
rows = []
for rom in PREF_JA:
    r = W.src_dmm(rom); rows += [dict(x, _rom=rom) for x in r]
    print(PREF_JA[rom], len(r), flush=True)
json.dump({"made": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="minutes"), "rows": rows},
          open("dmm_week.json", "w", encoding="utf-8"), ensure_ascii=False)
print("DMM計", len(rows))
