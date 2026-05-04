from collections.abc import Awaitable, Callable
from inspect import iscoroutinefunction


class IdentityResolver:
    """Resolves Telegram IDs to UUIDs and subscription IDs.

    Wraps user-supplied sync-or-async generator callables and exposes
    consistently-async resolve_* methods. Pure (no I/O, no state beyond the
    injected callables).
    """

    def __init__(self,
                 sub_gen: Callable[[int], str] | Callable[[int], Awaitable[str]],
                 uuid_gen: Callable[[int], str] | Callable[[int], Awaitable[str]],
                 ) -> None:
        self.sub_gen = sub_gen
        self.uuid_gen = uuid_gen

    async def resolve_uuid(self, telegram_id: int) -> str:
        if iscoroutinefunction(self.uuid_gen):
            return await self.uuid_gen(telegram_id)
        return self.uuid_gen(telegram_id)

    async def resolve_sub(self, telegram_id: int) -> str:
        if iscoroutinefunction(self.sub_gen):
            return await self.sub_gen(telegram_id)
        return self.sub_gen(telegram_id)
