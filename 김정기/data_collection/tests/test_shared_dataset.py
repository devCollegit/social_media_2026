import pandas as pd
from integration.export_shared_dataset import prepare,screen


def test_public_release_keeps_labels_but_withholds_risky_text_and_replaces_ids():
    source=pd.DataFrame({'stock_id':['001']*3,'post_id':['987654321','987654322','987654323'],
        'text_norm':['좋은 실적입니다','평단 10만원, 100주 보유','조용하네요'],
        'parent_text':['','좋은 실적입니다','평단 10만원, 100주 보유'],
        'context_status':['top_level','parent_available','parent_available']})
    clean=source[['stock_id','post_id']].assign(parent_id=['','987654321.0','987654322'],
        created_at=['2026-10-19 15:30:00','2026-10-19 15:31:00','2026-10-20 16:00:00'])
    predictions=source[['stock_id','post_id']].assign(relevance='related',sentiment=['긍정','부정','중립'],
        reason='test',evidence=['실적','평단','조용'],context_used=False)
    calendar=pd.DataFrame({'stock_id':['001']*2,'trading_date':['2026-10-19','2026-10-20']})
    public,private,stats=prepare(source,clean,predictions,calendar)
    assert len(public)==3 and set(public.sentiment)=={'긍정','부정','중립'}
    assert not {'post_id','parent_id','created_at','reason','evidence'}.intersection(public.columns)
    j=private.merge(public,on=['record_id','stock_id']).set_index('post_id')
    assert j.loc['987654322','text_norm']==''
    assert j.loc['987654323','parent_text']==''
    assert j.loc['987654322','parent_record_id']==j.loc['987654321','record_id']
    assert j.loc['987654321','trading_date']=='2026-10-19'
    assert j.loc['987654322','trading_date']=='2026-10-20'
    assert j.loc['987654323','trading_date']==''
    assert stats['text_withheld_privacy_screen']==1


def test_screen_contacts_personal_details_and_csv_formula_escape():
    from integration.export_shared_dataset import excel_safe
    for text in ['010-1234-5678','name@example.org','테스트님','서울로 20','제 아버지','보유 100주']:
        assert screen(text)
    assert not screen('기업 실적 발표 일정')
    assert excel_safe('  =2+2')==("'  =2+2",True)
