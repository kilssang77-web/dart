-- KIND 폴러가 생성하는 kind_{corp}_{time}_{title[:30]} 형식 uid가 VARCHAR(20)을 초과하는 버그 수정
-- rcept_no: VARCHAR(20) → VARCHAR(200)
ALTER TABLE disclosures ALTER COLUMN rcept_no TYPE VARCHAR(200);
