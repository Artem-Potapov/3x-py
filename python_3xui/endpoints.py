import json
import logging
from datetime import datetime, UTC
from typing import Generic, Literal, List, Dict

from httpx import Response
from pydantic import ValidationError
from pydantic.main import ModelT

from .api import XUIClient
from .custom_exceptions import ClientDoesNotExistError
from .models import Inbound, SingleInboundClient, ClientStats, InboundClients, timestamp_seconds, ClientsSettings
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
        json_resp = await self._simple_get(f"{endpoint}")
        inbounds = Inbound.from_list(json_resp)
        return inbounds

    async def get_specific_inbound(self, inbound_id) -> Inbound:
        """Retrieve a specific inbound by ID.

        Args:
            inbound_id: The ID of the inbound to retrieve.

        Returns:
            An Inbound model instance for the specified ID.
        """
        endpoint = f"/get/{inbound_id}"
        json = await self._simple_get(f"{endpoint}")
        inbound = Inbound(**json)
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

    async def get_client_with_email(self, email: str) -> ClientStats:
        """Retrieve client statistics by email.

        Args:
            email: The client's email identifier.

        Returns:
            A ClientStats model instance with the client's statistics.
        """
        endpoint = f"getClientTraffics/{email}"
        resp = await self._simple_get(endpoint)
        return ClientStats.model_validate(resp)

    async def get_client_with_uuid(self, uuid: str) -> List[ClientStats]:
        """Retrieve client statistics by UUID.

        Args:
            uuid: The client's unique identifier.

        Returns:
            A list of ClientStats model instances matching the UUID.
        """
        endpoint = f"getClientTrafficsById/{uuid}"
        resp = await self._simple_get(endpoint)
        client_stats = ClientStats.from_list(resp)
        return client_stats

    async def add_client(self, client: InboundClients | SingleInboundClient | Dict,
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
                final = InboundClients.model_validate(client)
            except ValidationError:
                # Check the SingleInboundClient now...
                tmp = SingleInboundClient.model_validate(client)
                if inbound_id:
                    final = InboundClients(id=inbound_id,
                                           settings=ClientsSettings(clients=[tmp]))
                else:
                    raise ValueError("A single client was provided to be added but no parent inbound id")
        elif isinstance(client, SingleInboundClient):
            final = InboundClients(id=inbound_id,
                                   settings=ClientsSettings(clients=[client]))
        elif isinstance(client, InboundClients):
            final = client
            if inbound_id:
                final.parent_id = inbound_id
        else:
            raise TypeError
        # send request
        data = json.loads(final.model_dump_json(by_alias=True))
        resp = await self.client.safe_post(f"{self._url}{endpoint}", json=data)
        #YOU NEED TO PASS SETTINGS AS A STRING, NOT AS A DICT, YOU IDIOT!
        return resp

    async def _request_update_client(self, client: InboundClients | SingleInboundClient,
                                     inbound_id: int | None = None,
                                     *, original_uuid: str | None = None) -> Response:
        """Request to update an existing client.

        Args:
            client: The client data to update. Can be:
                - A ClientUpdatePayload - Recommended (requires inbound_id)
                - A SingleInboundClient (requires inbound_id)
                - An InboundClients object (with one client)
            inbound_id: The ID of the inbound the client belongs to.
                Required if client is a SingleInboundClient or ClientUpdatePayload.
            original_uuid: The original UUID of the client to update.
                Required if client is a SingleInboundClient or ClientUpdatePayload.

        Returns:
            The HTTP response from the API.
        """
        if isinstance(client, SingleInboundClient):
            client = InboundClients(id=inbound_id, settings=ClientsSettings(clients=[client]))
        _endpoint = f"updateClient/{original_uuid if original_uuid else client.settings.clients[0].uuid}"
        #we have to do this because if we do model.dump() it will return a Settings **OBJECT** which we DON'T want.
        resp = await self.client.safe_post(f"{self._url}{_endpoint}",
                                           json=json.loads(client.model_dump_json(exclude_none=True, by_alias=True)))
        return resp

    async def _find_client_in_inbound(self, client_uuid: str, inbound_id: int) -> SingleInboundClient|None:
        prod_inbs = await self.client.get_production_inbounds() #check production first since they're all cached
        prod_inb_index = None
        for i, prod_inb in enumerate(prod_inbs):  # see if inbound is production
            if inbound_id == prod_inb.id:
                prod_inb_index = i

        if prod_inb_index is not None:
            needed_inb: Inbound = prod_inbs[prod_inb_index]
            for client in needed_inb.settings.clients:
                if client.uuid == client_uuid:
                    return client
            self.client.get_production_inbounds.cache_clear() # this means client is in a prod inbound but it's not refreshed

        inb = await self.client.inbounds_end.get_specific_inbound(inbound_id)
        for client in inb.settings.clients:
            if client.uuid == client_uuid:
                return client
        return None

    async def update_single_client(self, inbound_id: int, client_uuid: str, *,
                                   security: str | None = None,
                                   password: str | None = None,
                                   flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                   email: str | None = None,
                                   limit_ip: int | None = None,
                                   limit_gb: int | None = None,
                                   expiry_time: timestamp_seconds | None = None,
                                   enable: bool | None = None,
                                   sub_id: str | None = None,
                                   comment: str | None = None,
                                   ) -> Response:
        """Update an existing client's details.

        Args:
            client_uuid: The UUID of the original client.
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
                   if k not in ("self", "inbound_id", "client_uuid", "changes") and v is not None}
        # Rename sub_id to subscription_id if needed
        if 'sub_id' in changes:
            changes['subscription_id'] = changes.pop('sub_id')

        found_inbound = await self._find_client_in_inbound(client_uuid, inbound_id)
        if not found_inbound:
            raise ClientDoesNotExistError(f"The target inbound was checked but client {client_uuid} was not found.")

        changes["updated_at"] = int(datetime.now(UTC).timestamp())
        updated = found_inbound.model_copy(update=changes)
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
        _endpoint = f"{inbound_id}/delClientByEmail/{email}"
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
