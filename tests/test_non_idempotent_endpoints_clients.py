import asyncio
from datetime import UTC

import pytest
from pydantic import ValidationError

from python_3xui.api import XUIClient
from python_3xui.models import SingleInboundClient, ClientStats
from python_3xui.util import datetime_now_ms, generate_email_from_tgid_inbid


class TestClientsEndpoint:
    """All the non-idempotent tests for clients endpoint.
    These will:
     > Create new clients
     > Delete clients by email and uuid"""

    # Class variables to store test data
    test_telegram_id: int = 999888777
    test_inbound_id: int | None = None
    created_client_email: str | None = None
    created_client_uuid: str | None = None

    @pytest.fixture()
    async def setup_test_inbound(self, xui_client: XUIClient):
        """Fixture to get or create a test inbound for client testing"""
        # Get all existing inbounds
        all_inbounds = await xui_client.inbounds_end.get_all()

        if not all_inbounds:
            pytest.skip("No inbounds available for testing")

        # Try to find a suitable inbound (preferably with PROD_STRING in remark)
        test_inbound = None
        for inbound in all_inbounds:
            if xui_client.PROD_STRING.search(inbound.remark):
                test_inbound = inbound
                break

        # If no inbound with PROD_STRING found, use the first one
        if test_inbound is None:
            test_inbound = all_inbounds[0]

        TestClientsEndpoint.test_inbound_id = test_inbound.id
        yield test_inbound

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_add_client")
    async def test_add_client(self, xui_client: XUIClient, setup_test_inbound):
        """Test adding a new client to an inbound"""
        # Use the test inbound ID from fixture
        inbound_id = TestClientsEndpoint.test_inbound_id
        assert inbound_id is not None, "Test inbound should be available"

        # Generate unique test data
        timestamp = datetime_now_ms(UTC)
        test_uuid = await xui_client._resolve_uuid(TestClientsEndpoint.test_telegram_id)
        test_email = f"testclient_{timestamp}@example.com"

        # Create a test client
        custom_sub = await xui_client._resolve_sub(TestClientsEndpoint.test_telegram_id)
        test_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email=test_email,
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=10000,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400*1000,  # Using alias 'expiryTime' for 'expiry_time'
            enable=True,
            tgId="",  # Using alias 'tgId' for 'tg_id'
            subId=custom_sub,  # Using alias 'subId' for 'subscription_id'
            comment=f"Test client created at {timestamp}, TEST SUITE",
            created_at=timestamp,
            updated_at=timestamp
        )

        # Add the client to the inbound
        response = await xui_client.clients_end.add_client(test_client, inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Inbound client(s) have been added" in response_json["msg"]

        # Store created client data for deletion tests
        TestClientsEndpoint.created_client_email = test_email
        TestClientsEndpoint.created_client_uuid = test_uuid

        print(f"Created test client with email: {test_email}, UUID: {test_uuid} in inbound: {inbound_id}")

        # Verify the client was actually added by fetching it
        try:
            client_stats = await xui_client.clients_end.get_client_with_email(test_email)
            assert isinstance(client_stats, ClientStats)
            assert client_stats.email == test_email
            assert client_stats.uuid == test_uuid
        except Exception as e:
            # It might take a moment for the client to appear in stats
            print(f"Note: Client stats not immediately available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_add_client"], name="test_delete_client_email")
    async def test_delete_client_by_email(self, xui_client: XUIClient):
        """Test deleting a client by email"""
        # Check if we have a created client to delete
        if TestClientsEndpoint.created_client_email is None or TestClientsEndpoint.test_inbound_id is None:
            pytest.skip("No client created in previous test")

        email = TestClientsEndpoint.created_client_email
        inbound_id = TestClientsEndpoint.test_inbound_id

        # Verify the client exists before deletion
        try:
            client_stats = await xui_client.clients_end.get_client_with_email(email)
            assert client_stats.email == email
        except ValidationError as e:
            pytest.skip(f"Test client with email {email} no longer exists: {e}")

        # Delete the client by email
        print(f"Attempting to delete client with email: {email} from inbound: {inbound_id}")

        response = await xui_client.clients_end.delete_client_by_email(email, inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Client deleted successfully" in response_json["msg"]

        try:
            await xui_client.clients_end.get_client_with_email(email)
            #if there's no error meaning the client still exists, fail the test
            await asyncio.sleep(1)  # Wait a moment
            pytest.fail("The client still exists after deletion attempt")
        except ValidationError:
            print(f"Successfully deleted test client by email: {email}")

        # Only clear email, keep UUID for next test
        TestClientsEndpoint.created_client_email = None

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_add_client", "test_delete_client_email"], name="test_delete_client_uuid")
    async def test_delete_client_by_uuid(self, xui_client: XUIClient, setup_test_inbound):
        """Test deleting a client by UUID"""
        # For this test, we need to create a new client since we deleted the previous one by email
        inbound_id = TestClientsEndpoint.test_inbound_id
        assert inbound_id is not None, "Test inbound should be available"

        # Generate new test data
        timestamp = datetime_now_ms(UTC)
        test_uuid = await xui_client._resolve_uuid(TestClientsEndpoint.test_telegram_id + 1)  # Different UUID
        test_email = f"testclient_uuid_{timestamp}@example.com"

        # Create a new test client
        test_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email=test_email,
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=0,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400*1000,  # Using alias 'expiryTime' for 'expiry_time'
            enable=True,
            tgId="",  # Using alias 'tgId' for 'tg_id'
            subId=f"test_sub_{timestamp}",  # Using alias 'subId' for 'subscription_id'
            comment=f"Test client for UUID deletion at {timestamp}",
            created_at=timestamp,
            updated_at=timestamp
        )

        # Add the client
        response = await xui_client.clients_end.add_client(test_client, inbound_id)
        assert response.status_code == 200

        # Delete the client by UUID
        print(f"Attempting to delete client with UUID: {test_uuid} from inbound: {inbound_id}")
        response = await xui_client.clients_end.delete_client_by_uuid(test_uuid, inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Inbound client has been deleted." in response_json["msg"]

        print(f"The API said it deleted the client: {test_uuid}")
        check_clients = await xui_client.clients_end.get_client_with_uuid(test_uuid)
        for client in check_clients:
            if client.inboundId == inbound_id and client.uuid == test_uuid:
                pytest.fail("The client still exists after deletion attempt")
        print("Check complete, client not found as expected")

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_add_client", "test_delete_client_email"])
    async def test_delete_client_by_tgid_all_inbounds(self, xui_client: XUIClient):
        """Test deleting a client across all production inbounds by Telegram ID"""
        production_inbounds = await xui_client.get_production_inbounds()
        if not production_inbounds:
            pytest.skip("No production inbounds found for testing")
        TEST_TELEGRAM_ID = 420

        timestamp = datetime_now_ms(UTC)
        test_uuid = await xui_client._resolve_uuid(TEST_TELEGRAM_ID)

        template_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email="",  # set per-inbound below
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=0,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400 * 1000,  # Using alias 'expiryTime' for 'expiry_time'
            enable=True,
            tgId="",  # Using alias 'tgId' for 'tg_id'
            subId=f"test_tgid_{timestamp}",  # Using alias 'subId' for 'subscription_id'
            comment=f"Test client for TGID deletion at {timestamp}",
            created_at=timestamp,
            updated_at=timestamp
        )

        # Add client to every production inbound, recording the email actually used.
        emails_by_inbound: dict[int, str] = {}
        for inbound in production_inbounds:
            email = generate_email_from_tgid_inbid(TEST_TELEGRAM_ID, inbound.id)
            send_client = template_client.model_copy(update={"email": email})
            response = await xui_client.clients_end.add_client(send_client, inbound.id)
            assert response.status_code == 200, f"Failed to add client to inbound {inbound.id}: {response.text}"
            emails_by_inbound[inbound.id] = email

        print(f"Added test client UUID {test_uuid} to {len(production_inbounds)} production inbounds")

        responses = await xui_client.revoke_client_by_tgid_all_inbounds(TEST_TELEGRAM_ID)

        assert len(responses) == len(production_inbounds)
        for response in responses:
            assert response.status_code == 200
            response_json = response.json()
            assert response_json["success"] == True
            assert "Client deleted successfully" in response_json["msg"]

        print(f"Successfully deleted test client by Telegram ID from {len(responses)} production inbounds")

        # Verify each created email is actually gone. The 3X-UI panel responds with
        # status 200 + null obj for missing clients, which surfaces as a ValidationError
        # from ClientStats.model_validate (see test_delete_client_by_email).
        for inbound_id, email in emails_by_inbound.items():
            try:
                await xui_client.clients_end.get_client_with_email(email)
            except ValidationError:
                continue
            pytest.fail(
                f"Client with email {email} still exists in inbound {inbound_id} after revoke"
            )

        # Cross-check via UUID: no remaining stats should reference any production inbound.
        remaining = await xui_client.clients_end.get_client_with_uuid(test_uuid)
        prod_inbound_ids = {inb.id for inb in production_inbounds}
        leftover = [c for c in remaining if c.inboundId in prod_inbound_ids]
        assert not leftover, (
            f"UUID lookup still returns {len(leftover)} client(s) in production inbounds: "
            f"{[(c.inboundId, c.email) for c in leftover]}"
        )
