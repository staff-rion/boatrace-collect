#!/usr/bin/env python3
"""
ホールナビ(hall-navi.com) scraper — 本命ソース。
Cloudflareで403なのでPlaywright(headless)必須。/?area=<slug>でcookie踏み→serch_sche_result?k=<県コード>。
店×取材×台数×平均差枚×旧イベ を構造化して JSON/DB に出す。
使い方: python3 hall_navi.py            (関東=全県コード巡回)
        python3 hall_navi.py 3          (県コードk=3だけ)
"""
import re, sys, json, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
AREA = "kanto"  # エリアslug(cookie用)。全国=hokkaido/tohoku/kanto/chubu/kansai/chugoku/sikoku/kyusyu
# 関東の県コード(serch_sche_result?k=)
KCODE = {1: "東京", 2: "神奈川", 3: "埼玉", 4: "千葉", 5: "茨城", 6: "栃木", 7: "群馬"}


def parse_cards(text):
    """body innerText をカード単位(フッタ '結果レポートN件 / スケジュール…' 区切り)で分解。"""
    lines = [l.strip() for l in text.split("\n")]
    recs = []
    buf = []
    cur_date = None
    footer = re.compile(r"結果レポート[\d,]+件")
    for l in lines:
        md = re.match(r"^(\d{1,2}/\d{1,2})\([月火水木金土日]\)$", l)
        if md:
            cur_date = md.group(1)  # 直近の日付見出しを引き継ぐ
        buf.append(l)
        if footer.search(l):  # 1カードの終わり
            block = buf
            buf = []
            txt = "\n".join(block)
            m = re.search(r"(\d+)台\s*平均([+\-][\d,]+)枚", txt)
            if not m:
                continue
            # このカード内に日付見出しがあればそれ、無ければ直近
            dm = [x for x in block if re.match(r"^\d{1,2}/\d{1,2}\([月火水木金土日]\)$", x)]
            date = dm[-1][:dm[-1].find("(")] if dm else cur_date
            addr = next((x for x in block if re.search(r"[都道府県].+[市区町村]", x)), "")
            # 店名: 日付見出し/EXCELLENT/空 を除いた最初の実名
            shop = ""
            for x in block:
                if (x and x != "EXCELLENT!!" and not re.match(r"^\d{1,2}/\d{1,2}\(", x)
                        and "台 平均" not in x and "uu" not in x):
                    shop = x
                    break
            kyuibe = [x for x in block if "旧イベ" in x]
            toku = [x for x in block if ("取材" in x or "来店" in x) and "旧イベ" not in x]
            recs.append({
                "date": date, "shop": shop, "addr": addr,
                "dai": int(m.group(1)), "avg_diff": int(m.group(2).replace(",", "")),
                "toku": toku[:4], "kyuibe": kyuibe[:3],
            })
    return recs


def scrape(kcodes):
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=UA)
        pg.goto(f"https://hall-navi.com/?area={AREA}", wait_until="domcontentloaded", timeout=30000)
        for k in kcodes:
            got = 0
            for page in range(1, 12):
                url = f"https://hall-navi.com/serch_sche_result?k={k}" + (f"&page={page}" if page > 1 else "")
                try:
                    pg.goto(url, wait_until="networkidle", timeout=30000)
                    recs = parse_cards(pg.inner_text("body"))
                except Exception as e:
                    print(f"  k={k} p{page} ERR {e}", flush=True)
                    break
                if not recs:
                    break
                for r in recs:
                    r["pref"] = KCODE.get(k, str(k))
                out += recs
                got += len(recs)
                time.sleep(1.5)
            print(f"  k={k}({KCODE.get(k,k)}): {got}カード", flush=True)
        b.close()
    return out


if __name__ == "__main__":
    ks = [int(sys.argv[1])] if len(sys.argv) > 1 else list(KCODE)
    print(f"# ホールナビ area={AREA} k={ks}")
    recs = scrape(ks)
    json.dump(recs, open("hallnavi_latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n=== {len(recs)}カード 保存: hallnavi_latest.json ===")
    for r in recs[:10]:
        kb = ("｜旧イベ:" + r["kyuibe"][0][:30]) if r["kyuibe"] else ""
        print(f"  {r['date']} {r['shop'][:18]}  {r['dai']}台 平均{r['avg_diff']:+,}枚  取材:{'/'.join(t[:12] for t in r['toku'][:2])}{kb}")
