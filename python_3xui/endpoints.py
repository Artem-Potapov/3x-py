import json
from datetime import datetime, UTC
from typing import Generic, Literal, List, Dict

from httpx import Response
from pydantic import ValidationError
from pydantic.main import ModelT

from . import models
from .api import XUIClient
from .models import Inbound, SingleInboundClient
from .util import JsonType


class BaseEndpoint(Generic[ModelT]):
    """Base class for API endpoint handlers.

    Provides common functionality for making API requests to the 3X-UI panel.

    Attributes:
        _url: The base URL path for this endpoint group.
        client: Reference to the XUIClient instance.
    """
    _url: str

    def __init__(self, client: "XUIClient") -> None:
        self.client = client

    async def _simple_get(self, caller_endpoint: str) -> JsonType:
        """Perform a simple GET request and return the response object.

        Args:
            caller_endpoint: The endpoint path to request. If it doesn't start
                with the base URL, the base URL will be prepended.

        Returns:
            The 'obj' field from the JSON response.

        Raises:
            RuntimeError: If the response status code is not 200.
        """
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
    """Handler for server-related API endpoints.

    Provides methods for generating cryptographic keys and UUIDs.

    Endpoints:
        - /panel/api/server/getNewUUID
        - /panel/api/server/getNewX25519Cert
        - /panel/api/server/getNewmldsa65
        - /panel/api/server/getNewmlkem768x
    """
    _url = "panel/api/server"

    async def new_uuid(self) -> str:
        """Generate a new UUID from the server.

        Returns:
            A new UUID string.
        """
        endpoint = "/getNewUUID"
        resp_json = await self._simple_get(endpoint)
        return resp_json["uuid"]

    async def new_x25519(self) -> dict[Literal["privateKey", "publicKey"], str]:
        """Generate a new X25519 key pair.

        Returns:
            A dictionary containing 'privateKey' and 'publicKey' strings.
        """
        endpoint = "/getNewX25519Cert"
        resp_json = await self._simple_get(endpoint)
        return resp_json

    async def new_mldsa65(self) -> dict[Literal["verify", "seed"], str]:
        """Generate a new ML-DSA-65 post-quantum key pair.

        ML-DSA-65 is a post-quantum signature algorithm.

        Returns:
            A dictionary containing 'verify' (public key) and 'seed' values.
        """
        endpoint = "/getNewmldsa65"
        resp_json = await self._simple_get(endpoint)
        return resp_json

    async def new_mlkem768(self) -> dict[Literal["client", "seed"], str]:
        """Generate a new ML-KEM-768 post-quantum key pair.

        ML-KEM-768 is a post-quantum key encapsulation mechanism.

        Returns:
            A dictionary containing 'client' and 'seed' values.
        """
        endpoint = "/getNewmlkem768x"
        resp_json = await self._simple_get(endpoint)
        return resp_json


class Inbounds(BaseEndpoint):
    """Handler for inbound-related API endpoints.

    Provides methods for retrieving inbound configurations.

    Endpoints:
        - /panel/api/inbounds/list
        - /panel/api/inbounds/get/{id}
    """
    _url = "panel/api/inbounds"

    async def get_all(self) -> List[Inbound]:
        """Retrieve all inbounds from the server.

        Returns:
            A list of Inbound model instances.
        """
        endpoint = "/list"
        json = await self._simple_get(f"{endpoint}")
        inbounds = Inbound.from_list(json, client=self.client)
        return inbounds

    async def get_specific_inbound(self, id) -> Inbound:
        """Retrieve a specific inbound by ID.

        Args:
            id: The ID of the inbound to retrieve.

        Returns:
            An Inbound model instance for the specified ID.
        """
        endpoint = f"/get/{id}"
        json = await self._simple_get(f"{endpoint}")
        inbound = Inbound(client=self.client, **json)
        return inbound


class Clients(BaseEndpoint):
    """Handler for client-related API endpoints.

    Provides methods for retrieving, adding, updating, and deleting clients.

    Endpoints:
        - /panel/api/inbounds/getClientTraffics/{email}
        - /panel/api/inbounds/getClientTrafficsById/{uuid}
        - /panel/api/inbounds/addClient
        - /panel/api/inbounds/updateClient/{uuid}
        - /panel/api/inbounds/delDepletedClients/{inbound_id}
        - /panel/api/inbounds/{inbound_id}/delClient/{email|uuid}
    """
    _url = "panel/api/inbounds/"

    #although it's the same url, they should be differentiated

    async def get_client_with_email(self, email: str) -> models.ClientStats:
        """Retrieve client statistics by email.

        Args:
            email: The client's email identifier.

        Returns:
            A ClientStats model instance with the client's statistics.
        """
        endpoint = f"getClientTraffics/{email}"
        resp = await self._simple_get(endpoint)
        return models.ClientStats.model_validate(resp)

    async def get_client_with_uuid(self, uuid: str) -> List[models.ClientStats]:
        """Retrieve client statistics by UUID.

        Args:
            uuid: The client's unique identifier.

        Returns:
            A list of ClientStats model instances matching the UUID.
        """
        endpoint = f"getClientTrafficsById/{uuid}"
        resp = await self._simple_get(endpoint)
        client_stats = models.ClientStats.from_list(resp, client=self.client)
        return client_stats


    async def add_client(self, client: models.InboundClients | models.SingleInboundClient | Dict,
                         inbound_id: int | None = None) -> Response:
        """Add a new client to an inbound.

        Args:
            client: The client to add. Can be:
                - A dict (will be parsed as JSON)
                - A SingleInboundClient (requires inbound_id)
                - An InboundClients object
            inbound_id: The ID of the inbound to add the client to.
                Required if client is a SingleInboundClient.

        Returns:
            The HTTP response from the API.

        Raises:
            ValueError: If a single client is provided without an inbound_id.
            TypeError: If the client type is not supported.
        """
        endpoint = f"addClient"
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
        return resp

    async def _request_update_client(self, client: models.InboundClients | models.SingleInboundClient,
                                     inbound_id: int | None = None,
                                     *, original_uuid: str | None = None) -> Response:
        """Request to update an existing client.

        Args:
            client: The client data to update. Can be:
                - A SingleInboundClient (requires inbound_id)
                - An InboundClients object (with one client)
            inbound_id: The ID of the inbound the client belongs to.
                Required if client is a SingleInboundClient.
            original_uuid: The original UUID of the client to update.
                Required if client is a SingleInboundClient.

        Returns:
            The HTTP response from the API.
        """
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
        """Update an existing client's details.

        Args:
            existing_client: The existing client object to update.
            inbound_id: The ID of the inbound the client belongs to.
            security: New security settings (optional).
            password: New password (optional).
            flow: New flow settings (optional).
            email: New email address (optional).
            limit_ip: New IP limit (optional).
            limit_gb: New GB limit (optional).
            expiry_time: New expiry time (optional).
            enable: New enable status (optional).
            sub_id: New subscription ID (optional).
            comment: New comment (optional).

        Returns:
            The HTTP response from the API.
        """
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
        """Delete expired clients from an inbound.

        Args:
            inbound_id: The ID of the inbound to delete expired clients from.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"delDepletedClients/"
        resp = await self.client.safe_post(f"{self._url}{_endpoint}{inbound_id}")
        return resp

    async def delete_client_by_email(self, email: str, inbound_id: int) -> Response:
        """Delete a client by email.

        Args:
            email: The email of the client to delete.
            inbound_id: The ID of the inbound the client belongs to.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"{inbound_id}/delClient/{email}"
        resp = await self.client.safe_post(f"{self._url}{_endpoint}")
        return resp

    async def delete_client_by_uuid(self, uuid: str, inbound_id: int) -> Response:
        """Delete a client by UUID.

        Args:
            uuid: The UUID of the client to delete.
            inbound_id: The ID of the inbound the client belongs to.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"{inbound_id}/delClient/{uuid}"
        resp = await self.client.safe_post(f"{self._url}{_endpoint}")
        return resp
