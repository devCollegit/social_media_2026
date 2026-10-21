import pandas as pd
import pytest
from analysis.llm_study import build_panel


def test_panel_retains_activity_control_and_calendar_when_replacing_sentiment():
    b=pd.DataFrame(dict(stock_id=['001','001'],trading_date=['2026-10-19','2026-10-20'],
        post_count=[10,20],log_post_count=[2.3,3.0],sentiment_index=[.1,.2],
        positive_count=[4,8],neutral_count=[3,8],negative_count=[3,4],is_sparse=[False,False]))
    d=pd.DataFrame(dict(stock_id=['001','001'],trading_date=b.trading_date,
        total_posts=[10,20],unclassified_count=[0,0],eligible_count=[5,2],positive_count=[4,1],neutral_count=[0,0],negative_count=[1,1],
        sentiment_index=[.6,None],is_sparse=[False,True]))
    p=build_panel(b,d)
    assert p.log_post_count.tolist()==b.log_post_count.tolist()
    assert p.total_post_count.tolist()==[10,20]
    assert p.post_count.tolist()==[5,2]
    assert p.sentiment_prev.iloc[1]==.6
    with pytest.raises(ValueError,match='미분류'):
        build_panel(b,d.assign(unclassified_count=[0,1]))
    with pytest.raises(ValueError,match='집합'):
        build_panel(b,d.iloc[:1])

    with pytest.raises(ValueError,match='전체 글 수'):
        build_panel(b,d.assign(total_posts=[9,20]))
