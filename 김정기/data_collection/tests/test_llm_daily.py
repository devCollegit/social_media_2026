import pandas as pd
import pytest
from analysis.llm_daily import aggregate


def test_close_boundary_weekend_unknown_and_sparse_are_preserved():
    clean=pd.DataFrame({'stock_id':['001']*5,'post_id':list('12345'),
      'created_at':['2026-10-16T15:30:00+09:00','2026-10-16T15:30:01+09:00',
      '2026-10-18T12:00:00+09:00','2026-10-19T15:30:01+09:00','2026-10-19T10:00:00+09:00']})
    pred=clean[['stock_id','post_id']].iloc[:4].assign(
      relevance=['related','related','unclear','related'],sentiment=['긍정','부정','판단유보','중립'])
    market=pd.DataFrame({'stock_id':['001']*2,'trading_date':['2026-10-16','2026-10-19']})
    with pytest.raises(ValueError,match='allow_partial'):
        aggregate(clean,pred,market)
    daily,meta=aggregate(clean,pred,market,min_posts=1,allow_partial=True)
    assert daily.total_posts.tolist()==[1,3]
    assert daily.sentiment_index.tolist()==[1,-1]
    assert daily.unclassified_count.tolist()==[0,1]
    assert daily.unclear_count.tolist()==[0,1]
    assert meta['unassigned_after_last_close']==1
    assert daily.eligible_share_of_all.tolist()==[1,1/3]
    sparse,_=aggregate(clean,pred,market,min_posts=2,allow_partial=True)
    assert sparse.sentiment_index.isna().all()


def test_naive_clean_timestamp_is_already_korean_time_not_utc():
    clean=pd.DataFrame({'stock_id':['001']*2,'post_id':['1','2'],
        'created_at':['2026-10-19 10:00:00','2026-10-19 15:30:00']})
    pred=clean[['stock_id','post_id']].assign(relevance='related',sentiment='긍정')
    market=pd.DataFrame({'stock_id':['001']*2,'trading_date':['2026-10-19','2026-10-20']})
    daily,meta=aggregate(clean,pred,market,min_posts=1)
    assert daily.total_posts.tolist()==[2,0]
    aware=clean.assign(created_at=['2026-10-19T01:00:00Z','2026-10-19T15:30:00+09:00'])
    aware_daily,_=aggregate(aware,pred,market,min_posts=1)
    pd.testing.assert_frame_equal(daily,aware_daily)
    assert meta['unassigned_after_last_close']==0
