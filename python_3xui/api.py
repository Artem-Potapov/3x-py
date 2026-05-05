import asyncio
import logging
from typing import Any, Awaitable, Callable, List, Literal, Self, overload

import httpx
import pyotp
from httpx import AsyncClient, Response
from pydantic import SecretStr

from . import endpoints
from . import util
from .models import ClientStats, Inbound
from .api_core import ProductionInboundCache, SessionCore, TgIDClientService, IdentityResolver
from .api_core.session_core import (
    CookieType,
    DataType,
    HeaderType,
    ParamType,
)
from .util import JsonType


class XUIClient:
    """Facade for the 3X-UI panel API.

    XUIClient owns and wires up the components that do the real work:
    the HTTP/auth core (``SessionCore``), the production inbound cache,
    the identity resolver, the endpoint handlers, and the high-level
    Telegram-ID client service. It also drives the lifecycle
    (``connect`` / ``login`` / ``disconnect`` and the async context
    manager protocol).

    All the documented attributes below that map to session or auth state
    are read-only passthroughs to the underlying ``SessionCore`` and remain
    in place for backward compatibility.

    Attributes:
        connected: Whether an HTTP session is currently open.
        PROD_STRING: Compiled regex used to identify production inbounds
            (alias of ``ProductionInboundCache.PROD_STRING`` on ``_prod_cache``).
        session, base_host, base_port, base_path, base_url,
        session_start, session_duration, xui_username, xui_password,
        two_fac_secret, totp, max_retries, retry_delay:
            Pass-through to ``SessionCore``.
        sub_gen, uuid_gen: Pass-through to ``IdentityResolver``.
        server_end, clients_end, inbounds_end: Endpoint handlers.
    """

    def __init__(self, base_website: str, base_port: int, base_path: str,
                 *, username: str | None = None, password: str | None = None,
                 two_fac_code: str | None = None, session_duration: int = 3600,
                 custom_prod_string: str = "testing",
                 max_retries: int = 5, retry_delay: int = 1,
                 custom_sub_generator: Callable[[int], str] | Callable[[int], Awaitable[str]] = util.default_sub_from_tgid,
                 custom_uuid_generator: Callable[[int], str] | Callable[[int], Awaitable[str]] = util.get_uuid_from_tgid,
                 panel_id: Any = None
                 ) -> None:
        """Initialize the XUIClient.

        Args:
            base_website: The server hostname (e.g., "example.com").
            base_port: The server port (e.g., 443).
            base_path: The base path for the API (e.g., "/panel").
            username: Username for authentication.
            password: Password for authentication.
            two_fac_code: TOTP secret for 2FA. Short one-shot codes are
                accepted for the current login only.
            session_duration: Maximum session duration in seconds. Defaults to 3600.
            custom_prod_string: Regex pattern used to select production inbounds.
            max_retries: Maximum retries for database-lock responses.
            retry_delay: Seconds to wait between database-lock retries.
            custom_sub_generator: Sync or async callable that receives a
                Telegram ID and returns the subscription ID for new clients.
            custom_uuid_generator: Sync or async callable that receives a
                Telegram ID and returns the UUID for new clients.
            panel_id: this is solely for user's purposes to increase logging and accounting clarity. Default is None.
        """
        self._core = SessionCore(
            base_website,
            base_port,
            base_path,
            username=username,
            password=password,
            two_fac_code=two_fac_code,
            session_duration=session_duration,
            max_retries=max_retries,
            retry_delay=retry_delay,
            panel_id=panel_id,
        )
        self._identity = IdentityResolver(custom_sub_generator, custom_uuid_generator)
        self.sub_gen = self._identity.sub_gen
        self.uuid_gen = self._identity.uuid_gen
        self.panel_id: int | str | Any = panel_id
        self.server_end = endpoints.Server(self._core)
        self.clients_end = endpoints.Clients(self._core)
        self.inbounds_end = endpoints.Inbounds(self._core)
        self._prod_cache = ProductionInboundCache(
            self.inbounds_end,
            custom_prod_string,
            panel_id=self.panel_id,
        )
        self.PROD_STRING = self._prod_cache.PROD_STRING
        self.get_production_inbounds = self._prod_cache.get
        self._tg_client_service = TgIDClientService(
            self.clients_end,
            self.inbounds_end,
            self._identity,
            self._prod_cache,
        )

    @property
    def session(self) -> AsyncClient | None:
        return self._core.session

    @property
    def session_start(self) -> float | None:
        return self._core.session_start

    @property
    def session_duration(self) -> int:
        return self._core.session_duration

    @property
    def base_host(self) -> str:
        return self._core.base_host

    @property
    def base_port(self) -> int:
        return self._core.base_port

    @property
    def base_path(self) -> str:
        return self._core.base_path

    @property
    def base_url(self) -> str:
        return self._core.base_url

    @property
    def xui_username(self) -> str | None:
        return self._core.xui_username

    @property
    def xui_password(self) -> str | None:
        return self._core.xui_password

    @property
    def two_fac_secret(self) -> SecretStr | None:
        return self._core.two_fac_secret

    @property
    def totp(self) -> pyotp.TOTP | None:
        return self._core.totp

    @property
    def max_retries(self) -> int:
        return self._core.max_retries

    @property
    def retry_delay(self) -> int:
        return self._core.retry_delay

    @property
    def connected(self) -> bool:
        return self._core.connected

    @overload
    async def _safe_request(self, *, request_to_send: httpx.Request) -> Response:
        ...

    @overload
    async def _safe_request(self,
                            method: Literal["get", "post", "patch", "delete", "put"],
                            **kwargs: Any,
                            ) -> Response:
        ...

    async def _safe_request(self,
                            method: Literal["get", "post", "patch", "delete", "put"] | None = None,
                            **kwargs: Any,
                            ) -> Response:
        """Delegate for :meth:`BaseModel.from_response` DB-lock retries."""
        return await self._core._safe_request(method=method, **kwargs)

    async def safe_get(self,
                       url: httpx.URL | str,
                       *,
                       params: ParamType | None = None,
                       headers: HeaderType | None = None,
                       cookies: CookieType | None = None,
                       ) -> Response:
        """Execute a safe GET request with automatic retry on database lock.

        Note:
            "Safe" only means "with retries if database is locked".

        Args:
            url: The URL to request.
            params: Query parameters (optional).
            headers: Request headers (optional).
            cookies: Request cookies (optional).

        Returns:
            The HTTP response.

        Raises:
            RuntimeError: If the session is not initialized.
        """
        return await self._core.safe_get(
            url, params=params, headers=headers, cookies=cookies
        )

    async def safe_post(self,
                        url: httpx.URL | str,
                        *,
                        content: DataType | None = None,
                        data: JsonType | None = None,
                        json: Any | None = None,
                        params: ParamType | None = None,
                        headers: HeaderType | None = None,
                        cookies: CookieType | None = None,
                        ) -> Response:
        """Execute a safe POST request with automatic retry on database lock.

        Note:
            "Safe" only means "with retries if database is locked".

        Args:
            url: The URL to request.
            content: Request content (optional).
            data: Form data (optional).
            json: JSON body (optional).
            params: Query parameters (optional).
            headers: Request headers (optional).
            cookies: Request cookies (optional).

        Returns:
            The HTTP response.

        Raises:
            RuntimeError: If the session is not initialized.
        """
        return await self._core.safe_post(
            url,
            content=content,
            data=data,
            json=json,
            params=params,
            headers=headers,
            cookies=cookies,
        )

    async def login(self) -> None:
        """Authenticate the client with the 3X-UI panel.

        This method performs the login action, establishing a session for
        subsequent API requests.

        Raises:
            ValueError: If the login credentials are incorrect.
            RuntimeError: If the server returns an error status code.
        """
        await self._core.login()

    def connect(self) -> Self:
        """Establish a connection to the 3X-UI panel.

        This method creates an async HTTP client session.

        Returns:
            Self: The XUIClient instance.
        """
        self._core.connect()
        return self

    async def disconnect(self) -> None:
        """Close the client session.

        This method closes the async HTTP client session.
        """
        await self._prod_cache.stop()
        await self._core.disconnect()

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        This method is called when the client is used in an `async with`
        statement. It establishes a connection and starts the cache clearing
        task.

        Returns:
            Self: The XUIClient instance.
        """
        self.connect()
        await self.login()
        self._prod_cache.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager.

        This method is called when the client context is exited. It closes
        the client session.

        Args:
            exc_type: The exception type, if an exception occurred.
            exc_val: The exception value, if an exception occurred.
            exc_tb: The exception traceback, if an exception occurred.
        """
        if exc_type is None or exc_type is asyncio.exceptions.CancelledError:
            logging.info("Client is disconnecting (panel: %s)", self.panel_id or self.base_host)
        else:
            logging.warning("Client is disconnecting due to an error (may be unrelated):"
                            "\n%s, with value %s\nStacktrace:%s",
                            exc_type, exc_val, exc_tb, exc_info=exc_tb)
        logging.info("Client is disconnecting: %s", self.panel_id or self.base_host)
        await self.disconnect()
        return

    #=========================="meta" methods==========================
    async def _resolve_uuid(self, telegram_id: int) -> str:
        """Resolve a Telegram ID to a UUID via ``self.uuid_gen``.

        Handles both sync and async callables.
        """
        return await self._identity.resolve_uuid(telegram_id)

    async def _resolve_sub(self, telegram_id: int) -> str:
        """Resolve the subscription ID from a telegram id via ``self.sub_gen``

        Handles both sync and async callables.
        """
        return await self._identity.resolve_sub(telegram_id)

    #========================inbound management========================
    async def add_inbound(self, inbound: Inbound) -> Response:
        """Create a new inbound. Returns the panel HTTP response."""
        return await self.inbounds_end.add_inbound(inbound)

    async def delete_inbound(self, inbound_id: int) -> Response:
        """Delete an inbound by panel ID. Returns the panel HTTP response."""
        return await self.inbounds_end.delete_inbound_by_id(inbound_id)

    #========================clients management========================
    async def get_client_with_tgid(self, tgid: int, inbound_id: int | None = None) -> list[ClientStats]:
        """Retrieve client information by Telegram ID.

        This method fetches client information using the Telegram ID. If
        an inbound ID is provided, it fetches the client by email derived
        from the Telegram ID and inbound ID.

        Args:
            tgid: The Telegram ID of the client.
            inbound_id: The ID of the inbound (optional).

        Returns:
            List[ClientStats]: A list of client statistics.

        Note:
            If the client is not found by Telegram ID, the method falls back
            to using the Telegram ID and inbound ID to fetch the client.
        """
        return await self._tg_client_service.get_client_with_tgid(tgid, inbound_id)

    async def create_and_add_prod_client(self, telegram_id: int, *,
                                         additional_remark: str | None = None,
                                         expiry_time: int = 0,
                                         exist_ok: bool = False,
                                         replace_if_exist: bool = False,
                                         ) -> dict[int, Response]:
        """Create and add a production client.

        This method creates a new client with the given Telegram ID and
        adds it to the production inbounds. The client is configured with
        default settings and the additional remark. The subscription ID is
        created by ``self.sub_gen``; by default this is
        ``util.default_sub_from_tgid``.

        Args:
            telegram_id: The Telegram ID of the client.
            additional_remark: An optional additional remark for the client.
            expiry_time: Expiry time in SECONDS as a UNIX timestamp.
            exist_ok: If True, return API responses even when the panel reports
                a duplicate email.
            replace_if_exist: If True, inbounds that respond with
                "duplicate email" will have their existing client updated
                (via ``request_update_client``) instead of raising an error.
                Updates are burst-shot in a second ``asyncio.gather`` for
                minimal latency.

        Returns:
            Dict[int, Response]: A mapping of inbound IDs to API responses.
            For inbounds where the add succeeded, the response is from the
            add call. For inbounds where ``replace_if_exist`` replaced a
            duplicate, the response is from the update call.

        Raises:
            ClientEmailAlreadyExistsError: If a duplicate client is reported,
                ``replace_if_exist`` is False, and ``exist_ok`` is False.
        """
        return await self._tg_client_service.create_and_add_prod_client(
            telegram_id,
            additional_remark=additional_remark,
            expiry_time=expiry_time,
            exist_ok=exist_ok,
            replace_if_exist=replace_if_exist,
        )

    async def update_client_by_tgid_only(self, telegram_id: int, prod_only: bool, /, *,
                                         security: str | None = None,
                                         password: str | None = None,
                                         flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                         limit_ip: int | None = None,
                                         limit_gb: int | None = None,
                                         expiry_time: int | None = None,
                                         enable: bool | None = None,
                                         sub_id: str | None = None,
                                         comment: str | None = None,
                                         verbose: bool = True
                                         ) -> list[Response]:
        """Update every matching client found by Telegram ID.

        The client UUID is derived from ``telegram_id`` and searched across
        either production inbounds or all inbounds. Only keyword arguments with
        non-None values are applied to the client model before sending update
        requests.

        Args:
            telegram_id: Telegram ID used to derive the client UUID.
            prod_only: If True, search only production inbounds. If False,
                search every inbound returned by the panel.
            security: New security setting.
            password: New password.
            flow: New VLESS flow value.
            limit_ip: New simultaneous IP connection limit.
            limit_gb: New traffic limit in gigabytes.
            expiry_time: New expiry timestamp in seconds.
            enable: New enabled state.
            sub_id: New subscription ID.
            comment: New client comment.
            verbose: If True, warn when ``expiry_time`` looks like a duration
                instead of a UNIX timestamp.

        Returns:
            Responses from each inbound where a matching client was updated.
        """
        return await self._tg_client_service.update_client_by_tgid_only(
            telegram_id,
            prod_only,
            security=security,
            password=password,
            flow=flow,
            limit_ip=limit_ip,
            limit_gb=limit_gb,
            expiry_time=expiry_time,
            enable=enable,
            sub_id=sub_id,
            comment=comment,
            verbose=verbose,
        )

    async def update_client_by_tgid_inbid(self, telegram_id: int, inbound_id: int, /, *,
                                          security: str | None = None,
                                          password: str | None = None,
                                          flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                          limit_ip: int | None = None,
                                          limit_gb: int | None = None,
                                          expiry_time: int | None = None,
                                          enable: bool | None = None,
                                          sub_id: str | None = None,
                                          comment: str | None = None,
                                          email: str | None = None,
                                          verbose: bool = True,
                                          force_resolve_by_email: bool = False) -> Response:
        """
        Update a client in a specific inbound by Telegram ID. NOT optimized for multiple inbounds.

        Args:
            telegram_id: The Telegram ID of the client
            inbound_id: The ID of the inbound where the client exists
            security: Client security setting (optional)
            password: Client password (optional)
            flow: VLESS flow type (optional)
            limit_ip: IP connection limit (optional)
            limit_gb: Data limit in GB (optional)
            expiry_time: Client expiry time (UNIX timestamp) (optional)
            enable: Whether the client is enabled (optional)
            sub_id: Subscription ID (optional)
            comment: Client comment/note (optional)
            email: New client email (optional). USE WITH CAUTION BECAUSE THE XUIClient WILL NOT TRACK THE NEW EMAIL.
            verbose: Enables guardrails.
            force_resolve_by_email: Whether to enable fetch-thru-email fallback when a client is not found, uses ~3 extra fetches but provides an extra layer of protection.
        Returns:
            Response from the API
        """
        return await self._tg_client_service.update_client_by_tgid_inbid(
            telegram_id,
            inbound_id,
            security=security,
            password=password,
            flow=flow,
            limit_ip=limit_ip,
            limit_gb=limit_gb,
            expiry_time=expiry_time,
            enable=enable,
            sub_id=sub_id,
            comment=comment,
            email=email,
            verbose=verbose,
            force_resolve_by_email=force_resolve_by_email,
        )

    async def delete_client_by_tgid(self, telegram_id: int, inbound_id: int, *, suffix: str = "") -> Response:
        """Delete a client from a specific inbound by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client
            inbound_id: The ID of the inbound
            suffix: Appended to the generated email before deletion (use when the
                target client was created with a custom email suffix).

        Returns:
            Response from the API
        """
        return await self._tg_client_service.delete_client_by_tgid(telegram_id, inbound_id, suffix=suffix)

    async def revoke_client_by_tgid_all_inbounds(self, telegram_id: int) -> List[Response]:
        """Delete a client from all production inbounds by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client

        Returns:
            List of Response objects from each deletion attempt
        """
        return await self._tg_client_service.revoke_client_by_tgid_all_inbounds(telegram_id)
