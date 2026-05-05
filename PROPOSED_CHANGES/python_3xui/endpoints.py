from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Generic, Literal, Dict, TypeVar, TYPE_CHECKING

from httpx import Response
from pydantic import ValidationError, BaseModel

from .custom_exceptions import ClientDoesNotExistError

if TYPE_CHECKING:
    from python_3xui.api_core import SessionCore
from .models import Inbound, SingleInboundClient, ClientStats, InboundClients, timestamp_seconds, ClientsSettings
from .util import JsonType

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseEndpoint(Generic[ModelT]):
    """Base class for API endpoint handlers.

    Provides common functionality for making API requests to the 3X-UI panel.

    Attributes:
        _url: The base URL path for this endpoint group.
        _core: Reference to the SessionCore instance.
    """
    _url: str

    def __init__(self, core: SessionCore) -> None:
        self._core = core

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
        resp = await self._core.safe_get(endpoint_url)
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

    Provides methods for retrieving, creating, and deleting inbound configurations.

    Endpoints:
        - /panel/api/inbounds/list
        - /panel/api/inbounds/get/{id}
        - /panel/api/inbounds/add
        - /panel/api/inbounds/del/{inboundId}
    """
    _url = "panel/api/inbounds"

    async def get_all(self) -> list[Inbound]:
        """Retrieve all inbounds from the server.

        Returns:
            A list of Inbound model instances.
        """
        endpoint = "/list"
        json_resp = await self._simple_get(f"{endpoint}")
        inbounds = Inbound.from_list(json_resp)
        return inbounds

    async def get_specific_inbound(self, inbound_id: int) -> Inbound:
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

    async def add_inbound(self, inbound: Inbound) -> Response:
        """Create a new inbound on the panel.

        Args:
            inbound: Full inbound configuration. ``id`` and ``clientStats`` are
                omitted from the JSON body (assigned by the server).

        Returns:
            The raw HTTP response from the API.
        """
        payload = json.loads(
            inbound.model_dump_json(
                by_alias=True,
                exclude_none=True,
                exclude={"id", "clientStats"},
            )
        )
        return await self._core.safe_post(f"{self._url}/add", json=payload)

    async def delete_inbound_by_id(self, inbound_id: int) -> Response:
        """Delete an inbound by its panel ID.

        Args:
            inbound_id: The inbound identifier.

        Returns:
            The raw HTTP response from the API.
        """
        return await self._core.safe_post(f"{self._url}/del/{inbound_id}")


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
    _url = "panel/api/inbounds"

    #although it's the same url, they should be differentiated

    async def get_client_with_email(self, email: str, *, raise_if_none=True) -> ClientStats|None:
        """Retrieve client statistics by email.

        Args:
            email: The client's email identifier.

        Returns:
            A ClientStats model instance with the client's statistics.
        """
        endpoint = f"/getClientTraffics/{email}"
        resp = await self._simple_get(endpoint)
        if resp is None:
            if raise_if_none:
                raise ClientDoesNotExistError(f"Client with email {email} does not exist!")
            return None
        return ClientStats.model_validate(resp)

    async def get_client_with_uuid(self, uuid: str) -> list[ClientStats]:
        """Retrieve client statistics by UUID.

        Args:
            uuid: The client's unique identifier.

        Returns:
            A list of ClientStats model instances matching the UUID.
        """
        endpoint = f"/getClientTrafficsById/{uuid}"
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
        endpoint = f"/addClient"
        if isinstance(client, dict):
            try:
                final = InboundClients.model_validate(client)
            except ValidationError:
                # Check the SingleInboundClient now...
                tmp = SingleInboundClient.model_validate(client)
                if inbound_id:
                    final = InboundClients(parent_id=inbound_id,
                                           settings=ClientsSettings(clients=[tmp]))
                else:
                    raise ValueError("A single client was provided to be added but no parent inbound id")
        elif isinstance(client, SingleInboundClient):
            if not inbound_id:
                raise ValueError("A single client was provided to be added but no parent inbound id")
            final = InboundClients(parent_id=inbound_id,
                                   settings=ClientsSettings(clients=[client]))
        elif isinstance(client, InboundClients):
            final = client
            if inbound_id:
                final.parent_id = inbound_id
        else:
            raise TypeError
        # send request
        data = json.loads(final.model_dump_json(by_alias=True))
        resp = await self._core.safe_post(f"{self._url}{endpoint}", json=data)
        #YOU NEED TO PASS SETTINGS AS A STRING, NOT AS A DICT, YOU IDIOT!
        return resp

    async def request_update_client(self, client: InboundClients | SingleInboundClient,
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
                Required by the 3X-UI update endpoint.

        Returns:
            The HTTP response from the API.
        """
        if isinstance(client, SingleInboundClient):
            client = InboundClients(parent_id=inbound_id, settings=ClientsSettings(clients=[client]))
        _endpoint = f"/updateClient/{original_uuid}"
        # we have to do this because if we do model.dump() it will return a Settings **OBJECT** which we DON'T want.
        resp = await self._core.safe_post(f"{self._url}{_endpoint}",
                                          json=json.loads(client.model_dump_json(exclude_none=True, by_alias=True)))
        return resp

    async def update_single_client(self, inbound_id: int, found_client: SingleInboundClient, *,
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
        """Update an existing client.

        Caller must pass the current client model fetched from the panel.
        The previous implementation reached into ``XUIClient._find_client_in_inbound``;
        that lookup now lives in ``TgidClientService``.

        Args:
            inbound_id: The ID of the inbound the client belongs to.
            found_client: Existing client row as returned under the inbound.
            security: New security settings (optional).
            password: New password (optional).
            flow: New flow settings (optional).
            email: New email address (optional).
            limit_ip: New IP limit (optional).
            limit_gb: New traffic limit in gigabytes (optional).
            expiry_time: New expiry time as a UNIX timestamp in seconds (optional).
            enable: New enable status (optional).
            sub_id: New subscription ID (optional).
            comment: New comment (optional).

        Returns:
            The HTTP response from the API.
        """
        # Collect only the arguments that were explicitly provided (not None)
        changes = {k: v for k, v in locals().items()
                   if k not in ("self", "inbound_id", "found_client", "changes", "keep_uuid") and v is not None}
        # Rename sub_id to subscription_id if needed
        if 'sub_id' in changes:
            changes['subscription_id'] = changes.pop('sub_id')

        changes["updated_at"] = int(datetime.now(UTC).timestamp())
        # TODO: see if model_copy actually does validation
        updated = found_client.model_copy(update=changes)
        resp = await self.request_update_client(
            updated, inbound_id, original_uuid=found_client.uuid
        )
        return resp

    async def delete_expired_clients(self, inbound_id: int) -> Response:
        """Delete expired clients from an inbound.

        Args:
            inbound_id: The ID of the inbound to delete expired clients from.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"/delDepletedClients/"
        resp = await self._core.safe_post(f"{self._url}{_endpoint}{inbound_id}")
        return resp

    async def delete_client_by_email(self, email: str, inbound_id: int) -> Response:
        """Delete a client by email.

        Args:
            email: The email of the client to delete.
            inbound_id: The ID of the inbound the client belongs to.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"/{inbound_id}/delClientByEmail/{email}"
        resp = await self._core.safe_post(f"{self._url}{_endpoint}")
        return resp

    async def delete_client_by_uuid(self, uuid: str, inbound_id: int) -> Response:
        """Delete a client by UUID.

        Args:
            uuid: The UUID of the client to delete.
            inbound_id: The ID of the inbound the client belongs to.

        Returns:
            The HTTP response from the API.
        """
        _endpoint = f"/{inbound_id}/delClient/{uuid}"
        resp = await self._core.safe_post(f"{self._url}{_endpoint}")
        return resp
