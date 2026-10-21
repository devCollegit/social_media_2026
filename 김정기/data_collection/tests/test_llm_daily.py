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
