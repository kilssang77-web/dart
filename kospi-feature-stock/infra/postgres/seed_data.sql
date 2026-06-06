-- 시장 지수 의사 종목 (KOSPI 상대수익률 피처 계산용)
INSERT INTO stocks (code, name, market, sector, industry, is_active)
VALUES
('0001', 'KOSPI지수',   'INDEX', '지수', 'KOSPI',  TRUE),
('1001', 'KOSDAQ지수',  'INDEX', '지수', 'KOSDAQ', TRUE)
ON CONFLICT (code) DO NOTHING;

-- 샘플 종목 데이터
INSERT INTO stocks (code, name, market, sector, industry, is_active)
VALUES
('005930', '삼성전자',       'KOSPI',  '전기·전자', '반도체',        TRUE),
('000660', 'SK하이닉스',     'KOSPI',  '전기·전자', '반도체',        TRUE),
('035420', 'NAVER',          'KOSPI',  'IT서비스',  '포털·인터넷',   TRUE),
('068270', '셀트리온',       'KOSDAQ', '의약품',    '바이오',        TRUE),
('051910', 'LG화학',         'KOSPI',  '화학',      '정밀화학',      TRUE),
('035720', '카카오',         'KOSDAQ', 'IT서비스',  '플랫폼',        TRUE),
('207940', '삼성바이오로직스','KOSPI', '의약품',    '바이오CMO',     TRUE),
('323410', '카카오뱅크',     'KOSDAQ', '금융',      '인터넷은행',    TRUE),
('105560', 'KB금융',         'KOSPI',  '금융',      '종합금융',      TRUE),
('006400', '삼성SDI',        'KOSPI',  '전기·전자', '2차전지',       TRUE)
ON CONFLICT (code) DO UPDATE SET
    name=EXCLUDED.name, market=EXCLUDED.market,
    sector=EXCLUDED.sector, industry=EXCLUDED.industry,
    is_active=EXCLUDED.is_active, updated_at=NOW();

-- 샘플 특징주 이벤트 데이터
INSERT INTO feature_events (detected_at, code, event_type, price, change_rate, volume, volume_ratio, amount, signal_data, signal_score, risk_score)
VALUES
(NOW() - INTERVAL '1 hour',  '005930', 'VOLUME_SURGE',   83800, 0.7, 10500000, 2.8, 879900000000, '{"desc":"거래량 급증"}', 0.82, 0.25),
(NOW() - INTERVAL '2 hours', '000660', 'BREAKOUT_52W',   183200, 0.4, 2100000, 1.9, 384720000000, '{"desc":"52주 신고가 돌파"}', 0.88, 0.20),
(NOW() - INTERVAL '3 hours', '068270', 'VOLUME_SURGE',   165000, 3.2, 5600000, 4.2, 924000000000, '{"desc":"거래량 폭발 + 기관 매수"}', 0.91, 0.18),
(NOW() - INTERVAL '4 hours', '035420', 'LONG_WHITE_CANDLE', 215000, 2.1, 1200000, 2.1, 258000000000, '{"desc":"장대양봉"}', 0.75, 0.22),
(NOW() - INTERVAL '5 hours', '051910', 'BREAKOUT_26W',   420000, 1.8, 890000, 1.7, 373800000000, '{"desc":"26주 신고가"}', 0.72, 0.28),
(NOW() - INTERVAL '6 hours', '207940', 'HAMMER_CANDLE',  780000, -0.5, 320000, 1.4, 249600000000, '{"desc":"망치형 캔들"}', 0.68, 0.30),
(NOW() - INTERVAL '7 hours', '323410', 'VOLUME_SURGE',   21500, 2.4, 8900000, 3.1, 191350000000, '{"desc":"거래량 급증"}', 0.77, 0.24),
(NOW() - INTERVAL '8 hours', '105560', 'POST_DISCLOSURE_SURGE', 82500, 1.5, 2100000, 1.8, 173250000000, '{"desc":"공시 후 급등"}', 0.73, 0.26),
(NOW() - INTERVAL '12 hours','006400', 'BREAKOUT_20D',   395000, 1.2, 680000, 1.5, 268600000000, '{"desc":"20일 신고가"}', 0.70, 0.28),
(NOW() - INTERVAL '20 hours','035720', 'SUPPLY_ANOMALY', 52000, -0.8, 3400000, 1.6, 176800000000, '{"desc":"수급 이상"}', 0.65, 0.35)
ON CONFLICT DO NOTHING;

-- 샘플 매매 추천 데이터 (실제 수집 전 UI 확인용)
-- 가격은 시스템 가동 후 recommender가 실시간으로 덮어씀
INSERT INTO recommendations (code, created_at, action, entry_price, entry_price_low, entry_price_high, target_price, stop_loss_price, expected_hold_days, success_prob, expected_return, risk_score, risk_reward_ratio, rationale, similar_cases, expired_at)
VALUES
('005930', NOW() - INTERVAL '2 hours',  'BUY',  350000, 347000, 353000, 371000, 332000, 5, 0.82, 6.1, 0.25, 2.44, '{"reason":"거래량 급증 + 외국인 매수","signals":["VOLUME_SURGE"]}',        '[]', NOW() + INTERVAL '5 days'),
('000660', NOW() - INTERVAL '3 hours',  'BUY', 2300000,2280000,2320000,2490000,2185000, 7, 0.78, 8.3, 0.30, 2.77, '{"reason":"52주 신고가 돌파","signals":["BREAKOUT_52W"]}',                  '[]', NOW() + INTERVAL '7 days'),
('035420', NOW() - INTERVAL '1 hour',   'BUY',  215000, 213000, 217000, 228000, 207000, 5, 0.75, 6.0, 0.20, 3.00, '{"reason":"장대양봉 + 거래량 확인","signals":["LONG_WHITE_CANDLE"]}',      '[]', NOW() + INTERVAL '5 days'),
('068270', NOW() - INTERVAL '30 minutes','BUY', 165000, 163000, 167000, 180000, 157000, 5, 0.88, 9.1, 0.18, 5.06, '{"reason":"거래량 폭발 + 기관 매수","signals":["VOLUME_SURGE"]}',          '[]', NOW() + INTERVAL '5 days'),
('051910', NOW() - INTERVAL '4 hours',  'WAIT', 420000, 418000, 423000, 440000, 405000,10, 0.65, 4.8, 0.35, 1.37, '{"reason":"26주 신고가 돌파 관망","signals":["BREAKOUT_26W"]}',            '[]', NOW() + INTERVAL '10 days'),
('035720', NOW() - INTERVAL '2 hours',  'WAIT',  52000,  51500,  52500,  55000,  49000, 7, 0.62, 5.8, 0.40, 1.45, '{"reason":"수급 이상 - 추가 확인 필요","signals":["SUPPLY_ANOMALY"]}',     '[]', NOW() + INTERVAL '7 days'),
('207940', NOW() - INTERVAL '5 hours',  'WAIT', 780000, 775000, 785000, 820000, 750000,10, 0.61, 5.1, 0.28, 1.82, '{"reason":"망치형 캔들 - 저가 매수 관찰","signals":["HAMMER_CANDLE"]}',    '[]', NOW() + INTERVAL '10 days'),
('323410', NOW() - INTERVAL '1 hour',   'BUY',   21500,  21300,  21700,  23000,  20500, 5, 0.77, 7.0, 0.22, 3.18, '{"reason":"거래량 급증 + 상승 모멘텀","signals":["VOLUME_SURGE"]}',        '[]', NOW() + INTERVAL '5 days'),
('105560', NOW() - INTERVAL '3 hours',  'BUY',   82500,  82000,  83000,  88000,  79000, 7, 0.73, 6.7, 0.26, 2.58, '{"reason":"공시 후 급등 패턴","signals":["POST_DISCLOSURE_SURGE"]}',       '[]', NOW() + INTERVAL '7 days'),
('006400', NOW() - INTERVAL '6 hours',  'WAIT', 395000, 393000, 397000, 415000, 380000,10, 0.60, 5.1, 0.32, 1.59, '{"reason":"20일 신고가 돌파 - 추세 확인 중","signals":["BREAKOUT_20D"]}', '[]', NOW() + INTERVAL '10 days');

-- 샘플 공시 데이터
INSERT INTO disclosures (rcept_no, code, corp_name, disclosed_at, report_type, disclosure_type, title, category, sentiment_score, raw_json)
VALUES
('20260601000001', '005930', '삼성전자', NOW() - INTERVAL '5 hours', '수시공시', '주요사항보고', '반도체 설비투자 3조원 확대 결정', 'favorable', 0.85, '{"title":"반도체 설비투자 3조원 확대 결정"}'),
('20260601000002', '000660', 'SK하이닉스', NOW() - INTERVAL '4 hours', '수시공시', '주요사항보고', 'HBM4 양산 개시 공시', 'favorable', 0.90, '{"title":"HBM4 양산 개시 공시"}'),
('20260601000003', '035420', 'NAVER', NOW() - INTERVAL '3 hours', '수시공시', '주요사항보고', 'AI 검색 서비스 유료화 계획 발표', 'neutral', 0.70, '{"title":"AI 검색 서비스 유료화 계획 발표"}'),
('20260601000004', '068270', '셀트리온', NOW() - INTERVAL '2 hours', '수시공시', '주요사항보고', '바이오시밀러 미국 FDA 승인 획득', 'favorable', 0.92, '{"title":"바이오시밀러 미국 FDA 승인 획득"}'),
('20260601000005', '207940', '삼성바이오로직스', NOW() - INTERVAL '1 hour', '수시공시', '주요사항보고', '글로벌 제약사와 CMO 계약 체결 (계약액 1.2조원)', 'favorable', 0.88, '{"title":"글로벌 제약사와 CMO 계약 체결"}');

-- 일봉 데이터는 collector가 KIS API로 자동 수집하므로 seed 불필요

SELECT 'Data seeded successfully' AS result;
