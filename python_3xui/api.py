import asyncio
import json
import logging
import re
from asyncio import Task
from collections.abc import Sequence, Mapping
from datetime import datetime, UTC
from inspect import iscoroutinefunction
from logging import DEBUG
from typing import Self, Optional, Dict, Iterable, AsyncIterable, Type, Union, Any, List, Tuple, Literal, Callable, Awaitable, overload
import contextlib

import httpx
import pyotp
from async_lru import alru_cache
from httpx import Response, AsyncClient, Request
from pydantic import SecretStr

from . import custom_exceptions
from . import util
from . import endpoints
from .models import Inbound, SingleInboundClient, ClientStats
from .util import JsonType, async_range, get_inbound_in_client

DataType: Type[str | bytes | Iterable[bytes] | AsyncIterable[bytes]] = Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]]
PrimitiveData = Optional[Union[str, int, float, bool]]
ParamType = Union[
    Mapping[str, Union[PrimitiveData, Sequence[PrimitiveData]]],
    list[Tuple[str, PrimitiveData]],
    tuple[Tuple[str, PrimitiveData], ...],
    str,
    bytes,
]
CookieType = Union[Dict[str, str], list[tuple[str, str]]]
HeaderType = Union[
    Mapping[str, str],
    Mapping[bytes, bytes],
    Sequence[Tuple[str, str]],
    Sequence[Tuple[bytes, bytes]],
]


class XUIClient:
    """Main client for interacting with the 3X-UI panel API.

    This class provides methods for authenticating with the 3X-UI panel,
    managing sessions, and performing operations on inbounds and clients.
    It also owns the endpoint handlers and the per-instance production
    inbound cache.

    Attributes:
        connected: Whether an HTTP session is currently open.
        PROD_STRING: Compiled regex used to identify production inbounds.
        session: The async HTTP client session, if connected.
        base_host: The server hostname.
        base_port: The server port.
        base_path: The base path for the API.
        base_url: The full base URL for API requests.
        session_start: Timestamp of when the session was created.
        session_duration: Maximum session duration in seconds.
        xui_username: Username for authentication.
        xui_password: Password for authentication.
        two_fac_secret: TOTP secret or one-shot 2FA code, if configured.
        totp: TOTP generator used for repeated logins when a secret is provided.
        max_retries: Maximum number of retry attempts for failed requests.
        retry_delay: Delay in seconds between retries.
        sub_gen: Callable/Awaitable used to derive subscription IDs from Telegram IDs.
        uuid_gen: Callable/Awaitable used to derive UUIDs from Telegram IDs.
        server_end: Server endpoint handler.
        clients_end: Clients endpoint handler.
        inbounds_end: Inbounds endpoint handler.
    """

    def __init__(self, base_website: str, base_port: int, base_path: str,
                 *, username: str | None = None, password: str | None = None,
                 two_fac_code: str | None = None, session_duration: int = 3600,
                 custom_prod_string: str = "testing",
                 max_retries: int = 5, retry_delay=1,
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
        self.connected: bool = False
        self.PROD_STRING = re.compile(custom_prod_string)
        self.session: AsyncClient | None = None
        self.base_host: str = base_website
        self.base_port: int = base_port
        self.base_path: str = base_path
        self.base_url: str = f"https://{self.base_host}:{self.base_port}{self.base_path}"
        self.session_start: float | None = None
        self.session_duration: int = session_duration
        self.xui_username: str | None = username
        self.xui_password: str | None = password
        self.two_fac_secret: SecretStr | None = SecretStr(two_fac_code) if two_fac_code is not None else None
        self.totp: pyotp.TOTP | None = None
        self.max_retries: int = max_retries
        self.retry_delay: int = retry_delay
        self.sub_gen = custom_sub_generator
        self.uuid_gen = custom_uuid_generator
        self.panel_id: int | str | Any = panel_id
        # endpoints
        self.server_end = endpoints.Server(self)
        self.clients_end = endpoints.Clients(self)
        self.inbounds_end = endpoints.Inbounds(self)
        # Per-instance cache wrapper. Using a class-level @alru_cache() on the underlying coroutine binds the cache to
        # the first event loop that touches it (see async_lru._check_loop), which breaks any caller that creates
        # a new XUIClient on a fresh loop (e.g. each pytest-asyncio test). Building the wrapper here gives every
        # instance its own cache bound to its own loop.
        self.get_production_inbounds = alru_cache(maxsize=128)(self._get_production_inbounds_impl)
        self._cache_cleaner_task: Task | None = None
        #init self.totp
        if self.two_fac_secret:
            if len(self.two_fac_secret.get_secret_value()) <= 8:
                print("WARNING: You seem to have entered a 2FA **code**, not a 2FA secret."
                      "Although entering the secret is dangerous, there is no other way to provide a consistent way"
                      "for continuous login. This code will only work for this specific login.")
                self.totp = None
            else:
                self.totp = pyotp.TOTP(self.two_fac_secret.get_secret_value())

    #========================request stuffs========================
    @overload
    async def _safe_request(self, *, request_to_send: httpx.Request) -> Response:
        ...

    @overload
    async def _safe_request(self, method: Literal["get", "post", "patch", "delete", "put"],
                            **kwargs) -> Response:
        ...

    async def _safe_request(self,
                            method: Literal["get", "post", "patch", "delete", "put"] | None = None,
                            **kwargs) -> Response:
        """Execute an HTTP request with automatic retry on database lock.

        The request can be made either from a prebuilt ``request_to_send`` or
        from an HTTP method plus keyword arguments accepted by ``httpx``.
        The method handles automatic session refresh on expired 404 responses
        and retries when the 3X-UI database is locked.

        Args:
            method: The HTTP method to use when building a new request.
            **kwargs: Either ``request_to_send`` by itself, or request
                arguments such as ``url``, ``json``, ``params``, and headers.

        Returns:
            The HTTP response.

        Raises:
            ValueError: If neither a method nor a prebuilt request is provided,
                or both request styles are mixed.
            RuntimeError: If max retries are exceeded or a valid session gets
                an unexpected 404 response.
        """
        if "request_to_send" in kwargs and len(kwargs.keys()) != 1:
            raise ValueError("Provide either a prebuilt request or arguments to build one.")
        if not "request_to_send" in kwargs:
            if method is None:
                raise ValueError("If there's no prebuilt request, you must provide a method.")

        url = kwargs["url"] if "url" in kwargs.keys() else kwargs["request_to_send"].url
        if "json" in kwargs:
            json_payload = kwargs["json"]
        elif "request_to_send" in kwargs:
            _req = kwargs["request_to_send"]
            if _req.content:
                try:
                    json_payload = json.loads(_req.content.decode())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    json_payload = None
            else:
                json_payload = None
        else:
            json_payload = None
        logging.info("Safe %s is running to %s%s\nJSON Payload: %s",
                     method, str(self.session.base_url), str(url),
                     json.dumps(json_payload) if json_payload is not None else "(no payload)")
        async for attempt in async_range(self.max_retries):
            if "request_to_send" in kwargs:
                _request: Request = kwargs["request_to_send"]
                resp = await self.session.send(_request)
            else:
                # noinspection PyTypeChecker
                resp = await self.session.request(method, **kwargs)
            if resp.status_code // 100 != 2:  #because it can return either 201 or 202
                if resp.status_code == 404:
                    now: float = datetime.now(UTC).timestamp()
                    if self.session_start is None or now - self.session_start > self.session_duration:
                        logging.info("Client (panel: %s) is not logged in, logging in...", self.panel_id or self.base_host)
                        await self.login()
                        continue
                    else:
                        logging.error("Server returned a status code of %s with a valid session", resp.status_code)
                        raise RuntimeError("""Server returned a 404, and the session should still be valid, likely it's a REAL 404""")
                else:
                    logging.error("Server returned a status code of %s", resp.status_code)
                    resp.raise_for_status()

            status = await util.check_xui_response(resp)
            if status == "OK":
                return resp
            elif status == "DB_LOCKED":
                if attempt + 1 >= self.max_retries:
                    raise RuntimeError("Too many retries")
                await asyncio.sleep(self.retry_delay)
                continue
            else:
                logging.error("A %s request was unsuccessful (code 200, but success=false).\nPayload: %s",
                              method, json.dumps(resp.json()))
                return resp
        raise RuntimeError(f"For some reason safe_request didn't exit, dump:\nmethod:\n{method}\n{kwargs}")

    async def safe_get(self,
                       url: httpx.URL | str,
                       *,
                       params: ParamType | None = None,
                       headers: HeaderType | None = None,
                       cookies: CookieType | None = None) -> Response:
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
        #NOTE: "safe" only means "with retries if database is locked"!
        if self.session is None:
            raise RuntimeError("Session is not initialized")

        resp = await self._safe_request(method="get",
                                        url=url,
                                        params=params,
                                        headers=headers,
                                        cookies=cookies)

        return resp

    async def safe_post(self,
                        url: httpx.URL | str,
                        *,
                        content: DataType | None = None,
                        data: JsonType | None = None,
                        json: Any | None = None,
                        params: ParamType | None = None,
                        headers: HeaderType | None = None,
                        cookies: CookieType | None = None) -> Response:
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
        if self.session is None:
            raise RuntimeError("Session is not initialized")

        resp = await self._safe_request(method="post",
                                        url=url,
                                        content=content,
                                        data=data,
                                        json=json,
                                        params=params,
                                        headers=headers,
                                        cookies=cookies)
        return resp

    #========================Login and session management==============================
    async def login(self) -> None:
        """Authenticate the client with the 3X-UI panel.

        This method performs the login action, establishing a session for
        subsequent API requests.

        Raises:
            ValueError: If the login credentials are incorrect.
            RuntimeError: If the server returns an error status code.
        """
        payload = {
            "username": self.xui_username,
            "password": self.xui_password,
        }
        if self.totp:
            if self.totp.interval - datetime.now().timestamp() % self.totp.interval < 3:
                await asyncio.sleep(3.1)  # just to not submit an invalid code
            payload["twoFactorCode"] = self.totp.now()
        else:
            if self.two_fac_secret:
                payload["twoFactorCode"] = self.two_fac_secret.get_secret_value()

        logging.info("Client is logging in (panel: %s)", self.panel_id or self.base_host)
        resp = await self.session.post("/login", data=payload)
        if resp.status_code == 200:
            resp_json = resp.json()
            if "success" not in resp_json:
                raise RuntimeError(f"Error: server returned a status code of {resp.status_code} but the response is not valid: {resp_json}")
            if not resp_json["success"]:
                raise ValueError("Error: wrong credentials (including status code) or failed login.")
            self.session_start: float = (datetime.now(UTC).timestamp())
            return
        else:
            raise RuntimeError(f"Error: server returned a status code of {resp.status_code}")

    def connect(self) -> Self:
        """Establish a connection to the 3X-UI panel.

        This method creates an async HTTP client session.

        Returns:
            Self: The XUIClient instance.
        """
        logging.log(DEBUG, "Client connected (panel: %s)", self.panel_id or self.base_url)
        self.session = AsyncClient(base_url=self.base_url)
        self.connected = True
        return self

    async def disconnect(self) -> None:
        """Close the client session.

        This method closes the async HTTP client session.
        """
        if self._cache_cleaner_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                self._cache_cleaner_task.cancel("Panel is exiting.")
        self.connected = False

        if self.session is not None:
            await self.session.aclose()

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
        if not self._cache_cleaner_task:
            self._cache_cleaner_task = asyncio.create_task(
                self._clear_prod_inbound_cache_task(create_new=True), name=f"inb_cache_clearer_for_{self.base_url}"
            )
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
        print(f"Client is disconnecting: {self.panel_id or self.base_host}")
        await self.disconnect()
        return

    #=========================="meta" methods==========================
    async def _resolve_uuid(self, telegram_id: int) -> str:
        """Resolve a Telegram ID to a UUID via ``self.uuid_gen``.

        Handles both sync and async callables.
        """
        if iscoroutinefunction(self.uuid_gen):
            return await self.uuid_gen(telegram_id)
        return self.uuid_gen(telegram_id)

    async def _resolve_sub(self, telegram_id: int) -> str:
        """Resolve the subscription ID from a telegram id via ``self.sub_gen``

        Handles both sync and async callables.
        """
        if iscoroutinefunction(self.sub_gen):
            return await self.sub_gen(telegram_id)
        return self.sub_gen(telegram_id)

    #========================inbound management========================
    async def _get_production_inbounds_impl(self) -> tuple[Inbound, ...]:
        """Retrieve production inbounds.

        This method fetches all inbounds and filters them based on the
        production string. It is wrapped in a per-instance ``alru_cache``
        in ``__init__`` and exposed as ``get_production_inbounds``; do not
        call this method directly outside of that wrapper.

        Returns:
            tuple[Inbound]: A list of production inbounds.

        Raises:
            RuntimeError: If no production inbounds are found.
        """
        inbounds = await self.inbounds_end.get_all()
        usable_inbounds: list[Inbound] = []
        for inb in inbounds:
            if self.PROD_STRING.search(inb.remark):
                usable_inbounds.append(inb)
        if len(usable_inbounds) == 0:
            raise RuntimeError("No production inbounds found! Change prod_string!")

        return tuple(usable_inbounds)

    async def _clear_prod_inbound_cache_task(self, *, create_new: bool = False):
        """Refresh the production inbound cache in the background.

        The async context manager starts this loop after login. Each cycle
        clears the cached production inbound list, repopulates it from the
        panel, and then waits before refreshing again.

        create_new param is kw-only and for people who know what they're doing, so they won't get the warning.
        """
        if (self._cache_cleaner_task is not None) and (not create_new):
            logging.warning("You're trying to create another cache cleaner task, which is a FaF (Fire-And-Forget)."
                            "Please destroy the previous task and set _cache_cleaner_task to None, if you know what you're doing.")
            return
        logging.info("Initializing cache cleaner task for %s", self.panel_id)
        while self.connected:
            self.get_production_inbounds.cache_clear()
            await self.get_production_inbounds()  # fill the cache
            await asyncio.sleep(3600)  # update every 1h

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
        if inbound_id:
            email = util.generate_email_from_tgid_inbid(tgid, inbound_id)
            resp = [await self.clients_end.get_client_with_email(email)]
            return resp
        uuid = await self._resolve_uuid(tgid)
        resp = await self.clients_end.get_client_with_uuid(uuid)
        return resp

    async def create_and_add_prod_client(self, telegram_id: int, *,
                                         additional_remark: str | None = None,
                                         expiry_time: int = 0,
                                         exist_ok: bool = False
                                         ) -> list[Response]:
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

        Returns:
            List[Response]: A list of responses from the server for each
            inbound the client was added to.

        Raises:
            ClientEmailAlreadyExistsError: If a duplicate client is reported
                and ``exist_ok`` is False.
        """
        production_inbounds: tuple[Inbound, ...] = await self.get_production_inbounds()

        tasks = []
        custom_sub: str
        custom_sub = await self._resolve_sub(telegram_id)
        uuid = await self._resolve_uuid(telegram_id)
        for inb in production_inbounds:
            tmp_email = util.generate_email_from_tgid_inbid(telegram_id, inb.id)
            client = SingleInboundClient(
                uuid=uuid,
                flow="",
                email=tmp_email,
                limit_gb=0,
                enable=True,
                subscription_id=custom_sub,
                comment=f"{additional_remark + ", " if additional_remark else ""}created at {datetime.now(UTC)}",
                expiry_time=expiry_time * 1000,
            )
            tasks.append(asyncio.create_task(self.clients_end.add_client(client, inb.id)))
        responses: list[Response] = await asyncio.gather(*tasks)
        if exist_ok:
            return responses
        for resp in responses:
            json_resp = resp.json()
            if "duplicate email" in json_resp["msg"].lower():
                logging.error("ERROR: Client already exists and exist_ok not set: %s", json_resp["msg"])
                raise custom_exceptions.ClientEmailAlreadyExistsError(json_resp["msg"])
        return responses

    async def _find_client_in_inbound(self, client_uuid: str, inbound_id: int,
                                      use_cache=False) -> SingleInboundClient | None:
        """Note:
            Cached production inbounds can be stale because the panel may be
            changed by another actor. If a cached production inbound misses the
            client, the production cache is cleared and fetched once more
            before falling back to a direct inbound lookup.
        """
        if use_cache:
            prod_inbs = await self.get_production_inbounds()
            prod_inb_index = None
            for i, prod_inb in enumerate(prod_inbs):  # see if inbound is production
                if inbound_id == prod_inb.id:
                    prod_inb_index = i

            if prod_inb_index is not None:
                needed_inb: Inbound = prod_inbs[prod_inb_index]
                result = get_inbound_in_client(client_uuid, needed_inb)
                if result is None:
                    self.get_production_inbounds.cache_clear()  # this means client is in a prod inbound but it's not refreshed
                    new_inb = (await self.get_production_inbounds())[prod_inb_index]
                    new_result = get_inbound_in_client(client_uuid, new_inb)
                    return new_result

        inb = await self.inbounds_end.get_specific_inbound(inbound_id)
        for client in inb.settings.clients:
            if client.uuid == client_uuid:
                return client
        return None

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
        updates = {
            "security": security,
            "password": password,
            "flow": flow,
            "limit_ip": limit_ip,
            "limit_gb": limit_gb,
            "expiry_time": expiry_time,
            "enable": enable,
            "sub_id": sub_id,
            "comment": comment,
        }
        # remove None values
        updates = {k: v for k, v in updates.items() if v is not None}

        if verbose:
            if expiry_time and expiry_time < 1e9:
                logging.warning("Warning: You're trying to update a client with expiry time %s. "
                                "You set it to expire before 2001, likely because you provided the DURATION. "
                                "You need to provide a TIMESTAMP. "
                                "If you want to disable this message, set verbose=false.",
                                expiry_time)

        _to_exec: list[Task] = []
        client_uuid = await self._resolve_uuid(telegram_id)
        if prod_only:
            self.get_production_inbounds.cache_clear()
            inbounds = await self.get_production_inbounds()
        else:
            inbounds = await self.inbounds_end.get_all()
        for inbound in inbounds:
            found_client = util.get_inbound_in_client(client_uuid, inbound)
            if found_client:
                new_client = found_client.model_copy(update=updates, deep=True)
                _to_exec.append(
                    asyncio.create_task(self.clients_end.request_update_client(
                        new_client, inbound.id, original_uuid=client_uuid
                    ))
                )
        responses = await asyncio.gather(*_to_exec)
        return responses

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
                                          verbose: bool = True) -> Response:
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
            email: New client email (optional). USE WITH CAUTION BECAUSE THE PANEL WILL NOT TRACK THE NEW EMAIL.

        Returns:
            Response from the API
        """
        if verbose:
            if expiry_time and expiry_time < 1e9:
                logging.warning("Warning: You're trying to update a client with expiry time %s. "
                                "You set it to expire before 2001, likely because you provided the DURATION. "
                                "You need to provide a TIMESTAMP. "
                                "If you want to disable this message, set verbose=false.",
                                expiry_time)

        client_uuid = await self._resolve_uuid(telegram_id)
        resp = await self.clients_end.update_single_client(
            inbound_id=inbound_id, client_uuid=client_uuid,
            security=security,
            password=password,
            email=email,
            flow=flow,
            limit_ip=limit_ip,
            limit_gb=limit_gb,
            expiry_time=expiry_time,
            enable=enable,
            sub_id=sub_id,
            comment=comment
        )
        return resp

    async def delete_client_by_tgid(self, telegram_id: int, inbound_id: int) -> Response:
        """Delete a client from a specific inbound by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client
            inbound_id: The ID of the inbound

        Returns:
            Response from the API
        """
        email = util.generate_email_from_tgid_inbid(telegram_id, inbound_id)
        resp = await self.clients_end.delete_client_by_email(email, inbound_id)
        return resp

    async def revoke_client_by_tgid_all_inbounds(self, telegram_id: int) -> List[Response]:
        """Delete a client from all production inbounds by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client

        Returns:
            List of Response objects from each deletion attempt
        """
        production_inbounds = await self.get_production_inbounds()
        _to_exec: list[Task] = []
        for inbound in production_inbounds:
            email = util.generate_email_from_tgid_inbid(telegram_id, inbound.id)
            _to_exec.append(
                asyncio.create_task(self.clients_end.delete_client_by_email(email, inbound.id))
            )
            logging.info("Clients of of tgid %s pending deletion", telegram_id)
        responses = await asyncio.gather(*_to_exec)
        return responses
