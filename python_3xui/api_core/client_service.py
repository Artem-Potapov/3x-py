"""Telegram-ID-oriented high-level client operations."""

from __future__ import annotations

import asyncio
import logging
from asyncio import Task
from datetime import datetime, UTC
from typing import TYPE_CHECKING, List, Literal

from httpx import Response

from python_3xui import util
from python_3xui.custom_exceptions import ClientDoesNotExistError, ClientEmailAlreadyExistsError
from python_3xui.models import ClientStats, Inbound, SingleInboundClient
from python_3xui.util import get_inbound_in_client

if TYPE_CHECKING:
    from python_3xui.endpoints import Clients, Inbounds
    from python_3xui.api_core.identity import IdentityResolver
    from python_3xui.api_core.prod_cache import ProductionInboundCache


class TgIDClientService:
    """Orchestrates TGID-derived flows against panel endpoints."""

    __slots__ = ("_clients", "_inbounds", "_identity", "_prod_cache")

    def __init__(self,
                 clients_endpoint: Clients,
                 inbounds_endpoint: Inbounds,
                 identity: IdentityResolver,
                 prod_cache: ProductionInboundCache,
                 ) -> None:
        self._clients = clients_endpoint
        self._inbounds = inbounds_endpoint
        self._identity = identity
        self._prod_cache = prod_cache

    async def get_client_with_tgid(self, tgid: int, inbound_id: int | None = None) -> list[ClientStats]:
        if inbound_id:
            email = util.generate_email_from_tgid_inbid(tgid, inbound_id)
            return [await self._clients.get_client_with_email(email)]
        uuid = await self._identity.resolve_uuid(tgid)
        return await self._clients.get_client_with_uuid(uuid)

    async def create_and_add_prod_client(self,
                                         telegram_id: int,
                                         *,
                                         additional_remark: str | None = None,
                                         expiry_time: int = 0,
                                         exist_ok: bool = False,
                                         replace_if_exist: bool = False,
                                         ) -> dict[int, Response]:
        production_inbounds: tuple[Inbound, ...] = await self._prod_cache.get()

        custom_sub = await self._identity.resolve_sub(telegram_id)
        uuid = await self._identity.resolve_uuid(telegram_id)

        # --- Phase 1: build clients and burst-add them ---
        _to_exec: list[asyncio.Task[Response]] = []
        clients_by_inbound: dict[int, SingleInboundClient] = {}
        for inb in production_inbounds:
            tmp_email = util.generate_email_from_tgid_inbid(telegram_id, inb.id)
            client = SingleInboundClient(
                uuid=uuid,
                flow="",
                email=tmp_email,
                limit_gb=0,
                enable=True,
                subscription_id=custom_sub,
                comment=f"{additional_remark + ', ' if additional_remark else ''}created at {datetime.now(UTC)}",
                expiry_time=expiry_time,
            )
            clients_by_inbound[inb.id] = client
            _to_exec.append(
                asyncio.create_task(self._clients.add_client(client, inb.id))
            )

        raw_results: list[Response] = await asyncio.gather(*_to_exec)

        # Map inbound IDs to their add responses
        responses: dict[int, Response] = {}
        for i, inb in enumerate(production_inbounds):
            responses[inb.id] = raw_results[i]

        # --- Phase 2: replace duplicates when replace_if_exist is set ---
        if replace_if_exist:
            _update_exec: list[asyncio.Task[Response]] = []
            # Track which inbound each update task corresponds to via list index
            update_inbound_ids: list[int] = []

            for inb_id, resp in list(responses.items()):
                json_resp = resp.json()
                msg = json_resp.get("msg", "")
                if "duplicate email" in msg.lower():
                    client = clients_by_inbound[inb_id]
                    _update_exec.append(
                        asyncio.create_task(
                            self._clients.request_update_client(
                                client, inb_id, original_uuid=client.uuid,
                            )
                        )
                    )
                    update_inbound_ids.append(inb_id)

            if _update_exec:
                update_results: list[Response] = await asyncio.gather(*_update_exec)
                for i, inb_id in enumerate(update_inbound_ids):
                    responses[inb_id] = update_results[i]

        # --- Phase 3: raise on remaining duplicates if not exist_ok ---
        if not exist_ok:
            for inb_id, resp in responses.items():
                json_resp = resp.json()
                msg = json_resp.get("msg", "")
                if "duplicate email" in msg.lower():
                    logging.error(
                        "ERROR: Client already exists and exist_ok not set: %s",
                        msg,
                    )
                    raise ClientEmailAlreadyExistsError(msg)

        return responses

    async def _find_client_in_inbound(self,
                                      client_uuid: str,
                                      inbound_id: int,
                                      *,
                                      use_cache: bool = False,
                                      ) -> SingleInboundClient | None:
        if use_cache:
            prod_inbs = await self._prod_cache.get()
            prod_inb_index = None
            for i, prod_inb in enumerate(prod_inbs):
                if inbound_id == prod_inb.id:
                    prod_inb_index = i

            if prod_inb_index is not None:
                needed_inb: Inbound = prod_inbs[prod_inb_index]
                result = get_inbound_in_client(client_uuid, needed_inb)
                if result is None:
                    self._prod_cache.get.cache_clear()
                    new_inb = (await self._prod_cache.get())[prod_inb_index]
                    return get_inbound_in_client(client_uuid, new_inb)

        inb = await self._inbounds.get_specific_inbound(inbound_id)
        for client in inb.settings.clients:
            if client.uuid == client_uuid:
                return client
        return None

    async def update_client_by_tgid_only(self,
                                         telegram_id: int,
                                         prod_only: bool,
                                         /,
                                         *,
                                         security: str | None = None,
                                         password: str | None = None,
                                         flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                         limit_ip: int | None = None,
                                         limit_gb: int | None = None,
                                         expiry_time: int | None = None,
                                         enable: bool | None = None,
                                         sub_id: str | None = None,
                                         comment: str | None = None,
                                         verbose: bool = True,
                                         force_search_by_email: bool = False,
                                         not_found_action: Literal["raise", "ignore"] = "ignore",
                                         client_to_create: SingleInboundClient | None = None
                                         ) -> list[Response]:
        updates = {
            "security": security,
            "password": password,
            "flow": flow,
            "limit_ip": limit_ip,
            "limit_gb": limit_gb,
            "expiry_time": expiry_time,
            "enable": enable,
            "sub_id": sub_id,
            "comment": comment,
        }
        updates = {k: v for k, v in updates.items() if v is not None}

        if verbose:
            if expiry_time and expiry_time < 1e9:
                logging.warning(
                    "Warning: You're trying to update a client with expiry time %s. "
                    "You set it to expire before 2001, likely because you provided the DURATION. "
                    "You need to provide a TIMESTAMP. "
                    "If you want to disable this message, set verbose=false.",
                    expiry_time,
                )

        _to_exec: list[Task] = []
        client_uuid = await self._identity.resolve_uuid(telegram_id)
        if prod_only:
            self._prod_cache.get.cache_clear()
            inbounds = await self._prod_cache.get()
        else:
            inbounds = await self._inbounds.get_all()
        for inbound in inbounds:
            found_client = util.get_inbound_in_client(client_uuid, inbound)
            if not found_client:
                if force_search_by_email:
                    _email = util.generate_email_from_tgid_inbid(telegram_id, inbound.id)
                    found_client = await self._clients.get_client_with_email(_email, raise_if_none=False)
                # this double-check is better than 2 branches doing the same thing
                if not found_client:
                    if not_found_action == "ignore":
                        pass
                    if not_found_action == "raise":
                        raise ClientDoesNotExistError(f"Client not found: {client_uuid}")

            if found_client:
                new_client = found_client.model_copy(update=updates, deep=True)
                _to_exec.append(
                    asyncio.create_task(
                        self._clients.request_update_client(
                            new_client, inbound.id, original_uuid=client_uuid
                        )
                    )
                )
        return await asyncio.gather(*_to_exec)

    async def update_client_by_tgid_inbid(self,
                                          telegram_id: int,
                                          inbound_id: int,
                                          /,
                                          *,
                                          security: str | None = None,
                                          password: str | None = None,
                                          flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"] | None = None,
                                          limit_ip: int | None = None,
                                          limit_gb: int | None = None,
                                          expiry_time: int | None = None,
                                          enable: bool | None = None,
                                          sub_id: str | None = None,
                                          comment: str | None = None,
                                          email: str | None = None,
                                          verbose: bool = True,
                                          force_resolve_by_email: bool = False,
                                          ) -> Response:
        if verbose:
            if expiry_time and expiry_time < 1e9:
                logging.warning(
                    "Warning: You're trying to update a client with expiry time %s. "
                    "You set it to expire before 2001, likely because you provided the DURATION. "
                    "You need to provide a TIMESTAMP. "
                    "If you want to disable this message, set verbose=false.",
                    expiry_time,
                )

        client_uuid = await self._identity.resolve_uuid(telegram_id)
        found = await self._find_client_in_inbound(client_uuid, inbound_id)
        if not found:
            if force_resolve_by_email:
                _email = util.generate_email_from_tgid_inbid(telegram_id, inbound_id)
                resp = await self._clients.get_client_with_email(email, raise_if_none=False)
                if resp is None:
                    raise ClientDoesNotExistError(f"The target inbound was force-checked by email but client {_email} was not found.")
                client_uuid = resp.uuid
            raise ClientDoesNotExistError(
                f"The target inbound was checked but client {client_uuid} was not found."
            )
        return await self._clients.update_single_client(
            inbound_id=inbound_id,
            found_client=found,
            security=security,
            password=password,
            email=email,
            flow=flow,
            limit_ip=limit_ip,
            limit_gb=limit_gb,
            expiry_time=expiry_time,
            enable=enable,
            sub_id=sub_id,
            comment=comment,
        )

    async def delete_client_by_tgid(self, telegram_id: int, inbound_id: int) -> Response:
        email = util.generate_email_from_tgid_inbid(telegram_id, inbound_id)
        return await self._clients.delete_client_by_email(email, inbound_id)

    async def revoke_client_by_tgid_all_inbounds(self, telegram_id: int) -> List[Response]:
        production_inbounds = await self._prod_cache.get()
        _to_exec: list[Task] = []
        for inbound in production_inbounds:
            email = util.generate_email_from_tgid_inbid(telegram_id, inbound.id)
            _to_exec.append(
                asyncio.create_task(
                    self._clients.delete_client_by_email(email, inbound.id)
                )
            )
            logging.info("Clients of of tgid %s pending deletion", telegram_id)
        return await asyncio.gather(*_to_exec)
