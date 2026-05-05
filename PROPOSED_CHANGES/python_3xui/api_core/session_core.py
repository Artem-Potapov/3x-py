"""HTTP session, credentials, TOTP, and retry-with-relogin policy for the panel API."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from logging import DEBUG
from typing import Any, Literal, Self, Tuple, Type, Union, overload

import httpx
import pyotp
from httpx import AsyncClient, Request, Response
from pydantic import SecretStr

from python_3xui import util
from python_3xui.util import JsonType, async_range

DataType: Type[str | bytes | Iterable[bytes] | AsyncIterable[bytes]] = Union[
    str, bytes, Iterable[bytes], AsyncIterable[bytes]
]
PrimitiveData = Union[str, int, float, bool] | None
ParamType = Union[
    Mapping[str, Union[PrimitiveData, Sequence[PrimitiveData]]],
    list[Tuple[str, PrimitiveData]],
    tuple[Tuple[str, PrimitiveData], ...],
    str,
    bytes,
]
CookieType = Union[dict[str, str], list[tuple[str, str]]]
HeaderType = Union[
    Mapping[str, str],
    Mapping[bytes, bytes],
    Sequence[tuple[str, str]],
    Sequence[tuple[bytes, bytes]],
]


class SessionCore:
    """Owns HTTP session, credentials, TOTP, and the retry-with-relogin policy.

    Single object that talks to the panel. Endpoint classes receive a
    SessionCore (not the full XUIClient) and call ``safe_get`` / ``safe_post``
    on it. The 404-with-expired-session branch in ``_safe_request`` calls
    ``self.login()``, so transport and auth must live together.
    """

    def __init__(self, base_website: str, base_port: int, base_path: str,
                 *, username: str | None = None, password: str | None = None,
                 two_fac_code: str | None = None, session_duration: int = 3600,
                 max_retries: int = 5, retry_delay: int = 1, panel_id: Any = None,
                 ) -> None:
        self.connected: bool = False
        self.session: AsyncClient | None = None
        self.base_host: str = base_website
        self.base_port: int = base_port
        self.base_path: str = base_path
        self.base_url: str = f"https://{self.base_host}:{self.base_port}{self.base_path}"
        self.session_start: float | None = None
        self.session_duration: int = session_duration
        self.xui_username: str | None = username
        self.xui_password: str | None = password
        self.two_fac_secret: SecretStr | None = (
            SecretStr(two_fac_code) if two_fac_code is not None else None
        )
        self.totp: pyotp.TOTP | None = None
        self.max_retries: int = max_retries
        self.retry_delay: int = retry_delay
        self.panel_id = panel_id
        if self.two_fac_secret:
            if len(self.two_fac_secret.get_secret_value()) <= 8:
                print(
                    "WARNING: You seem to have entered a 2FA **code**, not a 2FA secret."
                    "Although entering the secret is dangerous, there is no other way to provide a consistent way"
                    "for continuous login. This code will only work for this specific login."
                )
                self.totp = None
            else:
                self.totp = pyotp.TOTP(self.two_fac_secret.get_secret_value())

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
            raise ValueError(
                "Provide either a prebuilt request or arguments to build one."
            )
        if "request_to_send" not in kwargs:
            if method is None:
                raise ValueError(
                    "If there's no prebuilt request, you must provide a method."
                )

        url = (
            kwargs["url"]
            if "url" in kwargs.keys()
            else kwargs["request_to_send"].url
        )
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
        if __debug__:
            logging.info(
                "Safe %s is running to %s%s\nJSON Payload: %s",
                method,
                str(self.session.base_url),
                str(url),
                json.dumps(json_payload) if json_payload is not None else "(no payload)",
            )
        async for attempt in async_range(self.max_retries):
            if "request_to_send" in kwargs:
                _request: Request = kwargs["request_to_send"]
                resp = await self.session.send(_request)
            else:
                # noinspection PyTypeChecker
                resp = await self.session.request(method, **kwargs)
            if resp.status_code // 100 != 2:  # because it can return either 201 or 202
                if resp.status_code == 404:
                    now: float = datetime.now(UTC).timestamp()
                    if (
                            self.session_start is None
                            or now - self.session_start > self.session_duration
                    ):
                        logging.info(
                            "Client (panel: %s) is not logged in, logging in...",
                            self.panel_id or self.base_host,
                        )
                        await self.login()
                        continue
                    else:
                        logging.error(
                            "Server returned a status code of %s with a valid session",
                            resp.status_code,
                        )
                        raise RuntimeError(
                            "Server returned a 404, and the session should still be valid, likely it's a REAL 404"
                        )
                else:
                    logging.error(
                        "Server returned a status code of %s", resp.status_code
                    )
                    resp.raise_for_status()

            status = await util.check_xui_response(resp)
            if status == "OK":
                return resp
            if status == "DB_LOCKED":
                if attempt + 1 >= self.max_retries:
                    raise RuntimeError("Too many retries")
                await asyncio.sleep(self.retry_delay)
                continue
            logging.error(
                "A %s request was unsuccessful (code 200, but success=false).\nPayload: %s",
                method,
                json.dumps(resp.json()),
            )
            return resp
        raise RuntimeError(
            f"For some reason safe_request didn't exit, dump:\nmethod:\n{method}\n{kwargs}"
        )

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
        if self.session is None:
            raise RuntimeError("Session is not initialized")

        return await self._safe_request(
            method="get",
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
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
        if self.session is None:
            raise RuntimeError("Session is not initialized")

        return await self._safe_request(
            method="post",
            url=url,
            content=content,
            data=data,
            json=json,
            params=params,
            headers=headers,
            cookies=cookies,
        )

    async def login(self) -> None:
        """Authenticate with the 3X-UI panel."""
        payload = {
            "username": self.xui_username,
            "password": self.xui_password,
        }
        if self.totp:
            if (
                    self.totp.interval - datetime.now().timestamp() % self.totp.interval
                    < 3
            ):
                await asyncio.sleep(3.1)  # just to not submit an invalid code
            payload["twoFactorCode"] = self.totp.now()
        elif self.two_fac_secret:
            payload["twoFactorCode"] = self.two_fac_secret.get_secret_value()

        logging.info(
            "Client is logging in (panel: %s)", self.panel_id or self.base_host
        )
        resp = await self.session.post("/login", data=payload)
        if resp.status_code == 200:
            resp_json = resp.json()
            if "success" not in resp_json:
                raise RuntimeError(
                    f"Error: server returned a status code of {resp.status_code} but the response is not valid: {resp_json}"
                )
            if not resp_json["success"]:
                raise ValueError(
                    "Error: wrong credentials (including status code) or failed login."
                )
            self.session_start = datetime.now(UTC).timestamp()
            return
        raise RuntimeError(f"Error: server returned a status code of {resp.status_code}")

    def connect(self) -> Self:
        """Create an async HTTP client session."""
        logging.log(
            DEBUG, "Client connected (panel: %s)", self.panel_id or self.base_url
        )
        self.session = AsyncClient(base_url=self.base_url)
        self.connected = True
        return self

    async def disconnect(self) -> None:
        """Close the HTTP session only (no cache teardown)."""
        self.connected = False
        if self.session is not None:
            await self.session.aclose()
