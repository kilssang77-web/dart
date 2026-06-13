import json
import os
import httpx
import logging

logger = logging.getLogger("notifier.telegram")

TELEGRAM_API = "https://api.telegram.org"


class TelegramSender:

    def __init__(self, db_pool=None):
        token   = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment"
            )
        self._token   = token
        self._chat_id = chat_id
        self._enabled = os.environ.get("TELEGRAM_ENABLED", "1") == "1"
        self._client  = httpx.AsyncClient(timeout=15)
        self._db      = db_pool

    async def send_message(
        self,
        text: str,
        *,
        msg_type: str = "unknown",
        code: str = "",
        name: str = "",
        title: str = "",
    ) -> bool:
        ok, err = True, None
        if not self._enabled:
            logger.debug(f"[DISABLED] {text[:60]}")
        else:
            url     = f"{TELEGRAM_API}/bot{self._token}/sendMessage"
            payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
            try:
                resp = await self._client.post(
                    url,
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                ok, err = False, str(e)

        if self._db:
            await self._log(msg_type, code or None, name or None, title, text, ok, err)
        return ok

    async def _log(
        self,
        msg_type: str,
        code,
        name,
        title: str,
        message: str,
        success: bool,
        error_msg,
    ) -> None:
        try:
            async with self._db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO telegram_logs
                        (msg_type, code, name, title, message, success, error_msg)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    """,
                    msg_type, code, name, title, message, success, error_msg,
                )
        except Exception as e:
            logger.warning(f"telegram_logs insert error: {e}")

    async def close(self):
        await self._client.aclose()
