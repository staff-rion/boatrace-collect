"""締切20分前〜締切の各レースの公式直前情報を取って out/ に保存する。
既に取得済みのレース一覧は done.txt(サーバーから取得)で渡す。403/503は止める(回避しない)。"""
import datetime, gzip, json, os, re, subprocess, sys, time

JST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(JST)
ds = now.strftime('%Y%m%d')
done = set(open('done.txt').read().split()) if os.path.exists('done.txt') else set()

def curl(url):
    r = subprocess.run(['curl', '-s', '--max-time', '60', '-w', '\n%{http_code}', url], capture_output=True, text=True)
    body, _, code = r.stdout.rpartition('\n')
    return code, body

code, body = curl(f'https://boatraceopenapi.github.io/programs/v2/{now.year}/{ds}.json')
if code != '200':
    print('programs', code); sys.exit(0)
races = []
for x in json.loads(body)['programs']:
    c = datetime.datetime.fromisoformat(x['race_closed_at'].replace(' ', 'T')[:19]).replace(tzinfo=JST)
    m = (c - now).total_seconds() / 60
    key = f"{x['race_stadium_number']:02d}_{x['race_number']:02d}"
    if 0 < m <= 20 and key not in done:
        races.append((m, x['race_stadium_number'], x['race_number'], key))
os.makedirs(f'out/{ds}', exist_ok=True)
got = 0
for m, j, r, key in sorted(races):
    code, h = curl(f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={r}&jcd={j:02d}&hd={ds}')
    time.sleep(3)
    if code in ('403', '503'):
        print('official', code, '停止'); break   # 回避しない。取れた分は送る
    if code != '200':
        continue
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', h, flags=re.S)
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))
    i = t.find('部品交換 前走成績')
    sec = t[i:t.find('部品交換凡例', i)] if i >= 0 else ''
    n = len(re.findall(r'kg (\d\.\d\d)', sec))
    if n == 0:
        continue  # 展示タイムが1つも無い=まだ出ていない(欠場・展示タイム無しの艇がいても、出ていれば保存)
    with gzip.open(f'out/{ds}/{key}_beforeinfo.html.gz', 'wt') as g:
        g.write(h)
    got += 1
print(now.strftime('%H:%M'), '対象', len(races), '取得', got)
