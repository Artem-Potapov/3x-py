from linecache import clearcache
from typing import Generic, Type, Literal, LiteralString, Union, List, Dict

from httpx import Response
from pydantic import ValidationError
from pydantic.main import ModelT

import models
from api import XUIClient
from util import camel_to_snake, JsonType
from models import Inbound


class BaseEndpoint(Generic[ModelT]):
    _url: str

    def __init__(self, client: "XUIClient") -> None:
        self.client = client

    async def _get_simple_response(self, caller_endpoint: str) -> JsonType:
        resp = await self.client.safe_get(f"{self._url}{caller_endpoint}")
        if resp.status_code == 200:
            resp_json = resp.json()["obj"]
            return resp_json
        elif resp.status_code == 518:
            raise RuntimeError("Error: too many retries")
        else:
            raise RuntimeError(f"Error: wrong status code {resp.status_code}")

class Server(BaseEndpoint):
    _url = "/panel/api/server"

    async def new_uuid(self) -> str:
        endpoint = "/getNewUUID"
        resp_json = await self._get_simple_response(endpoint)
        return resp_json["uuid"]

    async def new_telegram_uuid(self, telegram_id) -> str:
        zeros = 12 - len(telegram_id)
        return f"11111111-1111-1111-1111-{zeros*'0'}{telegram_id}"

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

    async def get_all(self) -> List[Inbound]:
        endpoint = "/list"
        pass
        # no use for this yet...

    async def get_specific(self, id) -> Inbound:
        endpoint = f"/get/{id}"
        pass
        # no use for this yet...




class Clients(BaseEndpoint):
    _url = "/panel/api/inbounds"
    #although it's the same url, they should be differentiated

    async def get_client_with_email(self, email):
        endpoint = f"/getClientTraffics/{email}"
        #kinda pointless...

    async def get_client_with_uuid(self, uuid) -> List[models.ClientStats]:
        endpoint = f"/getClientTrafficsById/{uuid}"
        resp = await self._get_simple_response(endpoint)
        client_stats = models.ClientStats.from_list(resp, client=self.client)
        return client_stats


    async def add_client(self, client: models.InboundClients | models.SingleInboundClient | Dict,
                         inbound_id: int|None=None) -> Response:
        endpoint = f"/inbounds/addClient/"
        if isinstance(client, Dict):
            try:
                client = str(client)
                final = models.InboundClients.model_validate_json(client)
            except ValidationError:
                # if there is in fact an error, I want it to raise
                tmp = models.SingleInboundClient.model_validate_json(client)
                if inbound_id:
                    final = models.InboundClients(parent_id=inbound_id,
                                                  settings=models.InboundClients.Settings(clients=[tmp]))
                else:
                    raise ValueError("A single client was provided to be added but no parent inbound id")
        elif isinstance(client, models.SingleInboundClient):
            final = models.InboundClients(parent_id=inbound_id,
                                          settings=models.InboundClients.Settings(clients=[client]))
        elif isinstance(client, models.InboundClients):
            final = client
        else:
            raise TypeError
        # send request
        data = final.model_dump(by_alias=True)
        resp = await self.client.safe_post(f"{self._url}{endpoint}", data=data)
        return resp



a = models.InboundClients.model_validate_json('''{"id": 3, "settings": {"clients": [{ "id": "0213c327-c619-4998-9bb3-adaced38c68b", "flow": "", "email": "chipichipichapachapa", "limitIp": 0, "totalGB": 0, "expiryTime": 0, "enable": true, "tgId": "", "subId": "86xi6py5uwsgokh1", "comment": "", "reset": 0 }, { "id": "02333327-c619-4998-9bb3-adaced38c68b", "flow": "", "email": "chipichdwaadwhapachapa", "limitIp": 0, "totalGB": 0, "expiryTime": 0, "enable": true, "tgId": "", "subId": "86xi6ddduwsgokh1", "comment": "", "reset": 0 }]}}''')
print(a)