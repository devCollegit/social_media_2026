from pathlib import Path
import os,urllib.request,xml.etree.ElementTree as ET,csv,time,json
R=Path(__file__).resolve().parent;os.environ['SSL_CERT_FILE']=str(R/'private/system_ca.pem')
for code in ['005380','010120']:
 try:
  u=f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=180&requestType=0'
  raw=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read()
  data=[]
  for item in ET.fromstring(raw.decode('euc-kr')).iter('item'):
   a=item.attrib['data'].split('|');d=f'{a[0][:4]}-{a[0][4:6]}-{a[0][6:8]}'
   if '2026-07-01'<=d<='2026-10-27':data.append(dict(zip(['date','open','high','low','close','volume'],[d]+a[1:])))
  with (R/'private'/f'{code}_market.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['date','open','high','low','close','volume']);w.writeheader();w.writerows(data)
  print(code,len(data),flush=True)
 except Exception as e:print(code,type(e).__name__,str(e)[:90],flush=True)
 time.sleep(2)
