#!/usr/bin/env python3
"""
1週間先までの取材予定を「取材日程サイト」から集めて week_schedule.json に保存。
build_future_schedule.py がこれを読み、SNS告知(今日・明日)に足して future_<県>.json を作る。

ソース:
  ・スロパチステーション  /report_schedule_pref/<県>/page/N（日付順）
  ・じゃんじゃん  schedule.php（全国1ページ）
  ・DMMぱちタウン  /schedules/<県>?page=N
      日付指定は効かず、今日から日付順に20件ずつ並ぶ → 7日先を超えた所でページ送りを止める。
      1件 = 店名 / 住所 / 実施日：YYYY/MM/DD / 媒体 / 企画名
  ・(停止中) ホールナビ  /serch_sche_result?ymd=YYYY-MM-DD&k[]=<県コード>   (50件/ページ・8日先まで)
      上位は「会員登録して表示する」で店名が隠れる。★ログインはしない＝店名が見える分だけ使う。
出力: [{"date":"YYYY/MM/DD","pref":"埼玉県","shop":..,"event":..,"addr":..,"src":"DMM"|"HN"}, ...]
使い方: python3 src_week.py            (全国)
        python3 src_week.py saitama    (県指定・テスト用)
"""
import re, sys, json, time, datetime
from bs4 import BeautifulSoup
from prefs import PREF_JA
import aggregate_events as A

HORIZON = 7
OUT = "week_schedule.json"
TODAY = datetime.date.today()
LAST = TODAY + datetime.timedelta(days=HORIZON)
DATE = re.compile(r"実施日：(\d{4})/(\d{1,2})/(\d{1,2})")


def _lines(h):
    return [l.strip() for l in BeautifulSoup(h or "", "html.parser").get_text("\n").split("\n") if l.strip()]


PREF_RE = re.compile(r"^(北海道|東京都|京都府|大阪府|.{2,3}?県)")


def _is_addr(s):
    return bool(PREF_RE.match(s)) and len(s) < 60


def src_dmm(rom):
    out = []
    for page in range(1, 60):
        L = _lines(A.get(f"https://p-town.dmm.com/schedules/{rom}?page={page}"))
        got, beyond = 0, False
        for i, l in enumerate(L):
            m = DATE.match(l)
            if not m:
                continue
            got += 1
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d > LAST:
                beyond = True
                continue
            # 住所は実施日の1〜3行前（間に「当日は撮影等…」の注記が入る店がある）。店名は住所の1行前。
            a = next((j for j in range(i - 1, max(i - 4, 0), -1) if _is_addr(L[j])), None)
            if d <= TODAY or a is None or a < 1:
                continue
            media = L[i + 1] if i + 1 < len(L) else ""
            title = L[i + 2] if i + 2 < len(L) and L[i + 2] != "PR" and not _is_addr(L[i + 2]) else ""
            ev = f"{media} {title}".strip() if title and title != media else media
            out.append({"date": d.strftime("%Y/%m/%d"), "pref": PREF_RE.match(L[a]).group(1),
                        "shop": L[a - 1], "event": ev, "addr": L[a], "src": "DMM"})
        if not got or beyond:
            break
        time.sleep(1.0)
    return out


def src_slopachi(rom):
    """スロパチステーション 県別予定 /report_schedule_pref/<県>/page/N。
    並び: 「M/D (」「曜」「)」「【県市区】」「取材名<TAB…>店名」。日付順なので7日先を超えたら止める。"""
    out = []
    base = f"https://777.slopachi-station.com/report_schedule_pref/{rom}/"
    for page in range(1, 30):
        L = _lines(A.get(base if page == 1 else f"{base}page/{page}"))
        got, beyond = 0, False
        for i, l in enumerate(L):
            m = re.fullmatch(r"(\d{1,2})/(\d{1,2})\s*\(", l)
            if not m or i + 4 >= len(L):
                continue
            pm = re.match(r"【((?:北海道|東京都|京都府|大阪府|.{2,3}?県).*)】", L[i + 3])
            if not pm:
                continue
            got += 1
            mo, d = int(m.group(1)), int(m.group(2))
            y = TODAY.year + (1 if mo < TODAY.month - 6 else 0)
            dd = datetime.date(y, mo, d)
            if dd > LAST:
                beyond = True; continue
            if dd <= TODAY:
                continue
            parts = [x.strip() for x in re.split(r"[\t\xa0]+", L[i + 4]) if x.strip()]
            if len(parts) < 2:
                continue
            ev, shop = parts[0], parts[-1]
            out.append({"date": dd.strftime("%Y/%m/%d"), "pref": PREF_RE.match(pm.group(1)).group(1),
                        "shop": shop, "event": ev if ev.startswith("スロパチ") else f"スロパチステーション {ev}", "addr": pm.group(1), "src": "SP"})
        if not got or beyond:
            break
        time.sleep(1.0)
    return out


def src_jyanjyan():
    """じゃんじゃん 全国の予定(1ページ)。build_future_schedule の既存パーサを使う。"""
    import build_future_schedule as B
    out = []
    for date, pref, hall, event in B.src_jyanjyan():
        try:
            dd = datetime.date(*map(int, date.split("/")))
        except Exception:
            continue
        if TODAY < dd <= LAST and hall:
            out.append({"date": dd.strftime("%Y/%m/%d"), "pref": pref, "shop": hall,
                        "event": f"じゃんじゃん {event}".strip(), "addr": "", "src": "JJ"})
    return out


def src_hallnavi(pages_per_day=10, only_prefs=None):
    """ホールナビ全エリア。店名が見えるカードだけ。
    ★同じブラウザ文脈で続けて開くと空ページが返る（弾かれる）→ エリア・県ごとに新しい文脈を作り直す。"""
    import hall_navi as H
    from playwright.sync_api import sync_playwright
    out = []
    areas = ["hokkaido", "tohoku", "kanto", "chubu", "kansai", "chugoku", "sikoku", "kyusyu"]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        for area in areas:
            ctx = b.new_context(user_agent=H.UA)
            try:
                pg = ctx.new_page()
                pg.goto(f"https://hall-navi.com/?area={area}", wait_until="networkidle", timeout=30000)
                ks = pg.eval_on_selector_all(
                    "a[href*='serch_sche_result?k=']",
                    "els=>els.map(e=>[e.getAttribute('href'), e.innerText.trim()])")
            except Exception as e:
                print(f"  HN {area} ERR {e}", flush=True); ctx.close(); continue
            ctx.close()
            kmap = {}
            for href, txt in ks:
                m = re.search(r"k=(\d+)", href or "")
                pm = PREF_RE.match(txt or "")
                if m and pm:
                    kmap[m.group(1)] = pm.group(1)
            if not kmap:
                print(f"  HN {area}: 県コード取得できず", flush=True)
            for k, pref in kmap.items():
                if only_prefs and pref not in only_prefs:
                    continue
                before = len(out)
                ctx = b.new_context(user_agent=H.UA)
                pg = ctx.new_page()
                try:
                    pg.goto(f"https://hall-navi.com/?area={area}", wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                for dd in range(HORIZON + 1):
                    ymd = (TODAY + datetime.timedelta(days=dd)).isoformat()
                    for page in range(1, pages_per_day + 1):
                        url = f"https://hall-navi.com/serch_sche_result?ymd={ymd}&k%5B%5D={k}" + (f"&page={page}" if page > 1 else "")
                        try:
                            pg.goto(url, wait_until="networkidle", timeout=30000)
                            t = pg.inner_text("body")
                        except Exception as e:
                            print(f"  HN {pref} {ymd} p{page} ERR {e}", flush=True); break
                        n = _parse_hn(t, ymd, pref, out)
                        if n == 0 or "次へ" not in t:
                            break
                        time.sleep(1.2)
                    time.sleep(1.2)
                ctx.close()
                print(f"  HN {pref}: {len(out) - before}件", flush=True)
                time.sleep(2)
        b.close()
    return out


def _parse_hn(text, ymd, pref, out):
    """一覧のカード(「NN.N点」〜次の「NN.N点」)を切り出し、店名が見えるものだけ拾う。-> そのページのカード数"""
    y, mo, d = ymd.split("-")
    date_s = f"{int(y)}/{int(mo):02d}/{int(d):02d}"
    want = f"{y}/{mo}/{d}"
    i = text.find("のスケジュール一覧")
    body = text[i:] if i >= 0 else text
    cards = re.split(r"\n\s*\d+\.\d点\s*\n", body)[1:]
    n = 0
    for c in cards:
        L = [l.strip() for l in c.split("\n") if l.strip()]
        if not L or not L[0].startswith(want):
            continue
        n += 1
        if any("会員登録して表示する" in l for l in L):
            continue
        shop = L[1] if len(L) > 1 else ""
        if not shop or _is_addr(shop) or shop.endswith("県"):
            continue
        evs, addr = [], ""
        for j, l in enumerate(L[2:], 2):
            if _is_addr(l):
                addr = l; break
            if re.fullmatch(r"[SABC他]", l) and j + 1 < len(L):
                evs.append(L[j + 1])
        # 「ナビ子AI予想」はホールナビ独自の予想で取材告知ではない（事実のみ）→ 除外。
        #  括弧内の旧イベ(1のつく日・周年 等)だけは事実なので kyuibe として残す。
        kyuibe, real = [], []
        for e in evs:
            if re.match(r"取材/予想", e):
                continue
            for k in re.findall(r"[（(]([^)）]*(?:のつく日|周年|ゾロ目|月[0-9０-９]+日)[^)）]*)[)）]", e):
                kyuibe.append(k.strip())
            if e.startswith("ナビ子"):
                continue
            real.append(re.sub(r"\s*[（(][^)）]*[)）]\s*$", "", e).strip() or e)
        if not real and not kyuibe:
            continue
        out.append({"date": date_s, "pref": pref, "shop": shop, "event": " / ".join(real),
                    "kyuibe": kyuibe, "addr": addr, "src": "HN"})
    return n


def main():
    only = sys.argv[1:]
    roms = only or list(PREF_JA.keys())
    rows = []
    t0 = time.time()
    for rom in roms:
        r = src_dmm(rom)
        r2 = src_slopachi(rom)
        rows += r + r2
        print(f"  {PREF_JA.get(rom, rom)}: DMM {len(r)}件 / スロパチ {len(r2)}件", flush=True)
        time.sleep(1.0)
    if not only:
        r = src_jyanjyan()
        rows += r
        print(f"  じゃんじゃん(全国): {len(r)}件", flush=True)
    t1 = time.time()
    # ホールナビは自動アクセスを Cloudflare でブロックしている（"Sorry, you have been blocked"・10/27確認）。
    # ボット対策の回避はしない＝夜間の自動取得には使わない。src_hallnavi() は残すが呼ばない。
    t2 = time.time()
    json.dump({"made": datetime.datetime.now().isoformat(timespec="minutes"), "rows": rows},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    by = {}
    for r in rows:
        by[r["src"]] = by.get(r["src"], 0) + 1
    print(f"# week_schedule: {len(rows)}件 {by}  DMM {t1-t0:.0f}秒 / HN {t2-t1:.0f}秒")


if __name__ == "__main__":
    main()
