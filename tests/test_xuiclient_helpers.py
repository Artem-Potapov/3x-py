"""Non-idempotent tests for the high-level XUIClient client helpers.

These tests exercise the convenience methods on `XUIClient` itself (as opposed
to the lower-level `clients_end` endpoint methods covered elsewhere):

- `create_and_add_prod_client`
- `get_client_with_tgid`
- `update_client_by_tgid`
- `delete_client_by_tgid`

Each test uses a dedicated Telegram ID so they can be run independently and
always clean up via `revoke_client_by_tgid_all_inbounds` in `finally`.
"""
import pytest
from pydantic import ValidationError

from python_3xui.api import XUIClient
from python_3xui.custom_exceptions import ClientEmailAlreadyExistsError
from python_3xui.models import ClientStats
from python_3xui.util import (
    generate_email_from_tgid_inbid,

)


# Distinct Telegram IDs per test, kept well clear of the IDs used in
# test_non_idempotent_endpoints_clients.py (999_888_777, 420).
_TGID_CREATE = 770_001
_TGID_GET = 770_002
_TGID_UPDATE = 770_003
_TGID_DELETE_ONE = 770_004
_TEST_SUB_ID = "TESTING_INBOUND_SUB_ID"


class TestXUIClientHelpers:
    """Test suite for high-level XUIClient client helpers."""

    @pytest.mark.asyncio
    async def test_create_and_add_prod_client(self, xui_client: XUIClient):
        """create_and_add_prod_client adds a client to every production inbound."""
        production_inbounds = await xui_client.get_production_inbounds()
        if not production_inbounds:
            pytest.skip("No production inbounds found for testing")

        try:
            responses = await xui_client.create_and_add_prod_client(
                _TGID_CREATE, additional_remark="helpers-suite-create"
            )
            assert len(responses) == len(production_inbounds)
            for resp in responses:
                assert resp.status_code == 200
                body = resp.json()
                assert body["success"] is True, f"Add failed: {body}"

            # Each per-inbound email must now resolve.
            for inbound in production_inbounds:
                email = generate_email_from_tgid_inbid(_TGID_CREATE, inbound.id)
                stats = await xui_client.clients_end.get_client_with_email(email)
                assert isinstance(stats, ClientStats)
                assert stats.email == email
                assert stats.inboundId == inbound.id

            # Calling again with exist_ok=True must not raise even though every
            # email is now a duplicate.
            await xui_client.create_and_add_prod_client(
                _TGID_CREATE, additional_remark="helpers-suite-create-2", exist_ok=True
            )

            # Calling without exist_ok must raise on duplicates.
            with pytest.raises(ClientEmailAlreadyExistsError):
                await xui_client.create_and_add_prod_client(
                    _TGID_CREATE, additional_remark="helpers-suite-create-3"
                )
        finally:
            await xui_client.revoke_client_by_tgid_all_inbounds(_TGID_CREATE)

    @pytest.mark.asyncio
    async def test_get_client_with_tgid_both_paths(self, xui_client: XUIClient):
        """get_client_with_tgid returns ClientStats via both the email and UUID paths."""
        production_inbounds = await xui_client.get_production_inbounds()
        if not production_inbounds:
            pytest.skip("No production inbounds found for testing")

        try:
            await xui_client.create_and_add_prod_client(
                _TGID_GET, additional_remark="helpers-suite-get"
            )

            # inbound_id provided -> uses generate_email_from_tgid_inbid + get_client_with_email.
            target_inbound = production_inbounds[0]
            by_email = await xui_client.get_client_with_tgid(
                _TGID_GET, inbound_id=target_inbound.id
            )
            assert isinstance(by_email, list) and len(by_email) == 1
            assert isinstance(by_email[0], ClientStats)
            assert by_email[0].email == generate_email_from_tgid_inbid(
                _TGID_GET, target_inbound.id
            )
            assert by_email[0].inboundId == target_inbound.id

            # inbound_id=None -> uses UUID, returns one entry per production inbound.
            by_uuid = await xui_client.get_client_with_tgid(_TGID_GET)
            assert isinstance(by_uuid, list)
            expected_uuid = await xui_client._resolve_uuid(_TGID_GET)
            assert all(isinstance(c, ClientStats) for c in by_uuid)
            assert all(c.uuid == expected_uuid for c in by_uuid)
            prod_ids = {inb.id for inb in production_inbounds}
            returned_prod_ids = {c.inboundId for c in by_uuid if c.inboundId in prod_ids}
            assert returned_prod_ids == prod_ids, (
                f"UUID lookup missed inbounds: expected {prod_ids}, got {returned_prod_ids}"
            )
        finally:
            await xui_client.revoke_client_by_tgid_all_inbounds(_TGID_GET)

    @pytest.mark.asyncio
    async def test_update_client_by_tgid(self, xui_client: XUIClient):
        """update_client_by_tgid changes a field that is observable via ClientStats."""
        production_inbounds = await xui_client.get_production_inbounds()
        if not production_inbounds:
            pytest.skip("No production inbounds found for testing")

        target_inbound = production_inbounds[0]
        try:
            await xui_client.create_and_add_prod_client(
                _TGID_UPDATE, additional_remark="helpers-suite-update", exist_ok=True
            )

            email = generate_email_from_tgid_inbid(_TGID_UPDATE, target_inbound.id)
            before = await xui_client.clients_end.get_client_with_email(email)
            assert before.enable is True, "Newly created client should start enabled"

            resp = await xui_client.update_client_by_tgid_inbid(
                _TGID_UPDATE, target_inbound.id, verbose=False, sub_id=_TEST_SUB_ID,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True, f"Update failed: {body}"

            after = await xui_client.clients_end.get_client_with_email(email)
            assert after.subId == _TEST_SUB_ID, "subscription did not change"
            assert after.email == email
            assert after.uuid == before.uuid
        finally:
            await xui_client.revoke_client_by_tgid_all_inbounds(_TGID_UPDATE)

    @pytest.mark.asyncio
    async def test_delete_client_by_tgid_single_inbound(self, xui_client: XUIClient):
        """delete_client_by_tgid removes the client from exactly the given inbound."""
        production_inbounds = await xui_client.get_production_inbounds()
        if len(production_inbounds) < 1:
            pytest.skip("No production inbounds found for testing")

        target_inbound = production_inbounds[0]
        try:
            await xui_client.create_and_add_prod_client(
                _TGID_DELETE_ONE, additional_remark="helpers-suite-delete-one"
            )

            target_email = generate_email_from_tgid_inbid(
                _TGID_DELETE_ONE, target_inbound.id
            )
            # Sanity: the client exists in the target inbound before deletion.
            await xui_client.clients_end.get_client_with_email(target_email)

            resp = await xui_client.delete_client_by_tgid(
                _TGID_DELETE_ONE, target_inbound.id
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True, f"Delete failed: {body}"
            assert "Client deleted successfully" in body["msg"]

            # Target inbound entry must be gone (3X-UI returns null obj -> ValidationError).
            with pytest.raises(ValidationError):
                await xui_client.clients_end.get_client_with_email(target_email)

            # Other production inbounds must be untouched.
            for inbound in production_inbounds:
                if inbound.id == target_inbound.id:
                    continue
                other_email = generate_email_from_tgid_inbid(
                    _TGID_DELETE_ONE, inbound.id
                )
                stats = await xui_client.clients_end.get_client_with_email(other_email)
                assert stats.email == other_email
                assert stats.inboundId == inbound.id
        finally:
            await xui_client.revoke_client_by_tgid_all_inbounds(_TGID_DELETE_ONE)
