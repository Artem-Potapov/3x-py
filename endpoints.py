from typing import Generic, Type, Literal, LiteralString

from httpx import Response
from pydantic.main import ModelT

import models
from api import XUIClient
from util import camel_to_snake
from models import Inbound


class BaseEndpoint(Generic[ModelT]):
    _url: str

    def __init__(self, client: "XUIClient") -> None:
        self.client = client

class Server(BaseEndpoint):
    _url = "/panel/api/server"

    async def _get_simple_response(self, caller_endpoint: str):
        resp = await self.client.safe_get(f"{self._url}{caller_endpoint}")
        if resp.status_code == 200:
            resp_json = resp.json()["obj"]
            return resp_json
        elif resp.status_code == 518:
            raise RuntimeError("Error: too many retries")
        else:
            raise RuntimeError(f"Error: wrong status code {resp.status_code}")


    async def new_uuid(self) -> str:
        endpoint = "/getNewUUID"
        resp_json = await self._get_simple_response(endpoint)
        return resp_json["uuid"]

    async def new_x25519(self) -> dict[Literal["privateKey", "publicKey"], str]:
        endpoint = "/getNewX25519Cert"
        resp_json = await self._get_simple_response(endpoint)
        return resp_json

    async def new_mldsa65(self) -> dict[Literal["verify", "seed"], str]:
        endpoint = "/getNewmldsa65"
        resp_json = await self._get_simple_response(endpoint)
        return resp_json

    async def new_mlkem768(self) -> dict[Literal["client", "seed"], str]:
        endpoint = "/getNewmlkem768x"
        resp_json = await self._get_simple_response(endpoint)
        return resp_json




class Inbounds(BaseEndpoint):
    _url = "/panel/api/inbounds"

    async def get_all(self):
        endpoint = "/list"

    async def get_specific(self, id):
        endpoint = f"/get/{id}"

    async def get_client_with_email(self, email):
        endpoint = f"/getClientTraffics/{email}"

    async def get_client_with_uuid(self, uuid):
        endpoint = f"/getClientTrafficsById/{uuid}"

    async def add_client(self, client: models.InboundClients|models.SingleInboundClient):
        endpoint = f"/inbounds/addClient/"

