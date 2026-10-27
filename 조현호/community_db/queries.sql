-- 1. Source-separated coverage
SELECT * FROM stock_summary;
-- 2. LS ELECTRIC, classified negative expressions; screened bodies only
SELECT created_date,text_norm FROM records
WHERE stock_id='010120' AND classification_status='classified'
AND sentiment='부정' AND text_status='available'
ORDER BY created_date DESC LIMIT 20;
-- 3. Existing pre/during/after analysis; exact per-record times are not shared
SELECT date,session,observed_posts,classified,score FROM session_daily
WHERE stock_id='010120' ORDER BY date,session;
-- 4. Unclassified is not neutral
SELECT stock_id,COUNT(*) FROM records WHERE classification_status='unclassified' GROUP BY stock_id;
-- 5. Daily sentiment with denominator and missingness
SELECT * FROM daily_sentiment WHERE stock_id='003670' ORDER BY trading_date;
