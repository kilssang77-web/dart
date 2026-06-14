-- 텔레그램 발송 이력
CREATE TABLE IF NOT EXISTS telegram_logs (
    id          BIGSERIAL PRIMARY KEY,
    msg_type    VARCHAR(20)  NOT NULL,
    code        VARCHAR(10),
    name        VARCHAR(100),
    title       TEXT         NOT NULL DEFAULT '',
    message     TEXT         NOT NULL,
    success     BOOLEAN      NOT NULL DEFAULT TRUE,
    error_msg   TEXT,
    sent_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_logs_sent_at  ON telegram_logs (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_telegram_logs_msg_type ON telegram_logs (msg_type);
CREATE INDEX IF NOT EXISTS idx_telegram_logs_code     ON telegram_logs (code) WHERE code IS NOT NULL;
