"""Unit tests for Clients endpoint."""
import pytest
from api import XUIClient
from models import ClientStats


class TestClientsEndpoint:
    """Test suite for Clients endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_get_client_email")
    async def test_get_client_with_email(self, xui_client: XUIClient):
        """Test get_client_with_email returns ClientStats."""
        all_inbounds = await xui_client.inbounds_end.get_all()
        assert len(all_inbounds) > 0
        test_email = None
        for inb in all_inbounds:
            if inb.clientStats:
                test_email = inb.clientStats[0].email
                break
        if test_email is None:
            pytest.skip("No clients available for testing")
        client_stats = await xui_client.clients_end.get_client_with_email(test_email)
        assert isinstance(client_stats, ClientStats)
        assert client_stats.email == test_email

    @pytest.mark.asyncio
    @pytest.mark.dependency(name="test_get_client_uuid")
    async def test_get_client_with_uuid(self, xui_client: XUIClient):
        """Test get_client_with_uuid returns list of ClientStats."""
        all_inbounds = await xui_client.inbounds_end.get_all()
        test_uuid = None
        for inb in all_inbounds:
            if inb.clientStats:
                test_uuid = inb.clientStats[0].uuid
                break
        if test_uuid is None:
            pytest.skip("No clients available for testing")
        clients = await xui_client.clients_end.get_client_with_uuid(test_uuid)
        assert isinstance(clients, list)
        assert all(isinstance(c, ClientStats) for c in clients)
