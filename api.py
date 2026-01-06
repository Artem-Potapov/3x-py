import asyncio
import datetime
import json
import logging
import subprocess
from collections.abc import Sequence, Mapping
from logging import DEBUG
from typing import Self, Optional, Dict, Iterable, AsyncIterable, TypeAlias, Type, Union, Any, List, Tuple, Literal

import httpx
from httpx import Response, AsyncClient
from requests import session

import util
from util import JsonType, async_range

DataType: Type[str|bytes|Iterable[bytes]|AsyncIterable[bytes]] = Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]]
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
    _instance = None

    def __init__(self, base_website:str, base_port: int, base_path: str,
                 *, xui_username: str|None=None, xui_password: str|None=None,
                 two_fac_code: str|None=None, session_duration: int=3600) -> None:
        self.session: AsyncClient | None = None
        self.base_host: str = base_website
        self.base_port: int = base_port
        self.base_path: str = base_path
        self.base_url: str = f"https://{self.base_host}:{self.base_port}{self.base_path}"
        self.session_start: float|None = None
        self.session_duration: int = session_duration
        self.xui_username: str|None = xui_username
        self.xui_password: str|None = xui_password
        self.two_fac_code: str|None = two_fac_code
        self.max_retries: int = 5
        self.retry_delay: int = 1

    def __new__(cls, *args, **kwargs):
        print("initializing client")
        if cls._instance is None:
            print("nu instance")
            cls._instance = super(XUIClient, cls).__new__(cls)
        return cls._instance

    async def _safe_request(self,
                            method: Literal["get", "post", "patch", "delete", "put"],
                            **kwargs) -> Response:
        async for attempt in async_range(self.max_retries):
            resp = await self.session.request(method=method, **kwargs)
            if resp.status_code // 100 != 2: #because it can return either 201 or 202
                if resp.status_code == 404:
                    now: float = datetime.datetime.now().timestamp()
                    if self.session_start is None or now - self.session_start > self.session_duration:
                        await self.login()
                        continue
                    else:
                        raise RuntimeError("Server returned a 404, and the session should still be valid")
                else:
                    raise RuntimeError(f"Wrong status code: {resp.status_code}")

            status = util.check_xui_response_validity(resp)
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

    async def login(self, username: str|None = None, password: str|None = None,
                    two_fac_code: str|None = None) -> None:
        if self.xui_username and username:
            self.xui_username = username
        if self.xui_password and password:
            self.xui_password = password
        if self.two_fac_code and two_fac_code:
            self.two_fac_code = two_fac_code

        payload = {
            "username": self.xui_username,
            "password": self.xui_password,
        }
        if two_fac_code is not None:
            payload["twoFactorCode"] = self.two_fac_code

        resp = await self.session.post("/login", data=payload)
        resp_json = resp.json()
        if resp.status_code == 200:
            if resp_json["success"]:
                self.session_start: float = (datetime.datetime.now().timestamp())
                return
            else:
                raise ValueError("Error: wrong credentials or failed login")
        else:
            raise RuntimeError(f"Error: server returned a status code of {resp.status_code}")

    def connect(self) -> Self:
        self.session = AsyncClient(base_url=self.base_url)
        return self

    async def disconnect(self) -> None:
        await self.session.aclose()

    async def __aenter__(self) -> Self:
        self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
        return
