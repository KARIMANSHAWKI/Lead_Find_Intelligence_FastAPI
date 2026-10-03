import asyncio
import logging

import httpx

from app.domain.ports.result_callback import ResultCallbackPort

logger = logging.getLogger(__name__)


class ResultCallbackClient(ResultCallbackPort):
    """Deliver results to Laravel without redirects or exposing bearer tokens."""

    async def send(self, url: str, token: str, payload: dict) -> bool:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if response.is_success:
                        return True
                    if response.status_code < 500:
                        break
                except httpx.RequestError:
                    pass
                if attempt < 2:
                    await asyncio.sleep(attempt + 1)
        logger.error("Laravel callback delivery failed for run %s", payload["run_id"])
        return False
