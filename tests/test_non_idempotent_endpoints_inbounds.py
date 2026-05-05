import json

import pytest
from datetime import datetime, UTC

from python_3xui.api import XUIClient
from python_3xui.models import Inbound


class TestInboundsEndpoint:
    """Non-idempotent integration tests for inbound create/delete."""

    created_inbound_id: int | None = None

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_create_inbound")
    async def test_create_inbound(self, xui_client: XUIClient):
        """Create a minimal VLESS inbound via ``XUIClient.add_inbound``."""
        existing = await xui_client.inbounds_end.get_all()
        assert len(existing) > 0, "Need at least one inbound to mirror trafficReset casing from the panel"
        traffic_reset = existing[0].trafficReset

        timestamp = int(datetime.now(UTC).timestamp())
        remark_suffix = f"{timestamp}"
        response = None
        chosen_remark: str | None = None
        chosen_port: int | None = None

        for attempt in range(2):
            test_port = 40000 + ((timestamp + attempt * 9973) % 25000)
            chosen_remark = f"Test Inbound {remark_suffix}_{attempt}"
            test_inbound = Inbound(
                id=0,
                up=0,
                down=0,
                total=0,
                allTime=0,
                remark=chosen_remark,
                enable=True,
                expiryTime=timestamp + 86400,
                trafficReset=traffic_reset,
                lastTrafficResetTime=0,
                clientStats=None,
                listen="",
                port=test_port,
                protocol="vless",
                settings=json.dumps(
                    {"clients": [], "decryption": "none", "fallbacks": []}
                ),
                streamSettings=json.dumps(
                    {
                        "network": "tcp",
                        "security": "none",
                        "tcpSettings": {"header": {"type": "none"}},
                    }
                ),
                sniffing=json.dumps({"enabled": True, "destOverride": ["http", "tls"]}),
                tag=f"test-inbound-{remark_suffix}-{attempt}",
            )
            response = await xui_client.add_inbound(test_inbound)
            body = response.json()
            if response.status_code == 200 and body.get("success") is True:
                chosen_port = test_port
                break
            msg = (body.get("msg") or "")
            if attempt == 0 and "Port already exists" in msg:
                continue
            pytest.fail(f"add_inbound failed: status={response.status_code} body={body}")

        assert response is not None and chosen_remark is not None and chosen_port is not None
        response_json = response.json()
        msg = (response_json.get("msg") or "").lower()
        assert "success" in msg and "creat" in msg

        obj = response_json.get("obj")
        created_id: int | None = None
        if isinstance(obj, dict) and obj.get("id"):
            created_id = int(obj["id"])

        if created_id is None:
            all_inbounds = await xui_client.inbounds_end.get_all()
            matches = [inb for inb in all_inbounds if inb.remark == chosen_remark]
            assert len(matches) == 1, "New inbound should appear in list when obj.id missing"
            created_id = matches[0].id

        TestInboundsEndpoint.created_inbound_id = created_id

        all_inbounds = await xui_client.inbounds_end.get_all()
        test_inbounds = [inb for inb in all_inbounds if inb.remark == chosen_remark]
        assert len(test_inbounds) == 1
        assert test_inbounds[0].port == chosen_port
        assert test_inbounds[0].protocol == "vless"
        assert test_inbounds[0].enable is True

    @pytest.mark.asyncio
    @pytest.mark.dependency(depends=["test_create_inbound"], name="test_delete_inbound")
    async def test_delete_inbound_by_id(self, xui_client: XUIClient):
        """Delete the inbound created in the previous test via ``XUIClient.delete_inbound``."""
        if TestInboundsEndpoint.created_inbound_id is None:
            pytest.skip("No inbound created in previous test")

        inbound_id = TestInboundsEndpoint.created_inbound_id

        try:
            existing_inbound = await xui_client.inbounds_end.get_specific_inbound(inbound_id)
            assert existing_inbound.id == inbound_id
        except Exception as e:
            pytest.skip(f"Test inbound with ID {inbound_id} no longer exists: {e}")

        response = await xui_client.delete_inbound(inbound_id)
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["success"] is True

        all_inbounds = await xui_client.inbounds_end.get_all()
        assert not any(inb.id == inbound_id for inb in all_inbounds), "Inbound should be removed from list"

        TestInboundsEndpoint.created_inbound_id = None
