"""Local read-only viewer. Standard library only; binds to loopback, no AI or collection."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import sqlite3,json,argparse
P=Path(__file__).resolve().parent
HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>팀 커뮤니티 DB</title><style>body{font:16px -apple-system,sans-serif;background:#f2f4f6;color:#191f28;padding:30px;max-width:1300px;margin:auto}section{background:white;border-radius:14px;padding:20px;margin:15px 0}input,select,button{padding:10px;font:inherit;margin:4px;border-radius:8px;border:1px solid #d1d6db}button{background:#3182f6;color:white}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #e5e8eb}p{line-height:1.6}.text{white-space:pre-wrap;max-width:750px}</style><h1>팀 커뮤니티 공유 DB</h1><p>이미 확보한 4종목 자료 · 출처와 미분류를 구분합니다.<br>추가 수집·AI 호출 없음. 원래 ID·정확한 작성 시각·작성자 정보는 포함하지 않습니다.</p><section id="summary"></section><section><select id="stock"><option value="">전체 종목</option><option value="003670">포스코퓨처엠</option><option value="450080">에코프로머티</option><option value="005380">현대차</option><option value="010120">LS ELECTRIC</option></select><select id="status"><option value="">전체 처리 상태</option><option value="classified">분류 완료</option><option value="unclassified">미분류</option></select><select id="sentiment"><option value="">모든 감정</option><option>긍정</option><option>중립</option><option>부정</option><option>혼합</option><option>판단유보</option></select><input id="q" placeholder="공유 본문 검색"><button id="search">검색</button><p id="count"></p><div id="rows"></div><button id="prev">이전</button><button id="next">다음</button></section><script>const el=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let offset=0;async function load(){const p=new URLSearchParams({offset});for(const k of ['stock','status','sentiment','q'])p.set(k,el(k).value);const a=await(await fetch('/api/records?'+p)).json();el('count').textContent=`필터 ${a.total.toLocaleString()}건 / ${offset+1}부터 ${a.rows.length}건`;el('rows').innerHTML=a.rows.map(r=>`<section><b>${esc(r.name)} · ${esc(r.created_date)} · ${esc(r.sentiment||'미분류')}</b><p>${esc(r.source_id)} / ${esc(r.record_type)}</p><div class="text">${r.text_status==='available'?esc(r.text_norm):'[개인정보 위험 표현 검사로 본문 비공개]'}</div></section>`).join('');el('prev').disabled=offset===0;el('next').disabled=offset+50>=a.total}fetch('/api/summary').then(r=>r.json()).then(a=>{el('summary').innerHTML='<table><tr><th>종목</th><th>확보</th><th>AI 분류</th><th>미분류</th><th>기간</th></tr>'+a.map(r=>`<tr><td>${esc(r.name)}</td><td>${r.records.toLocaleString()}</td><td>${r.classified.toLocaleString()}</td><td>${r.unclassified.toLocaleString()}</td><td>${esc(r.first_date)}~${esc(r.last_date)}</td></tr>`).join('')+'</table>'});el('search').onclick=()=>{offset=0;load()};el('prev').onclick=()=>{offset=Math.max(0,offset-50);load()};el('next').onclick=()=>{offset+=50;load()};load();</script></html>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  path=urlparse(self.path);p={k:v[0] for k,v in parse_qs(path.query).items()}
  if path.path=='/':
   b=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  if path.path not in ['/api/summary','/api/records']:self.send_error(404);return
  with sqlite3.connect((P/'shared/community.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as c:
   c.row_factory=sqlite3.Row
   if path.path=='/api/summary':result=[dict(r) for r in c.execute('SELECT * FROM stock_summary ORDER BY stock_id')]
   else:
    where=[];args=[]
    for key,col in [('stock','r.stock_id'),('status','classification_status'),('sentiment','sentiment')]:
     if p.get(key):where.append(col+'=?');args.append(p[key])
    if p.get('q'):where.append('instr(text_norm,?)>0');args.append(p['q'][:200])
    clause=' WHERE '+' AND '.join(where) if where else ''
    try:offset=max(0,min(1000000,int(p.get('offset','0'))))
    except ValueError:self.send_error(400);return
    total=c.execute('SELECT COUNT(*) FROM records r'+clause,args).fetchone()[0]
    records=[dict(r) for r in c.execute('SELECT r.*,s.name FROM records r JOIN stocks s USING(stock_id)'+clause+' ORDER BY created_date DESC,r.source_id,r.record_id LIMIT 50 OFFSET ?',args+[offset])];result={'total':total,'rows':records}
  b=json.dumps(result,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def log_message(self,*args):pass
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);a=ap.parse_args();print(f'Read-only viewer: http://127.0.0.1:{a.port}',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
