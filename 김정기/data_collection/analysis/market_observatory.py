"""관측된 커뮤니티 반응을 시장 브리핑용으로 요약한다. 예측·매매 신호는 만들지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ['stock_id', 'trading_date']


def profile(daily, market, window=20, min_history=10, min_messages=5):
    if not 1 <= min_history <= window or min_messages < 1:
        raise ValueError('기간·최소 글 수 설정 오류')
    for frame in [daily, market]:
        if frame.duplicated(KEYS).any() or frame[KEYS].isna().any().any():
            raise ValueError('중복 또는 빈 종목·거래일')
    if set(map(tuple,daily[KEYS].to_numpy())) != set(map(tuple,market[KEYS].to_numpy())):
        raise ValueError('시장 자료와 커뮤니티의 날짜 범위 불일치')
    if daily.unclassified_count.sum():
        raise ValueError('전체 판정이 완료된 집계를 사용하세요')
    counts=['total_posts','eligible_count','related_count','positive_count','negative_count',
        'neutral_count','mixed_count','unrelated_count','unclear_count','abstained_related_count']
    if daily[counts].isna().any().any() or (daily[counts] < 0).any().any():
        raise ValueError('빈 값 또는 음수 집계')
    if not daily.eligible_count.eq(daily.positive_count+daily.negative_count+daily.neutral_count).all():
        raise ValueError('유효 감정 건수 불일치')
    if not daily.total_posts.eq(daily.eligible_count+daily.mixed_count+daily.unrelated_count+
            daily.unclear_count+daily.abstained_related_count).all():
        raise ValueError('전체 판정 건수 불일치')
    if not daily.related_count.eq(daily.eligible_count+daily.mixed_count+daily.abstained_related_count).all():
        raise ValueError('관련 글 건수 불일치')
    result=daily.merge(market[KEYS+['close','volume','ret']],on=KEYS,validate='one_to_one').sort_values(KEYS).reset_index(drop=True)
    for source,name in [('total_posts','observed_activity'),('volume','market_volume')]:
        prior=result.groupby('stock_id')[source].transform(
            lambda x:x.shift(1).rolling(window,min_periods=min_history).median())
        result[name+'_prior_median']=prior
        result[name+'_ratio']=result[source]/prior.replace(0,np.nan)
    eligible=result.eligible_count.where(result.eligible_count>=min_messages)
    directional=(result.positive_count+result.negative_count)
    result['negative_share']=result.negative_count/eligible
    result['direction_balance']=(result.positive_count-result.negative_count)/eligible
    result['opposing_message_mix']=(2*np.minimum(result.positive_count,result.negative_count)/
        directional.where(directional>=min_messages))
    result['eligible_share']=result.eligible_count/result.total_posts.replace(0,np.nan)
    result['llm_abstain_count']=result.unrelated_count+result.unclear_count+result.abstained_related_count
    result['llm_abstain_share']=result.llm_abstain_count/result.total_posts.replace(0,np.nan)
    result['mixed_share']=result.mixed_count/result.total_posts.replace(0,np.nan)
    result['same_day_return']=np.expm1(result.ret)
    result['activity_watch_example']=result.observed_activity_ratio.ge(2).where(result.observed_activity_ratio.notna())
    return result


def fmt(value,percent=False):
    if pd.isna(value):return '자료 부족'
    return f'{value:.1%}' if percent else f'{value:.2f}'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily',type=Path,required=True)
    ap.add_argument('--market',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/'state'):
        raise ValueError('실행 결과는 state 아래 새 폴더')
    result=profile(pd.read_csv(args.daily,dtype={'stock_id':str}),pd.read_csv(args.market,dtype={'stock_id':str}))
    settings=dict(window=20,min_history=10,min_eligible=5,example_activity_ratio=2,
                  selection='rank observed activity ratio only; not market returns')
    sensitivity=[]
    for stock,g in result.groupby('stock_id'):
        for threshold in [1.5,2,3]:
            chosen=g.observed_activity_ratio>=threshold
            sensitivity.append(dict(stock_id=stock,example_threshold=threshold,
                evaluable_days=int(g.observed_activity_ratio.notna().sum()),
                selected_stock_days=int(chosen.sum())))
    cards=[]
    for stock,g in result.groupby('stock_id'):
        selected=g[g.observed_activity_ratio.notna()].nlargest(3,'observed_activity_ratio').copy()
        cards.append(selected)
    cards=pd.concat(cards,ignore_index=True)
    summary=dict(objective='observed forum reaction briefing support',rows=len(result),
        stock_days_with_prior_baseline=int(result.observed_activity_ratio.notna().sum()),
        stocks=result.stock_id.nunique(), assigned_posts=int(result.total_posts.sum()),
        settings=settings,threshold_sensitivity=sensitivity,
        example_cards=cards[['stock_id','trading_date','total_posts','observed_activity_ratio','eligible_count',
                            'negative_share','opposing_message_mix','same_day_return','market_volume_ratio']].replace({np.nan:None}).to_dict('records'),
        limitations=['관측된 표본의 글 수이며 전체 게시판 활동·고유 투자자 관심도 아님',
            '양음 혼재는 게시물 구성의 균형이며 투자자 간 의견 불일치나 위험 확률 아님',
            'AI 유보율은 모델 처리 범위이며 시장 불확실성 아님',
            '동일날 시세는 맥락 참고이며 예측·인과·투자 수익성 검증 없음',
            '2배 기준은 설명용 설계값이며 유효성이 검증된 경보 아님',
            '수집 완전성·날짜별 수집 정책의 일관성 확인 전 배수는 표본 내 기술통계로만 사용'],
        inputs=[dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [args.daily,args.market]])
    args.output.mkdir(parents=True,exist_ok=False)
    result.to_csv(args.output/'daily_profile.csv',index=False,encoding='utf-8-sig')
    cards.to_csv(args.output/'example_cards.csv',index=False,encoding='utf-8-sig')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    text='# 커뮤니티 반응 관측 브리핑 예시\n\n과거 수집 표본의 요약이며 실시간 서비스·검증된 투자 신호가 아니다.\n'
    for r in cards.itertuples():
        text+=f'\n## {r.stock_id} · {r.trading_date}\n\n'
        text+=f'- 관측 글 {r.total_posts}건: 직전 20거래일 중앙값 대비 {fmt(r.observed_activity_ratio)}배\n'
        text+=f'- 감정 분류 가능 {r.eligible_count}건({fmt(r.eligible_share,True)}); 부정 비중 {fmt(r.negative_share,True)}\n'
        text+=f'- 긍정 {r.positive_count}건 / 부정 {r.negative_count}건; 양음 혼재도 {fmt(r.opposing_message_mix)}\n'
        text+=f'- AI 판단유보 {fmt(r.llm_abstain_share,True)}; 혼합 감정 {fmt(r.mixed_share,True)}\n'
        text+=f'- 같은 날 수익률 {fmt(r.same_day_return,True)}, 시장 거래량은 직전 기준 대비 {fmt(r.market_volume_ratio)}배\n'
        text+='- 활용: 이 날짜의 뉴스·공시를 먼저 확인할 후보로 제시. 원인과 투자 효용은 미검증.\n'
    (args.output/'브리핑예시.md').write_text(text)
    plot(result,args.output/'observatory.svg')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def plot(frame,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    stocks=sorted(frame.stock_id.unique());fig,axes=plt.subplots(4,len(stocks),figsize=(12,11),sharex='col',squeeze=False)
    for col,stock in enumerate(stocks):
        g=frame[frame.stock_id==stock];dates=pd.to_datetime(g.trading_date)
        axes[0,col].plot(dates,g.observed_activity_ratio,label='Observed messages',color='#13766e')
        axes[0,col].plot(dates,g.market_volume_ratio,label='Market volume',color='#9b9ea5',alpha=.8)
        axes[0,col].axhline(1,color='#cccccc',lw=.7);axes[0,col].set_ylabel('Ratio to prior 20-day median')
        axes[0,col].set_title('Stock '+stock);axes[0,col].legend(fontsize=8)
        axes[1,col].plot(dates,g.direction_balance,color='#13766e');axes[1,col].axhline(0,color='#cccccc',lw=.7)
        axes[1,col].set_ylim(-1.05,1.05);axes[1,col].set_ylabel('LLM message balance')
        axes[2,col].plot(dates,g.opposing_message_mix,color='#8a649c');axes[2,col].set_ylim(0,1.05)
        axes[2,col].set_ylabel('Positive/negative message mix')
        axes[3,col].plot(dates,g.eligible_share,label='Eligible',color='#2b77a0')
        axes[3,col].plot(dates,g.llm_abstain_share,label='LLM abstained',color='#c38c51')
        axes[3,col].set_ylim(0,1.05);axes[3,col].set_ylabel('Share of observed messages');axes[3,col].legend(fontsize=8)
        for ax in axes[:,col]:ax.grid(alpha=.15);ax.tick_params(axis='x',labelrotation=30)
    fig.suptitle('Forum reaction observatory — historical briefing support, not a trading signal')
    fig.tight_layout(rect=(0,.02,1,.97));fig.savefig(path);fig.savefig(path.with_suffix('.png'),dpi=130);plt.close(fig)


if __name__=='__main__':
    main()
