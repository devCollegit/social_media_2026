"""LLM 판정으로 거래일별 감성과 분류 범위를 집계한다. 예측 검증은 수행하지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ['stock_id', 'post_id']
LABELS = ['긍정', '중립', '부정']


def aggregate(clean, predictions, market, min_posts=5, allow_partial=False):
    if min_posts < 1:
        raise ValueError('min_posts는 1 이상')
    for frame in [clean, predictions]:
        if frame.duplicated(KEYS).any() or frame[KEYS].isna().any().any() or (frame[KEYS] == '').any().any():
            raise ValueError('중복 또는 빈 ID')
    clean_ids = set(map(tuple, clean[KEYS].to_numpy()))
    pred_ids = set(map(tuple, predictions[KEYS].to_numpy()))
    if not pred_ids <= clean_ids or (not allow_partial and pred_ids != clean_ids):
        raise ValueError('분류 ID 범위 불일치: 일부 표본은 allow_partial 필요')
    if market.duplicated(['stock_id', 'trading_date']).any():
        raise ValueError('중복 시세 거래일')
    joined = clean[KEYS + ['created_at']].merge(
        predictions[KEYS + ['relevance', 'sentiment']], on=KEYS, how='left', validate='one_to_one')
    # clean CSV는 한국 현지 naive 시각, 원자료는 offset-aware 시각일 수 있다.
    def local_timestamp(value):
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise ValueError('빈 작성 시각')
        return stamp if stamp.tzinfo is None else stamp.tz_convert('Asia/Seoul').tz_localize(None)
    joined['created_at'] = pd.to_datetime(joined.created_at.map(local_timestamp))
    if joined.created_at.isna().any():
        raise ValueError('빈 작성 시각')
    rows, unassigned = [], 0
    for code, group in joined.groupby('stock_id'):
        calendar = pd.to_datetime(market.loc[market.stock_id == code, 'trading_date']).sort_values()
        if calendar.empty:
            raise ValueError('종목의 거래일 달력 없음')
        dates = calendar.dt.normalize().to_numpy()
        closes = dates + np.timedelta64(15 * 60 + 30, 'm')
        index = np.searchsorted(closes, group.created_at.to_numpy(), side='left')
        valid = index < len(dates)
        unassigned += int((~valid).sum())
        group = group.loc[valid].copy()
        group['trading_date'] = dates[index[valid]]
        for day in dates:
            g = group[group.trading_date == day]
            classified = g.relevance.notna()
            related = g.relevance == 'related'
            eligible = related & g.sentiment.isin(LABELS)
            n = int(eligible.sum())
            pos = int((eligible & (g.sentiment == '긍정')).sum())
            neg = int((eligible & (g.sentiment == '부정')).sum())
            rows.append(dict(stock_id=code, trading_date=pd.Timestamp(day).strftime('%Y-%m-%d'),
                total_posts=len(g), classified_count=int(classified.sum()),
                unclassified_count=int((~classified).sum()), related_count=int(related.sum()),
                unrelated_count=int((g.relevance == 'unrelated').sum()),
                unclear_count=int((g.relevance == 'unclear').sum()),
                mixed_count=int((related & (g.sentiment == '혼합')).sum()),
                abstained_related_count=int((related & (g.sentiment == '판단유보')).sum()),
                eligible_count=n, positive_count=pos, negative_count=neg,
                neutral_count=n-pos-neg,
                eligible_share_of_all=n/len(g) if len(g) else None,
                eligible_share_of_related=n/int(related.sum()) if related.any() else None,
                sentiment_index=(pos-neg)/n if n >= min_posts else None,
                is_sparse=n < min_posts))
    return pd.DataFrame(rows), dict(unassigned_after_last_close=unassigned,
        partial_input=pred_ids != clean_ids, classified_rows=len(predictions),
        population_rows=len(clean), min_posts=min_posts,
        note='부분 표본 일별 값은 전체 게시판 분위기나 주가 관계로 해석하지 않음')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clean',type=Path,required=True)
    ap.add_argument('--predictions',type=Path,required=True,help='검증된 JSONL')
    ap.add_argument('--market',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--allow-partial',action='store_true')
    ap.add_argument('--min-posts',type=int,default=5)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/'state'):
        raise ValueError('출력은 state 아래')
    predictions=pd.DataFrame([json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()])
    if not predictions.relevance.isin(['related','unrelated','unclear']).all() or not predictions.sentiment.isin(LABELS+['혼합','판단유보']).all():
        raise ValueError('허용되지 않은 판정')
    if ((predictions.relevance != 'related') & (predictions.sentiment != '판단유보')).any():
        raise ValueError('관련성 불명·무관은 판단유보여야 함')
    daily,summary=aggregate(pd.read_csv(args.clean,dtype=str,keep_default_na=False),predictions,
        pd.read_csv(args.market,dtype=str,keep_default_na=False),args.min_posts,args.allow_partial)
    summary['inputs']=[dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [args.clean,args.predictions,args.market]]
    args.output.mkdir(parents=True,exist_ok=False)
    daily.to_csv(args.output/'daily.csv',index=False,encoding='utf-8-sig')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='inputs'},ensure_ascii=False))


if __name__=='__main__':
    main()
