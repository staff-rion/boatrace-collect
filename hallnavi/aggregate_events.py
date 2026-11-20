#!/usr/bin/env python3
"""
① 全媒体のイベント抽出（アグリゲーター）
複数ソース(スロパチ/DMMぱちタウン/…)から指定日の取材を集め、店×日付で名寄せ統合する。
新しい媒体は SOURCES に関数を足すだけで拡張できる。
使い方: python3 aggregate_events.py <pref> [M/D]
"""
import re, sys, json, time, datetime, urllib.request
from bs4 import BeautifulSoup
from prefs import PREF_JA

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
# DMM都道府県コード(1=北海道…)。スロパチはローマ字スラッグ。
DMM_PREF = {p: i + 1 for i, p in enumerate(PREF_JA)}


def get(url):
    for _ in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25).read().decode("utf-8", "replace")
        except Exception:
            time.sleep(3)
    return ""


def norm(s):
    """店名の名寄せキー: 空白/記号/全半角ゆらぎを吸収"""
    s = re.sub(r"[\s　]", "", s or "")
    s = s.replace("Ｄ", "D").replace("Ｓ", "S")
    for ch in "’'！!（）()　":
        s = s.replace(ch, "")
    s = re.sub(r"[店舗]$", "", s)
    s = s.replace("新!", "新").replace("新！", "新")
    return s.strip()


# ---- ソース1: スロパチステーション(県別スケジュール) ----
def src_slopachi(pref, mmdd):
    out = []
    base = "https://777.slopachi-station.com/report_schedule_pref"
    for p in range(1, 9):
        url = f"{base}/{pref}/" if p == 1 else f"{base}/{pref}/page/{p}"
        html = get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        found = 0
        for a in soup.find_all("a", href=True):
            m = re.search(r"/shop_data/(\d+)", a["href"])
            if not m:
                continue
            found += 1
            blk = a
            for _ in range(4):
                if blk.parent:
                    blk = blk.parent
            txt = re.sub(r"\s+", " ", blk.get_text(" ", strip=True))
            if mmdd in txt:
                name = re.sub(r"\s+", " ", a.get_text(strip=True))
                shop = name.split(" ")[-1]
                ev = name.rsplit(" ", 1)[0] if " " in name else ""
                out.append({"shop": shop, "media": "スロパチ", "event": ev, "sid": m.group(1)})
        if found == 0:
            break
    return out


# ---- ソース2: DMMぱちタウン(/schedules) ----
def src_dmm(pref, mmdd):
    out = []
    y, mo, d = 2026, int(mmdd.split("/")[0]), int(mmdd.split("/")[1])
    pcode = DMM_PREF[pref]
    base = f"https://p-town.dmm.com/schedules?start_date%5Byear%5D={y}&start_date%5Bmonth%5D={mo}&start_date%5Bday%5D={d}&prefecture={pcode}"
    want = f"実施日：{y}/{mo}/{d}"
    for pg in range(1, 10):
        url = base + (f"&page={pg}" if pg > 1 else "")
        html = get(url)
        if not html:
            break
        lines = [l.strip() for l in BeautifulSoup(html, "html.parser").get_text("\n").split("\n") if l.strip()]
        cnt = 0
        for i, l in enumerate(lines):
            if l == want:
                addr = shop = media = None
                for j in range(i - 1, max(i - 7, -1), -1):
                    if "県" in lines[j] and addr is None and len(lines[j]) < 40:
                        addr = lines[j]
                    elif addr and shop is None and lines[j] != "PR":
                        shop = lines[j]
                # 取材名(媒体)は実施日の次行
                if i + 1 < len(lines):
                    media = lines[i + 1]
                if shop:
                    out.append({"shop": shop, "media": f"DMM/{media or '?'}", "event": media or ""})
                    cnt += 1
        if cnt == 0 or cnt < 20:
            break
        time.sleep(1)
    return out


SOURCES = [src_slopachi, src_dmm]


def aggregate(pref, mmdd):
    merged = {}  # key= norm(shop) -> {shop, date, medias:set, raw:[]}
    for src in SOURCES:
        try:
            rows = src(pref, mmdd)
        except Exception as e:
            print(f"  [{src.__name__}] ERR {e}")
            rows = []
        for r in rows:
            k = norm(r["shop"])
            if not k:
                continue
            m = merged.setdefault(k, {"shop": r["shop"], "date": mmdd, "medias": set(), "events": set()})
            m["medias"].add(r["media"])
            if r.get("event"):
                m["events"].add(r["event"])
        print(f"  [{src.__name__}] {len(rows)}件")
    return merged


if __name__ == "__main__":
    pref = sys.argv[1] if len(sys.argv) > 1 else "saitama"
    mmdd = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().strftime("%-m/%-d")
    print(f"# {PREF_JA.get(pref,pref)} {mmdd} 全媒体統合")
    merged = aggregate(pref, mmdd)
    rows = sorted(merged.values(), key=lambda m: -len(m["medias"]))
    print(f"\n=== 名寄せ後 {len(rows)}店（媒体数が多い順＝複数媒体取材＝アツい）===")
    for m in rows:
        med = ", ".join(sorted(m["medias"]))
        print(f"  [{len(m['medias'])}媒体] {m['shop']}  ← {med}")
