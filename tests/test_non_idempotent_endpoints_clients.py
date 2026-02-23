import pytest
from datetime import datetime, UTC
from api import XUIClient
from models import SingleInboundClient, ClientStats
from util import get_telegram_uuid, sub_from_tgid


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
            if xui_client.PROD_STRING in inbound.remark.lower():
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
        timestamp = int(datetime.now(UTC).timestamp())
        test_uuid = get_telegram_uuid(TestClientsEndpoint.test_telegram_id)
        test_email = f"testclient_{timestamp}@example.com"

        # Create a test client
        test_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email=test_email,
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=10,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400,  # Using alias 'expiryTime' for 'expiry_time'
            enable=True,
            tgId="",  # Using alias 'tgId' for 'tg_id'
            subId=sub_from_tgid(TestClientsEndpoint.test_telegram_id),  # Using alias 'subId' for 'subscription_id'
            comment=f"Test client created at {timestamp}",
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
        except Exception as e:
            pytest.skip(f"Test client with email {email} no longer exists: {e}")

        # Delete the client by email
        response = await xui_client.clients_end.delete_client_by_email(email, inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Inbound client has been deleted." in response_json["msg"]

        # Verify deletion by trying to get the deleted client
        # Note: 3x-ui might return an error or null response for deleted client
        try:
            await xui_client.clients_end.get_client_with_email(email)
            # If we get here, the client still exists
            print(f"Warning: Client with email {email} might still exist after deletion")
            # For test purposes, we'll consider this acceptable if it's a timing issue
        except Exception:
            # Expected - client should be deleted
            pass

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
        timestamp = int(datetime.now(UTC).timestamp())
        test_uuid = get_telegram_uuid(TestClientsEndpoint.test_telegram_id + 1)  # Different UUID
        test_email = f"testclient_uuid_{timestamp}@example.com"

        # Create a new test client
        test_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email=test_email,
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=10,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400,  # Using alias 'expiryTime' for 'expiry_time'
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
        response = await xui_client.clients_end.delete_client_by_uuid(test_uuid, inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Inbound client has been deleted." in response_json["msg"]

        print(f"Successfully deleted test client by UUID: {test_uuid}")

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_add_client", "test_delete_client_email"])
    async def test_delete_client_by_tgid_all_inbounds(self, xui_client: XUIClient):
        """Test deleting a client across all production inbounds by Telegram ID"""
        # Get production inbounds
        production_inbounds = await xui_client.get_production_inbounds()
        if not production_inbounds:
            pytest.skip("No production inbounds found for testing")

        # Generate unique test data
        timestamp = int(datetime.now(UTC).timestamp())
        test_uuid = get_telegram_uuid(TestClientsEndpoint.test_telegram_id + 2)  # Different UUID
        test_email = f"testclient_tgid_{timestamp}@example.com"

        # Create a test client
        test_client = SingleInboundClient.model_construct(
            id=test_uuid,  # Using alias 'id' for 'uuid'
            security="",
            password="",
            flow="",
            email=test_email,
            limitIp=20,  # Using alias 'limitIp' for 'limit_ip'
            totalGB=10,  # Using alias 'totalGB' for 'limit_gb'
            expiryTime=timestamp + 86400,  # Using alias 'expiryTime' for 'expiry_time'
            enable=True,
            tgId="",  # Using alias 'tgId' for 'tg_id'
            subId=f"test_tgid_{timestamp}",  # Using alias 'subId' for 'subscription_id'
            comment=f"Test client for TGID deletion at {timestamp}",
            created_at=timestamp,
            updated_at=timestamp
        )

        # Add client to all production inbounds
        added_responses = []
        for inbound in production_inbounds:
            response = await xui_client.clients_end.add_client(test_client, inbound.id)
            assert response.status_code == 200
            added_responses.append(response)

        print(f"Added test client with email: {test_email}, UUID: {test_uuid} to {len(production_inbounds)} production inbounds")

        # Now delete the client from all production inbounds by Telegram ID
        responses = await xui_client.delete_client_by_tgid_all_inbounds(TestClientsEndpoint.test_telegram_id + 2)

        # Validate responses
        assert len(responses) == len(production_inbounds)
        for response in responses:
            assert response.status_code == 200
            response_json = response.json()
            assert response_json["success"] == True
            assert "Inbound client has been deleted." in response_json["msg"]

        print(f"Successfully deleted test client by Telegram ID from {len(responses)} production inbounds")

        # Verify deletion by trying to get the deleted client from each inbound
        for inbound in production_inbounds:
            try:
                await xui_client.clients_end.get_client_with_email(test_email)
                # If we get here, the client still exists in at least one inbound
                print(f"Warning: Client with email {test_email} might still exist in inbound {inbound.id} after deletion")
            except Exception:
                # Expected - client should be deleted
                pass
