"""전체 LLM 집계와 기존 시세 패널을 연결하는 탐색 진단. 기존 결과를 덮어쓰지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from analysis.robustness import adjust, lag_pair
from analysis.temporal import forecast

KEYS = ['stock_id', 'trading_date']


def build_panel(baseline, daily):
    for frame in [baseline, daily]:
        if frame.duplicated(KEYS).any():
            raise ValueError('중복 거래일')
    if set(map(tuple, baseline[KEYS].to_numpy())) != set(map(tuple, daily[KEYS].to_numpy())):
        raise ValueError('거래일 집합 불일치')
    if daily.unclassified_count.sum() != 0:
        raise ValueError('미분류 자료가 남아 있음: 전체 분류 후 연구 연결 가능')
    extra = daily.rename(columns={c:'llm_'+c for c in daily.columns if c not in KEYS})
    result = baseline.merge(extra, on=KEYS, validate='one_to_one')
    # 분류 대상은 바꾸되 활동량 통제 변수는 기존 전체 글 수로 유지한다.
    if 'llm_total_posts' in result and not result.post_count.eq(result.llm_total_posts).all():
        raise ValueError('같은 거래일의 전체 글 수가 기존 패널과 다름')
    result['lexicon_sentiment_index'] = result.sentiment_index
    for col in ['positive_count','neutral_count','negative_count','sentiment_index','is_sparse']:
        result[col] = result['llm_'+col]
    result['total_post_count'] = result.post_count
    result['post_count'] = result.llm_eligible_count
    result = result.sort_values(KEYS).reset_index(drop=True)
    result['sentiment_prev'] = result.groupby('stock_id').sentiment_index.shift(1)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline-panel', type=Path, required=True)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--daily-summary', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/'state'):
        raise ValueError('출력은 state 아래')
    info=json.loads(args.daily_summary.read_text())
    if info['partial_input']:
        raise ValueError('부분 표본 집계로 전체 연구를 실행하지 않습니다')
    baseline=pd.read_csv(args.baseline_panel,dtype={'stock_id':str})
    daily=pd.read_csv(args.daily,dtype={'stock_id':str})
    panel=build_panel(baseline,daily)
    descriptive=[]; tests=[]; predictions=[]; metrics=[]
    for stock,g in panel.groupby('stock_id'):
        descriptive.append(dict(stock_id=stock,days=len(g),eligible=int(g.post_count.sum()),
            all_posts=int(g.llm_total_posts.sum()),valid_days=int(g.sentiment_index.notna().sum()),
            mean_eligible_share=float(g.llm_eligible_share_of_all.mean()),
            index_correlation_with_lexicon=float(g[['sentiment_index','lexicon_sentiment_index']].corr().iloc[0,1])))
        original=baseline[baseline.stock_id==stock].sort_values('trading_date').copy()
        for name,data in [('llm',g),('lexicon',original)]:
            for minimum in [1,5,10]:
                for lag in range(-5,6):
                    pair=lag_pair(data,minimum,lag)
                    r,p=pearsonr(pair.s,pair.r) if len(pair)>=10 and pair.s.nunique()>1 and pair.r.nunique()>1 else (np.nan,np.nan)
                    tests.append(dict(method=name,stock_id=stock,minimum=minimum,lag=lag,n=len(pair),r=r,p=p))
            pred=forecast(data,min_train=40)
            if pred.empty:
                metrics.append(dict(stock_id=stock,method=name,n_forecasts=0,status='insufficient eligible training days'))
                continue
            pred.insert(0,'stock_id',stock);pred.insert(1,'method',name);predictions.append(pred)
            mse={k:float(np.mean((pred[k]-pred.actual)**2)) for k in ['controls','with_sentiment','historical_mean']}
            metrics.append(dict(stock_id=stock,method=name,n_forecasts=len(pred),
                relative_mse_vs_controls=mse['with_sentiment']/mse['controls'] if mse['controls'] else None,
                **{'mse_'+k:v for k,v in mse.items()}))
    correlations=adjust(pd.DataFrame(tests))
    # 모든 방식·최소 글 수·종목·시차를 하나의 탐색 검정군으로 보정한다.
    summary=dict(descriptive=descriptive,forecast_metrics=metrics,exploratory_tests=len(correlations),
        significant_bh=int((correlations.q_bh<.05).sum()),
        limitations=['같은 2종목·기간의 사후 탐색, 독립 홀드아웃 검증 아님',
            'Pearson p값은 시간 의존성을 보정하지 않음',
            'LLM 판정 정확도 미확인, 유보에 따른 선택 편향 가능',
            '예측 비교의 학습 표본·평가 날짜는 방식별로 다를 수 있어 방식 간 MSE 직접 비교 금지',
            '방식별 sentiment 추가 vs controls 비교는 해당 방식의 동일 학습·평가 표본 사용'],
        inputs=[dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [args.baseline_panel,args.daily,args.daily_summary]])
    args.output.mkdir(parents=True,exist_ok=False)
    panel.to_csv(args.output/'panel.csv',index=False,encoding='utf-8-sig')
    correlations.to_csv(args.output/'lag_sensitivity.csv',index=False)
    if predictions:
        pd.concat(predictions).to_csv(args.output/'forecasts.csv',index=False)
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='inputs'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
