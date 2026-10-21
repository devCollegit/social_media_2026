"""공개 Git용 행별 AI 분석 자료를 만든다. 위험 표현을 포함한 원문은 공개하지 않는다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import uuid

import numpy as np
import pandas as pd

from analysis.llm_results import _read_predictions, _check_predictions
from integration.prepare_context_review import parent_key

ROOT=Path(__file__).resolve().parents[1]
KEYS=['stock_id','post_id']
PATTERNS={
    'contact':r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:01[016789]|0\d{1,2})[- .]?\d{3,4}[- .]?\d{4}(?!\d)',
    'link_or_mention':r'https?://\S+|www\.\S+|#\[[^\]]*\]\([^)]*\)|@[A-Za-z0-9_]{2,}',
    'address':r'[가-힣]+(?:로|길)\s*\d+|\d+동\s*\d+호',
    'person_reference':r'(?<![가-힣])[가-힣A-Za-z0-9_]{2,15}(?:님|씨|형님|언니|누나|오빠|아저씨)(?![가-힣])',
    'financial_detail':r'평단|보유|물렸|손실|수익률|계좌|매수가|매입가|손익|평가손|[0-9,]+\s*(?:주|만원|억)',
    'private_life':r'(?:우리|저희|제)\s*(?:엄마|아빠|아버지|어머니|가족|아내|남편|여친|남친|딸|아들)|제\s*이름|주민등록|생년월일|계좌번호|입원|수술|암진단|암\s*진단',
}
COMPILED={k:re.compile(v,re.I) for k,v in PATTERNS.items()}


def screen(text):
    return sorted(k for k,pattern in COMPILED.items() if pattern.search(str(text)))


def excel_safe(text):
    text=str(text)
    escaped=text.lstrip().startswith(('=','+','-','@'))
    return ("'"+text if escaped else text),escaped


def prepare(source,clean,predictions,calendar):
    _check_predictions(source,predictions)
    if clean.duplicated(KEYS).any():raise ValueError('중복 clean ID')
    if set(map(tuple,source[KEYS].to_numpy())) != set(map(tuple,clean[KEYS].to_numpy())):
        raise ValueError('source와 clean ID 집합 불일치')
    if calendar.duplicated(['stock_id','trading_date']).any():raise ValueError('중복 거래일')
    frame=clean[KEYS+['parent_id','created_at']].merge(source[KEYS+['text_norm','parent_text','context_status']],on=KEYS,validate='one_to_one')
    frame=frame.merge(predictions[KEYS+['relevance','sentiment','context_used']],on=KEYS,validate='one_to_one')
    mapping={tuple(k):uuid.uuid4().hex for k in frame[KEYS].to_numpy()}
    dates={}
    for code,g in calendar.groupby('stock_id'):
        days=pd.to_datetime(g.trading_date).sort_values().dt.normalize().to_numpy()
        dates[code]=(days,days+np.timedelta64(15*60+30,'m'))
    output=[];stats=Counter();private=[]
    for r in frame.itertuples():
        key=(r.stock_id,r.post_id);rid=mapping[key]
        stamp=pd.Timestamp(r.created_at)
        if pd.isna(stamp):raise ValueError('빈 작성 시각')
        if stamp.tzinfo is not None:stamp=stamp.tz_convert('Asia/Seoul').tz_localize(None)
        days,closes=dates[r.stock_id];index=int(np.searchsorted(closes,stamp.to_datetime64(),side='left'))
        trade=str(pd.Timestamp(days[index]).date()) if index<len(days) else ''
        flags=screen(r.text_norm);parent_flags=screen(r.parent_text)
        # 고위험 부분만 잘라내면 남은 문장에서도 신원을 유추할 수 있어 해당 본문 전체를 보류한다.
        text,text_escaped=excel_safe(r.text_norm) if not flags else ('',False)
        parent,parent_escaped=excel_safe(r.parent_text) if not parent_flags else ('',False)
        status='withheld_privacy_screen' if flags else 'available'
        parent_status='withheld_privacy_screen' if parent_flags else 'available' if r.parent_text else r.context_status
        stats['text_'+status]+=1
        stats.update('flag_'+flag for flag in flags)
        stats['parent_withheld']+=bool(parent_flags)
        output.append(dict(record_id=rid,stock_id=r.stock_id,created_date=str(stamp.date()),trading_date=trade,
            parent_record_id=mapping.get((r.stock_id,parent_key(r.parent_id)),''),
            text_norm=text,text_status=status,text_excel_escaped=text_escaped,
            parent_text=parent,parent_text_status=parent_status,parent_excel_escaped=parent_escaped,
            relevance=r.relevance,sentiment=r.sentiment,model_context_used=r.context_used,model_name='gpt-6-luna'))
        private.append(dict(record_id=rid,stock_id=r.stock_id,post_id=r.post_id,
            text_flags='|'.join(flags),parent_flags='|'.join(parent_flags)))
    result=pd.DataFrame(output).sort_values('record_id').reset_index(drop=True)
    assert result.record_id.is_unique
    for col in ['text_norm','parent_text']:
        if result[col].map(screen).map(bool).any():raise ValueError('공개 텍스트 재검사 실패')
    return result,pd.DataFrame(private),dict(stats)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--clean',type=Path,required=True)
    ap.add_argument('--predictions',type=Path,required=True)
    ap.add_argument('--market',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--private-output',type=Path,required=True)
    args=ap.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'shared'):
        raise ValueError('공개 출력은 shared 아래 새 폴더')
    if not args.private_output.resolve().is_relative_to(ROOT/'state'):
        raise ValueError('원래 ID 매핑은 state 아래')
    if args.output.exists() or args.private_output.exists():raise ValueError('기존 출력 덮어쓰기 금지')
    source=pd.read_csv(args.source,dtype=str,keep_default_na=False)
    if len(source)!=7632:raise ValueError('기대 행 수 7632 불일치')
    public,private,stats=prepare(source,pd.read_csv(args.clean,dtype=str,keep_default_na=False),
        _read_predictions(args.predictions),pd.read_csv(args.market,dtype=str,keep_default_na=False))
    args.private_output.mkdir(parents=True);private.to_csv(args.private_output/'private_mapping.csv',index=False,encoding='utf-8-sig')
    args.output.mkdir(parents=True)
    public.to_csv(args.output/'records.csv',index=False,encoding='utf-8-sig')
    manifest=dict(rows=len(public),stats=stats,model='gpt-6-luna',format_version='public_screened_v1',
        predictions_unchanged=True,original_post_ids_replaced=True,exact_times_removed=True,
        freeform_ai_reason_and_evidence_omitted=True,privacy_method='rule_screen_whole_text_withholding; not a guarantee of complete anonymization',
        ai_labels_refer_to='original private text and parent context before sharing screen',
        sentiment_counts=public.sentiment.value_counts().to_dict(),relevance_counts=public.relevance.value_counts().to_dict(),
        records_sha256=sha(args.output/'records.csv'),
        input_sha256={name:sha(getattr(args,name)) for name in ['source','clean','predictions','market']})
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='input_sha256'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
