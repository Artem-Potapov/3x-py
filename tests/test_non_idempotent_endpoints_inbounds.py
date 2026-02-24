import pytest
import json
from datetime import datetime, UTC
from python_3xui.api import XUIClient
from python_3xui.models import Inbound


class TestInboundsEndpoint:
    """All the non-idempotent tests for inbounds endpoint.
    These will:
     > Create new inbounds
     > Delete inbounds by id"""

    # Class variable to store created inbound ID
    created_inbound_id: int | None = None

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_create_inbound")
    async def test_create_inbound(self, xui_client: XUIClient):
        """Test creating a new inbound with minimal required fields"""
        # Generate unique test data
        timestamp = int(datetime.now(UTC).timestamp())
        test_port = 50000 + (timestamp % 10000)  # Unique port number

        # Create minimal inbound configuration
        # Based on 3x-ui API, we need minimal required fields
        test_inbound = Inbound(
            id=0,  # Will be assigned by server
            up=0,
            down=0,
            total=0,
            allTime=0,
            remark=f"Test Inbound {timestamp}",
            enable=True,
            expiryTime=timestamp + 86400,  # 1 day from now
            trafficReset="Never",
            lastTrafficResetTime=0,
            clientStats=None,
            listen="",
            port=test_port,
            protocol="vless",
            settings=json.dumps({
                "clients": [],
                "decryption": "none",
                "fallbacks": []
            }),
            streamSettings=json.dumps({
                "network": "tcp",
                "security": "none",
                "tcpSettings": {
                    "header": {
                        "type": "none"
                    }
                }
            }),
            sniffing=json.dumps({
                "enabled": True,
                "destOverride": ["http", "tls"]
            }),
            tag=f"test-inbound-{timestamp}"
        )

        # Create the inbound
        response = await xui_client.inbounds_end.addigga

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True
        assert "Inbound" in response_json["msg"] and "created" in response_json["msg"].lower()

        # Store the created inbound ID for deletion test
        # Note: We need to fetch the inbound to get its ID since it's assigned by server
        all_inbounds = await xui_client.inbounds_end.get_all()
        test_inbounds = [inb for inb in all_inbounds if inb.remark == test_inbound.remark]
        assert len(test_inbounds) == 1, "New inbound should be in the list"

        TestInboundsEndpoint.created_inbound_id = test_inbounds[0].id
        print(f"Created test inbound with ID: {TestInboundsEndpoint.created_inbound_id}")

        # Validate the created inbound
        assert test_inbounds[0].port == test_port
        assert test_inbounds[0].protocol == test_inbound.protocol
        assert test_inbounds[0].enable == True

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_create_inbound"], name="test_delete_inbound")
    async def test_delete_inbound_by_id(self, xui_client: XUIClient):
        """Test deleting an inbound by ID"""
        # Check if we have a created inbound to delete
        if TestInboundsEndpoint.created_inbound_id is None:
            pytest.skip("No inbound created in previous test")

        inbound_id = TestInboundsEndpoint.created_inbound_id

        # Verify the inbound exists before deletion
        try:
            existing_inbound = await xui_client.inbounds_end.get_specific_inbound(inbound_id)
            assert existing_inbound.id == inbound_id
        except Exception as e:
            pytest.skip(f"Test inbound with ID {inbound_id} no longer exists: {e}")

        # Delete the inbound
        response = await xui_client.inbounds_end.delete_inbound_by_id(inbound_id)

        # Validate response
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] == True

        # Verify deletion by trying to get the deleted inbound
        all_inbounds = await xui_client.inbounds_end.get_all()
        deleted_inbound_exists = any(inb.id == inbound_id for inb in all_inbounds)
        assert not deleted_inbound_exists, "Inbound should be deleted from the list"

        print(f"Successfully deleted test inbound with ID: {inbound_id}")

        # Verify we can't get the deleted inbound
        # Note: 3x-ui might return 404 or error when trying to get deleted inbound
        # We'll handle this gracefully

        # Reset for potential test re-runs
        TestInboundsEndpoint.created_inbound_id = None
