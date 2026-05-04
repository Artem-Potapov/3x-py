from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from asyncio import Task
from typing import TYPE_CHECKING, Any

from async_lru import alru_cache

from python_3xui.models import Inbound

if TYPE_CHECKING:
    from python_3xui.endpoints import Inbounds


class ProductionInboundCache:
    """Per-instance cache of production inbounds + background refresher.

    The wrapper around the fetch impl is built per-instance (not via a
    class-level decorator) so each XUIClient owns its own async-lru cache
    bound to its own event loop. Using a class-level ``@alru_cache()`` on
    the underlying coroutine binds the cache to the first event loop that
    touches it (see async_lru._check_loop), which breaks any caller that
    creates a new XUIClient on a fresh loop (e.g. each pytest-asyncio test).
    Building the wrapper in ``__init__`` gives every instance its own cache
    bound to its own loop.
    """

    def __init__(self, inbounds_endpoint: Inbounds, prod_string_pattern: str,
                 *, panel_id: Any = None, refresh_interval: float = 3600, cache_size: int = 128,
                 ) -> None:
        self._inbounds = inbounds_endpoint
        self.PROD_STRING = re.compile(prod_string_pattern)
        self.panel_id = panel_id
        self._refresh_interval = refresh_interval
        self.get = alru_cache(maxsize=cache_size)(self._fetch_impl)
        self._task: Task | None = None
        self._running: bool = False

    async def _fetch_impl(self) -> tuple[Inbound, ...]:
        inbounds = await self._inbounds.get_all()
        usable: list[Inbound] = [inb for inb in inbounds if self.PROD_STRING.search(inb.remark)]
        if not usable:
            raise RuntimeError("No production inbounds found! Change prod_string!")
        return tuple(usable)

    def start(self, *, create_new: bool = False) -> None:
        """Idempotent. Mirrors the create_new guard from the original task."""
        if self._task is not None and not create_new:
            logging.warning(
                "Cache cleaner task already running; pass create_new=True to override."
            )
            return
        self._running = True
        logging.info("Initializing cache cleaner task for %s", self.panel_id)
        self._task = asyncio.create_task(
            self._refresh_loop(),
            name=f"inb_cache_clearer_for_{self.panel_id}",
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                self._task.cancel("Panel is exiting.")
            self._task = None

    async def _refresh_loop(self) -> None:
        while self._running:
            self.get.cache_clear()
            await self.get()
            await asyncio.sleep(self._refresh_interval)
