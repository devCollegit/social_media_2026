"""지정 커밋의 읽기용 수집 모듈을 private/에 준비한다. 외부 코드를 실행하지 않는다."""
import subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
D=R/'private/source/collector';D.mkdir(parents=True,exist_ok=True)
for name in ['fetchers.py','parser.py','http.py','__init__.py']:
 data=subprocess.check_output(['git','show',f'7ae6250:김정기/data_collection/collector/{name}'])
 (D/name).write_bytes(data)
(R/'private/stock_master.csv').write_text('stock_id,isin\n005380,KR7005380001\n010120,KR7010120004\n')
print('수집 모듈과 종목 매핑 준비 완료. 원문 수집은 별도 실행.')
