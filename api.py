import datetime
import logging
from typing import Self, Optional

from httpx import Response, AsyncClient
from requests import session


class XUIClient:
    _instance = None

    def __init__(self, base_host:str, base_port: int, base_path: str,
                 *, xui_username: str|None=None, xui_password: str|None=None,
                 two_fac_code: str|None=None, session_duration: int=3600) -> None:
        self.session: AsyncClient | None = None
        self.base_host: str = base_host
        self.base_port: int = base_port
        self.base_path: str = base_path
        self.base_url: str = f"https://{self.base_host}:{self.base_port}/{self.base_path}"
        self.session_start: float|None = None
        self.session_duration: int = session_duration
        self.xui_username: str|None = xui_username
        self.xui_password: str|None = xui_password
        self.two_fac_code: str|None = two_fac_code

    def __new__(cls, *args, **kwargs):
        print("initializing client")
        if cls._instance is None:
            print("nu instance")
            cls._instance = super(XUIClient, cls).__new__(cls)
        return cls._instance

    async def login(self, username: str|None = None, password: str|None = None,
                    two_fac_code: str|None = None) -> None:
        if self.xui_username and username:
            raise ValueError("You must provide a username either when initing XUI or to the function, not both")
        if self.xui_password and password:
            raise ValueError("You must provide a password either when initing XUI or to the function, not both")
        if self.two_fac_code and two_fac_code:
            raise ValueError("You must provide a 2fa code either when initing XUI or to the function, not both")



        payload = {
            "username": username,
            "password": password,
        }
        if two_fac_code is not None:
            payload["twoFactorCode"] = two_fac_code

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

    async def db_safe_get(self, url: str, **kwargs):
        # Automatic retry if GET request returns database locked error
        resp: Response = await self.session.get(url=url, **kwargs)
        if resp.status_code == 200:
            ...
        elif resp.status_code == 404:
            # 3x-ui returns a 404 code if you're not logged in, for obfuscation
            now: float = datetime.datetime.now().timestamp()
            if now - self.session_start > self.session_duration:
                await self.login()
        else:
            logging.ERROR("Server returned a code of %d", resp.status_code)

    async def __aenter__(self) -> Self:
        self.session = AsyncClient(base_url=self.base_url)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.session.aclose()
        return

a = XUIClient("12", 12, "23")
print(a)
print(a.__dict__)
b = XUIClient("12", 12, "34")
print(b)
print(b.__dict__)