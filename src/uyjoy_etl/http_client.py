from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from uyjoy_etl.config import OlxConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int | None
    elapsed_ms: int
    ok: bool
    text: str | None
    error_message: str | None = None


class OlxHttpClient:
    """Rate-limit va retry qo'shilgan oddiy OLX HTTP client."""

    def __init__(self, config: OlxConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,uz;q=0.8,en;q=0.7",
            }
        )
        self._last_request_at = 0.0

    def get(self, url: str) -> FetchResult:
        """URLni oladi; xato bo'lsa retry qiladi va barcha holatni FetchResultga yozadi."""

        last_result: FetchResult | None = None
        for attempt in range(1, self._config.max_retries + 1):
            self._sleep_if_needed()
            started = time.perf_counter()
            try:
                logger.info("HTTP GET boshlanyapti | attempt=%s | url=%s", attempt, url)
                response = self._session.get(url, timeout=self._config.timeout_seconds)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                ok = 200 <= response.status_code < 300
                result = FetchResult(
                    url=url,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    ok=ok,
                    text=response.text if ok else None,
                    error_message=None if ok else response.text[:500],
                )
                logger.info(
                    "HTTP GET tugadi | status=%s | elapsed_ms=%s | ok=%s | url=%s",
                    response.status_code,
                    elapsed_ms,
                    ok,
                    url,
                )
                if ok:
                    return result
                last_result = result
                if response.status_code in {400, 401, 403, 404, 410}:
                    return result
            except requests.RequestException as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                last_result = FetchResult(
                    url=url,
                    status_code=None,
                    elapsed_ms=elapsed_ms,
                    ok=False,
                    text=None,
                    error_message=str(exc),
                )
                logger.warning(
                    "HTTP GET xato | attempt=%s | elapsed_ms=%s | error=%s | url=%s",
                    attempt,
                    elapsed_ms,
                    exc,
                    url,
                )

            time.sleep(min(2 * attempt, 10))

        assert last_result is not None
        return last_result

    def _sleep_if_needed(self) -> None:
        elapsed = time.perf_counter() - self._last_request_at
        wait_seconds = self._config.request_delay_seconds - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        self._last_request_at = time.perf_counter()
