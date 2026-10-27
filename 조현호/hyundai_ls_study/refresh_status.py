from pathlib import Path
import json,sqlite3,datetime
R=Path(__file__).resolve().parent;D=R/'private/full_20260701_20261020';L=D/'llm'
c=sqlite3.connect(D/'collection.sqlite');state={k:json.loads(v) for k,v in c.execute('SELECT k,v FROM state')}
collection_text=('대상 부모 글과 연결 댓글의 수집 절차가 종료됐다. AI 분류·검증 완료 여부는 아래 집계를 따른다.' if state.get('run_complete') else '수집 중이며 전체 완료나 전수성을 주장하지 않는다.')
if (D/'frozen_snapshot.json').exists():collection_text='사용자 요청으로 확보분을 고정해 추가 수집·AI 분류를 종료했다. 목표 기간 전체 수집 완료를 뜻하지 않는다.'
lines=['# 현대차·LS ELECTRIC 분석 진행 현황','',f'갱신: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")}','', '**목표 기간: 2026-09-01~10-20.** 수집 중이며 전체 완료나 전수성을 주장하지 않는다.','', '|종목|기간 내 확보 글·댓글|확보분 중 가장 이른 시각|목록 페이지|목록 종료일 도달|','|---|---:|---|---:|---|']
lines[4]='**목표 기간: 2026-09-01~10-20.** '+collection_text
for code,name in [('005380','현대차'),('010120','LS ELECTRIC')]:
 n,lo=c.execute("SELECT COUNT(*),MIN(at) FROM posts WHERE code=? AND at>='2026-09-01' AND at<'2026-10-21'",(code,)).fetchone();st=state.get(code+':list',{});lines.append(f'|{name}|{n:,}|{lo or "미확보"}|{st.get("pages",0)}|{st.get("complete",False)}|')
inputs=list((L/'input').glob('batch-*.jsonl'));results=list(L.glob('worker_*/batch-*.jsonl'))
lines+=['','## AI 판정','',f'- 입력 묶음 {len(inputs)}개, 결과 파일 {len(results)}개. 파일 수는 검증 완료 행 수와 다르다.','- gpt-6-luna medium 작업자 3개가 서로 다른 글 묶음을 직접 분류한다. MoA 합의판정이 아니다.','- 정기님 공개 기준을 재구성했으며 비공개 원본 프롬프트를 복제한 실행은 아니다.','- 관련성·감정·판단 이유·실제 인용·부모 맥락을 검사하고, 누락/형식 오류가 있으면 수정 후 통합한다.']
if (L/'validation_summary.json').exists():
 v=json.loads((L/'validation_summary.json').read_text());lines.append(f'- 마지막 통합 검증 통과: {v["validated_predictions"]:,}행. 새 결과 오류가 있으면 이 값은 최신 결과 수와 다르다.')
lines+=['','## 파일과 재개','', '- 수집 커서와 원문: private/full_20260701_20261020/collection.sqlite (폴더명은 최초 실행 식별자이며 현재 실제 범위는 9/1~10/20).','- 미처리 AI 입력과 개별 결과: 같은 폴더의 llm/input, llm/worker_0~2.','- 앞서 만든 40건 AI 예비 판정은 별도 보존하며 이번 전체 분석에 합치지 않는다.','- 원문·AI 개별 판정은 Git 제외, 외부 업로드하지 않았다.','- 시세는 네이버 일봉이며 KRX 수정주가와의 대조는 아직 하지 않았다.','- 수집: python3 조현호/hyundai_ls_study/collect_full.py','- 입력 발행: python3 조현호/hyundai_ls_study/prepare_full_llm.py','- 결과 검증: python3 조현호/hyundai_ls_study/validate_full_llm.py','- 거래일 집계: python3 조현호/hyundai_ls_study/summarize_full.py']
(R/'진행현황.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:12]))
