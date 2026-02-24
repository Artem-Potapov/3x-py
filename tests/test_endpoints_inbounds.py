"""Unit tests for Inbounds endpoint."""
import pytest
from python_3xui.api import XUIClient
from python_3xui.models import Inbound


class TestInboundsEndpoint:
    """Test suite for Inbounds endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_get_inbounds_all")
    async def test_get_all_inbounds(self, xui_client: XUIClient):
        """Test get_all returns list of Inbounds."""
        inbounds = await xui_client.inbounds_end.get_all()
        assert isinstance(inbounds, list)
        assert len(inbounds) > 0
        assert all(isinstance(i, Inbound) for i in inbounds)

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_get_inbounds_verify_field_types")
    async def test_get_all_inbounds_field_types(self, xui_client: XUIClient):
        """Test inbound fields have correct types."""
        inbounds = await xui_client.inbounds_end.get_all()
        inbound = inbounds[0]
        assert isinstance(inbound.id, int)
        assert isinstance(inbound.port, int)
        assert isinstance(inbound.enable, bool)
        assert isinstance(inbound.remark, str)
        assert 1 <= inbound.port <= 65535

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_get_inbound_specific")
    async def test_get_specific_inbound(self, xui_client: XUIClient):
        """Test get_specific_inbound returns matching inbound."""
        all_inbounds = await xui_client.inbounds_end.get_all()
        assert len(all_inbounds) > 0
        test_id = all_inbounds[0].id
        specific = await xui_client.inbounds_end.get_specific_inbound(test_id)
        assert isinstance(specific, Inbound)
        assert specific.id == test_id

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_match_inbound_all_specific_same")
    async def test_get_specific_inbound_matches_get_all(self, xui_client: XUIClient):
        """Test get_specific_inbound matches data from get_all."""
        all_inbounds = await xui_client.inbounds_end.get_all()
        test_id = all_inbounds[0].id
        specific = await xui_client.inbounds_end.get_specific_inbound(test_id)
        # Compare key fields
        assert specific.id == all_inbounds[0].id
        assert specific.remark == all_inbounds[0].remark
        assert specific.port == all_inbounds[0].port

