"""Xサーバーの受け取り窓口(_bi/r.php)とやり取りする。
  sync.py list  -> 今日取得済みのレース一覧を done.txt に書く
  sync.py push  -> out/ の新しいファイルを送る
署名鍵 = 環境変数 KEY(XSERVER_KEY) の空白除去後の sha256。"""
import datetime, hashlib, hmac, os, sys, urllib.request
URL = 'https://nerai-navi.com/_bi/r.php?n='
K = hashlib.sha256(''.join(os.environ['KEY'].split()).encode()).hexdigest().encode()
def post(name, body=b''):
    sig = hmac.new(K, name.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(URL + name, data=body, headers={'X-Sig': sig, 'Content-Type': 'application/octet-stream'})
    return urllib.request.urlopen(req, timeout=60).read().decode()
if sys.argv[1] == 'file':
    r = post(sys.argv[2], open(sys.argv[3], 'rb').read()); print(sys.argv[2], r)
    if r != 'ok': sys.exit('送信失敗')
elif sys.argv[1] == 'list':
    ds = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y%m%d')
    open('done.txt', 'w').write(post(ds))
else:
    n = 0
    for d in sorted(os.listdir('out')) if os.path.isdir('out') else []:
        for f in sorted(os.listdir(f'out/{d}')):
            r = post(f'{d}/{f}', open(f'out/{d}/{f}', 'rb').read()); print(f, r)
            if r != 'ok': sys.exit('送信失敗')
            n += 1
    print('送信', n)
