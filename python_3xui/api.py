from collections.abc import Sequence, Mapping
from typing import Self, Optional, Dict, Iterable, AsyncIterable, Type, Union, Any, List, Tuple, Literal
from datetime import datetime, UTC

from httpx import Response, AsyncClient
from async_lru import alru_cache
import asyncio
import httpx

from . import util
from .models import Inbound, SingleInboundClient, ClientStats
from .util import JsonType, async_range

DataType: Type[str | bytes | Iterable[bytes] | AsyncIterable[bytes]] = Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]]
PrimitiveData = Optional[Union[str, int, float, bool]]
ParamType = Union[
    Mapping[str, Union[PrimitiveData, Sequence[PrimitiveData]]],
    List[Tuple[str, PrimitiveData]],
    Tuple[Tuple[str, PrimitiveData], ...],
    str,
    bytes,
]
CookieType = Union[Dict[str, str], List[Tuple[str, str]]]
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

    The client implements a singleton pattern to ensure only one instance
    exists at a time.

    Attributes:
        PROD_STRING: String used to identify production inbounds.
        session: The async HTTP client session.
        base_host: The server hostname.
        base_port: The server port.
        base_path: The base path for the API.
        base_url: The full base URL for API requests.
        session_start: Timestamp of when the session was created.
        session_duration: Maximum session duration in seconds.
        xui_username: Username for authentication.
        xui_password: Password for authentication.
        two_fac_code: Two-factor authentication code (if enabled).
        max_retries: Maximum number of retry attempts for failed requests.
        retry_delay: Delay in seconds between retries.
        server_end: Server endpoint handler.
        clients_end: Clients endpoint handler.
        inbounds_end: Inbounds endpoint handler.
    """
    _instance = None

    def __init__(self, base_website: str, base_port: int, base_path: str,
                 *, xui_username: str | None = None, xui_password: str | None = None,
                 two_fac_code: str | None = None, session_duration: int = 3600) -> None:
        """Initialize the XUIClient.

        Args:
            base_website: The server hostname (e.g., "example.com").
            base_port: The server port (e.g., 443).
            base_path: The base path for the API (e.g., "/panel").
            xui_username: Username for authentication.
            xui_password: Password for authentication.
            two_fac_code: Two-factor authentication code (if enabled).
            session_duration: Maximum session duration in seconds. Defaults to 3600.
        """
        from . import endpoints # look, I know it's bad, but we need to evade cyclical imports
        self.PROD_STRING = "tester-777"
        self.session: AsyncClient | None = None
        self.base_host: str = base_website
        self.base_port: int = base_port
        self.base_path: str = base_path
        self.base_url: str = f"https://{self.base_host}:{self.base_port}{self.base_path}"
        self.session_start: float | None = None
        self.session_duration: int = session_duration
        self.xui_username: str | None = xui_username
        self.xui_password: str | None = xui_password
        self.two_fac_code: str | None = two_fac_code
        self.max_retries: int = 5
        self.retry_delay: int = 1
        # endpoints
        self.server_end = endpoints.Server(self)
        self.clients_end = endpoints.Clients(self)
        self.inbounds_end = endpoints.Inbounds(self)

    #========================singleton pattern========================
    def __new__(cls, *args, **kwargs):
        """Create or return the singleton instance.

        Args:
            *args: Positional arguments passed to __init__.
            **kwargs: Keyword arguments passed to __init__.

        Returns:
            The singleton XUIClient instance.
        """
        print("initializing client")
        if cls._instance is None:
            print("nu instance")
            cls._instance = super(XUIClient, cls).__new__(cls)
        return cls._instance

    #========================request stuffs========================
    async def _safe_request(self,
                            method: Literal["get", "post", "patch", "delete", "put"],
                            **kwargs) -> Response:
        """Execute an HTTP request with automatic retry on database lock.

        This method handles automatic session refresh and retries when
        the 3X-UI database is locked.

        Args:
            method: The HTTP method to use.
            **kwargs: Additional arguments passed to the HTTP request.

        Returns:
            The HTTP response.

        Raises:
            RuntimeError: If max retries exceeded or session is invalid.
        """
        print(f"SAFE REQUEST, {method}, is running to a URL of {kwargs["url"]}")
        print(str(self.session.base_url) + str(kwargs["url"]))
        async for attempt in async_range(self.max_retries):
            resp = await self.session.request(method=method, **kwargs)
            if resp.status_code // 100 != 2:  #because it can return either 201 or 202
                if resp.status_code == 404:
                    now: float = datetime.now(UTC).timestamp()
                    if self.session_start is None or now - self.session_start > self.session_duration:
                        print("Guys, we're not logged in, fixing that rn")
                        await self.login()
                        continue
                    else:
                        raise RuntimeError("""Server returned a 404, and the session should still be valid, likely it's a REAL 404""")
                else:
                    raise RuntimeError(f"Wrong status code: {resp.status_code}")

            status = await util.check_xui_response_validity(resp)
            if status == "OK":
                return resp
            elif status == "DB_LOCKED":
                if attempt + 1 >= self.max_retries:
                    # resp.status_code = 518 # so the error can simply be handled as a "bad request"
                    # return resp
                    raise RuntimeError("Too many retries")
                await asyncio.sleep(self.retry_delay)
                continue
            else:
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

        print(self.session.base_url)
        print("WE'RE LOGGING IN")
        resp = await self.session.post("/login", data=payload)
        if resp.status_code == 200:
            resp_json = resp.json()
            if resp_json["success"]:
                self.session_start: float = (datetime.now(UTC).timestamp())
                return
            else:
                raise ValueError("Error: wrong credentials or failed login")
        else:
            raise RuntimeError(f"Error: server returned a status code of {resp.status_code}")

    def connect(self) -> Self:
        """Establish a connection to the 3X-UI panel.

        This method creates an async HTTP client session.

        Returns:
            Self: The XUIClient instance.
        """
        self.session = AsyncClient(base_url=self.base_url)
        return self

    async def disconnect(self) -> None:
        """Close the client session.

        This method closes the async HTTP client session.
        """
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
        asyncio.create_task(self.clear_prod_inbound_cache())
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
        print("disconnectin'")
        await self.disconnect()
        return

    #========================inbound management========================
    @alru_cache
    async def get_production_inbounds(self) -> List[Inbound]:
        """Retrieve production inbounds.

        This method fetches all inbounds and filters them based on the
        production string. It is cached for efficiency.

        Returns:
            List[Inbound]: A list of production inbounds.

        Raises:
            RuntimeError: If no production inbounds are found.
        """
        inbounds = await self.inbounds_end.get_all()
        usable_inbounds: list[Inbound] = []
        for inb in inbounds:
            if self.PROD_STRING.lower() in inb.remark.lower():
                usable_inbounds.append(inb)
        if len(usable_inbounds) == 0:
            raise RuntimeError("No production inbounds found! Change prod_string!")

        return usable_inbounds

    async def clear_prod_inbound_cache(self):
        """Clear the production inbound cache.

        This method clears the cache of production inbounds and refills it
        by fetching the inbounds again. It is intended to be run as a
        background task.

        Note:
            This method currently runs every 10 seconds. Please change the
            timer from 5 to 60*60*24 in the code.
        """
        #This is useless for now, but later get_production_inbounds() will be cached,
        # and this will clear the cache every 24 hours or so, to make sure the client
        # always has the most up-to-date inbounds list
        while True:
            print("You're seeing this message because I forgot to remove it in api.update_inbounds() !")
            print("Please change the timer from 5 to 60*60*24!")
            self.get_production_inbounds.cache_clear()
            await self.get_production_inbounds() #fill the cache
            await asyncio.sleep(10)
            #print(stat)

    #========================clients management========================
    async def get_client_with_tgid(self, tgid: int, inbound_id: int | None = None) -> List[ClientStats]:
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
        uuid = util.get_telegram_uuid(tgid)
        resp = await self.clients_end.get_client_with_uuid(uuid)
        return resp

    async def create_and_add_prod_client(self, telegram_id: int, additional_remark: str = None):
        """Create and add a production client.

        This method creates a new client with the given Telegram ID and
        adds it to the production inbounds. The client is configured with
        default settings and the additional remark.

        Args:
            telegram_id: The Telegram ID of the client.
            additional_remark: An optional additional remark for the client.

        Returns:
            List[Response]: A list of responses from the server for each
            inbound the client was added to.
        """
        production_inbounds: List[Inbound] = await self.get_production_inbounds()

        responses = []
        for inb in production_inbounds:
            client = SingleInboundClient.model_construct(
                uuid=util.get_telegram_uuid(telegram_id),
                flow="",
                email=util.generate_email_from_tgid_inbid(telegram_id, inb.id),
                limit_gb=0,
                enable=True,
                subscription_id=util.sub_from_tgid(telegram_id),
                comment=f"{additional_remark}, created at {datetime.now(UTC)}")
            responses.append(await self.clients_end.add_client(client, inb.id))
        return responses

    async def update_client_by_tgid(self, telegram_id: int, inbound_id: int, /,
                                    security: str | None = None,
                                    password: str | None = None,
                                    flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                    limit_ip: int | None = None,
                                    limit_gb: int | None = None,
                                    expiry_time: int | None = None,
                                    enable: bool | None = None,
                                    sub_id: str | None = None,
                                    comment: str | None = None) -> Response:
        """
        Update a client in a specific inbound by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client
            inbound_id: The ID of the inbound where the client exists
            security: Client security setting
            password: Client password
            flow: VLESS flow type
            limit_ip: IP connection limit
            limit_gb: Data limit in GB
            expiry_time: Client expiry time (UNIX timestamp)
            enable: Whether the client is enabled
            sub_id: Subscription ID
            comment: Client comment/note

        Returns:
            Response from the API
        """
        email = util.generate_email_from_tgid_inbid(telegram_id, inbound_id)
        existing_client = await self.clients_end.get_client_with_email(email)

        resp = await self.clients_end.update_single_client(
            SingleInboundClient.model_validate(existing_client.model_dump()),
            inbound_id,
            security=security,
            password=password,
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

    async def delete_client_by_tgid_all_inbounds(self, telegram_id: int) -> List[Response]:
        """Delete a client from all production inbounds by Telegram ID.

        Args:
            telegram_id: The Telegram ID of the client

        Returns:
            List of Response objects from each deletion attempt
        """
        production_inbounds = await self.get_production_inbounds()
        responses = []

        for inbound in production_inbounds:
            email = util.generate_email_from_tgid_inbid(telegram_id, inbound.id)
            resp = await self.clients_end.delete_client_by_email(email, inbound.id)
            responses.append(resp)

        return responses

