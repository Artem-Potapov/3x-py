import json
from linecache import clearcache
from typing import Generic, Type, Literal, LiteralString, Union, List, Dict, TYPE_CHECKING

import requests
from httpx import Response
from pydantic import ValidationError
from pydantic.main import ModelT

import models
from util import camel_to_snake, JsonType
from models import Inbound

from api import XUIClient


class BaseEndpoint(Generic[ModelT]):
    _url: str

    def __init__(self, client: "XUIClient") -> None:
        self.client = client

    async def _get_simple_response(self, caller_endpoint: str) -> JsonType:
        endpoint_url: str = caller_endpoint
        if self._url not in caller_endpoint:
            endpoint_url = f"{self._url}{caller_endpoint}"
        resp = await self.client.safe_get(endpoint_url)
        if resp.status_code == 200:
            resp_json = resp.json()
            return resp_json["obj"]
        else:
            raise RuntimeError(f"Error: wrong status code {resp.status_code}")

class Server(BaseEndpoint):
    _url = "panel/api/server"

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
    _url = "panel/api/inbounds"

    async def get_all(self) -> List[Inbound]:
        endpoint = "/list"
        json = await self._get_simple_response(f"{endpoint}")
        inbounds = Inbound.from_list(json, client=self.client)
        return inbounds


    async def get_specific_inbound(self, id) -> Inbound:
        endpoint = f"/get/{id}"
        pass
        # no use for this yet...




class Clients(BaseEndpoint):
    _url = "panel/api/inbounds"
    #although it's the same url, they should be differentiated

    async def get_client_with_email(self, email) -> models.ClientStats:
        endpoint = f"/getClientTraffics/{email}"
        resp = await self._get_simple_response(endpoint)
        return models.ClientStats.model_validate_json(str(resp))

    async def get_client_with_uuid(self, uuid) -> List[models.ClientStats]:
        endpoint = f"/getClientTrafficsById/{uuid}"
        resp = await self._get_simple_response(endpoint)
        client_stats = models.ClientStats.from_list(resp, client=self.client)
        return client_stats


    async def add_client(self, client: models.InboundClients | models.SingleInboundClient | Dict,
                         inbound_id: int|None=None) -> Response:
        endpoint = f"/addClient"
        if isinstance(client, Dict):
            try:
                client = str(client)
                final = models.InboundClients.model_validate_json(client)
            except ValidationError:
                # if there is in fact an error, I want it to raise
                tmp = models.SingleInboundClient.model_validate_json(client)
                if inbound_id:
                    final = models.InboundClients(id=inbound_id,
                                                  settings=models.InboundClients.Settings(clients=[tmp]))
                else:
                    raise ValueError("A single client was provided to be added but no parent inbound id")
        elif isinstance(client, models.SingleInboundClient):
            final = models.InboundClients(id=inbound_id,
                                          settings=models.InboundClients.Settings(clients=[client]))
        elif isinstance(client, models.InboundClients):
            final = client
            if inbound_id:
                final.parent_id = inbound_id
        else:
            raise TypeError
        # send request
        print(type(final))
        print(final)
        data = final.model_dump(by_alias=True)
        print(type(data))
        print(json.dumps(data))
        print(f"{self._url}{endpoint}")
        resp = await self.client.safe_post(f"{self._url}{endpoint}", data=data)

        #YOU NEED TO PASS SETTINGS AS A STRING, NOT AS A DICT, YOU FUCKING DUMBASS!
        print(resp)
        print(resp.json())

        # if not resp.json()["success"]:
        #     print("Error while creating a client")
        #     print(resp.json()["msg"])
        # return resp

    async def _request_update_client(self, client: models.InboundClients | models.SingleInboundClient,
                                     inbound_id: int|None=None,
                                     *, original_uuid: str|None=None) -> Response:
        if isinstance(client, models.SingleInboundClient):
            if inbound_id is None:
                raise ValueError("Provide a parent inbound ID or pass models.InboundClients")
            client = models.InboundClients(parent_id=inbound_id,
                                           settings=models.InboundClients.Settings(clients=[client]))
        else:
            if len(client.settings.clients) != 1:
                raise ValueError(f"You can only update 1 client at a time, instead got {len(client.settings.clients)}")

        _endpoint = f"updateClient/{original_uuid if original_uuid else client.settings.clients[0].uuid}"
        resp = await self.client.safe_post(f"{self._url}{_endpoint}", json=client.model_dump_json())

        return resp

    async def update_single_client(self, existing_client: SingleInboundClient, inbound_id: int, /, *,
                                   security: str | None = None,
                                   password: str | None = None,
                                   flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                   email: str | None = None,
                                   limit_ip: int | None = None,
                                   limit_gb: int | None = None,
                                   expiry_time: models.timestamp | None = None,
                                   enable: bool | None = None,
                                   sub_id: str | None = None,
                                   comment: str | None = None,
                                   ):
        # Collect only the arguments that were explicitly provided (not None)
        changes = {k: v for k, v in locals().items()
                   if k != 'self' and k != 'existing_client' and v is not None}
        # Rename sub_id to subscription_id if needed
        if 'sub_id' in changes:
            changes['subscription_id'] = changes.pop('sub_id')
        changes["updated_at"] = int(datetime.now(UTC).timestamp())
        updated = existing_client.model_copy(update=changes)

        resp = await self._request_update_client(updated, inbound_id)
        return resp


    async def delete_expired_clients(self, inbound_id: int) -> Response:
        _endpoint = f"delDepletedClients/"
        resp = await self.client.safe_post(f"{self._url}{_endpoint}{inbound_id}")
        return resp

# a = models.InboundClients.model_validate_json('''{"id": 3, "settings": {"clients": [{ "id": "0213c327-c619-4998-9bb3-adaced38c68b", "flow": "", "email": "penis", "limitIp": 0, "totalGB": 0, "expiryTime": 0, "enable": true, "tgId": "", "subId": "86xi6py5uwsgokh1", "comment": "", "reset": 0 }, { "id": "02333327-c619-4998-9bb3-adaced38c68b", "flow": "", "email": "chipichdwaadwhapachapa", "limitIp": 0, "totalGB": 0, "expiryTime": 0, "enable": true, "tgId": "", "subId": "86xi6ddduwsgokh1", "comment": "", "reset": 0 }]}}''')
# print(a)
# client = a.settings.clients[0]