import numpy as np
import pandas as pd
import pytest
from analysis.market_observatory import profile


def frames():
    n=12
    daily=pd.DataFrame({'stock_id':['001']*n,'trading_date':pd.date_range('2026-01-01',periods=n).strftime('%Y-%m-%d'),
        'total_posts':[10]*11+[100], 'unclassified_count':[0]*n,
        'eligible_count':[8]*11+[80], 'related_count':[9]*11+[90],
        'positive_count':[3]*11+[30], 'negative_count':[3]*11+[30],
        'neutral_count':[2]*11+[20], 'mixed_count':[1]*11+[10],
        'unrelated_count':[1]*11+[10], 'unclear_count':[0]*n,'abstained_related_count':[0]*n})
    market=daily[['stock_id','trading_date']].assign(close=100.,volume=[100]*11+[1000],ret=0.)
    return daily,market


def test_prior_median_excludes_today_and_future_and_keeps_initial_missing():
    d,m=frames();p=profile(d,m)
    assert p.observed_activity_ratio.iloc[:10].isna().all()
    assert p.observed_activity_ratio.iloc[-1]==10
    assert p.market_volume_ratio.iloc[-1]==10
    changed=d.copy();changed.loc[11,'total_posts']=1000;changed.loc[11,'unrelated_count']=910
    q=profile(changed,m)
    pd.testing.assert_series_equal(p.observed_activity_ratio.iloc[:11],q.observed_activity_ratio.iloc[:11])
    assert p.opposing_message_mix.iloc[-1]==1
    assert p.eligible_share.iloc[-1]==.8


def test_sparse_direction_and_invalid_counts_or_calendar_are_rejected():
    d,m=frames();d.loc[0,['positive_count','negative_count','neutral_count','eligible_count','unrelated_count']]=[1,0,0,1,8]
    d.loc[0,'related_count']=2
    p=profile(d,m)
    assert np.isnan(p.negative_share.iloc[0])
    assert np.isnan(p.opposing_message_mix.iloc[0])
    with pytest.raises(ValueError,match='전체'):
        profile(d.assign(total_posts=999),m)
    with pytest.raises(ValueError,match='날짜'):
        profile(d,m.iloc[:1])
