import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv("../.env")

# API configuration from environment
BASE_URL = os.getenv("BASE_URL")
PORT = os.getenv("PORT")
BASE_PATH = os.getenv("BASE_PATH")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")

# Construct base URL
BASE_API_URL = f"https://{BASE_URL}:{PORT}{BASE_PATH}"
LOGIN_URL = f"{BASE_API_URL}/login"

# Test constants for non-idempotent operations
TEST_INBOUND_ID = 25
TEST_CLIENT_EMAIL = "qndfils7"
TEST_CLIENT_UUID = "161b1f51-d027-4dcc-9e13-573cf6c9353a"

# Output directory for stub files
RESPONSE_STUBS_DIR = Path(__file__).parent / "response_stubs"


class APIResponseGatherer:
    """Helper class to gather and save API responses."""

    def __init__(self):
        self.session = requests.Session()
        self.responses = {}

    def login(self) -> bool:
        """
        Authenticate with the 3x-ui API and save session cookies.

        Returns:
            True if login was successful, False otherwise.
        """
        payload = {
            "username": XUI_USERNAME,
            "password": XUI_PASSWORD,
        }
        try:
            response = self.session.post(LOGIN_URL, data=payload)
            response.raise_for_status()
            resp_json = response.json()
            if resp_json.get("success"):
                print(f"Logged in successfully as {XUI_USERNAME}")
                return True
            else:
                print(f"✗ Login failed: {resp_json.get('msg', 'Unknown error')}")
                return False
        except requests.RequestException as e:
            print(f"✗ Login request failed: {e}")
            return False

    def get_endpoint(self, endpoint: str, method: str = "GET",
                     params: dict = None, json_data: dict = None,
                     data: dict = None) -> dict | None:
        """
        Make a request to an API endpoint and return the JSON response.

        Args:
            endpoint: API endpoint (without base URL)
            method: HTTP method (GET, POST, etc.)
            params: URL parameters for GET requests
            json_data: JSON body for POST requests
            data: Form data for POST requests

        Returns:
            Response JSON or None if request failed.
        """
        url = f"{BASE_API_URL}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, json=json_data, data=data)
            else:
                print(f"✗ Unsupported HTTP method: {method}")
                return None

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"✗ Request to {endpoint} failed: {e}")
            return None

    @staticmethod
    def save_stub(filename: str, data: dict | list | None) -> bool:
        """
        Save API response to a JSON file in the response_stubs directory.

        Args:
            filename: Name of the file (without .json extension)
            data: JSON data to save

        Returns:
            True if save was successful, False otherwise.
        """
        if data is None:
            print(f"✗ No data to save for {filename}")
            return False

        filepath = RESPONSE_STUBS_DIR / f"{filename}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Saved {filename}.json")
            return True
        except IOError as e:
            print(f"✗ Failed to save {filename}.json: {e}")
            return False

    def gather_all_responses(self):
        """Gather responses from all implemented endpoints in endpoints.py"""

        if not self.login():
            print("Cannot proceed without authentication")
            return

        print("\n" + "="*60)
        print("Gathering Server endpoint responses...")
        print("="*60)

        # Server endpoints
        server_uuid = self.get_endpoint("panel/api/server/getNewUUID")
        if server_uuid:
            self.save_stub("server_new_uuid", server_uuid)

        server_x25519 = self.get_endpoint("panel/api/server/getNewX25519Cert")
        if server_x25519:
            self.save_stub("server_new_x25519", server_x25519)

        server_mldsa65 = self.get_endpoint("panel/api/server/getNewmldsa65")
        if server_mldsa65:
            self.save_stub("server_new_mldsa65", server_mldsa65)

        server_mlkem768 = self.get_endpoint("panel/api/server/getNewmlkem768x")
        if server_mlkem768:
            self.save_stub("server_new_mlkem768", server_mlkem768)

        print("\n" + "="*60)
        print("Gathering Inbounds endpoint responses...")
        print("="*60)

        # Inbounds endpoints
        all_inbounds = self.get_endpoint("panel/api/inbounds/list")
        if all_inbounds:
            self.save_stub("inbounds_get_all", all_inbounds)

        specific_inbound = self.get_endpoint(f"panel/api/inbounds/get/{TEST_INBOUND_ID}")
        if specific_inbound:
            self.save_stub("inbounds_get_specific", specific_inbound)

        print("\n" + "="*60)
        print("Gathering Clients endpoint responses...")
        print("="*60)

        # Clients - read operations (GET)
        client_by_email = self.get_endpoint(f"panel/api/inbounds/getClientTraffics/{TEST_CLIENT_EMAIL}")
        if client_by_email:
            self.save_stub("clients_get_by_email", client_by_email)

        client_by_uuid = self.get_endpoint(f"panel/api/inbounds/getClientTrafficsById/{TEST_CLIENT_UUID}")
        if client_by_uuid:
            self.save_stub("clients_get_by_uuid", client_by_uuid)

        # Clients - write operations (POST)
        print("\n" + "-"*60)
        print("Creating test client...")
        add_client_response = self._add_test_client()
        if add_client_response:
            self.save_stub("clients_add_client", add_client_response)

        print("\n" + "-"*60)
        print("Updating test client...")
        update_client_response = self._update_test_client()
        if update_client_response:
            self.save_stub("clients_update_single_client", update_client_response)

        print("\n" + "-"*60)
        print("Deleting expired clients...")
        delete_expired_response = self.get_endpoint(
            f"panel/api/inbounds/delDepletedClients/{TEST_INBOUND_ID}",
            method="POST"
        )
        if delete_expired_response:
            self.save_stub("clients_delete_expired", delete_expired_response)

        print("\n" + "-"*60)
        print("Deleting test client by email...")
        delete_by_email_response = self.get_endpoint(
            f"panel/api/inbounds/{TEST_INBOUND_ID}/delClientByEmail/{TEST_CLIENT_EMAIL}",
            method="POST"
        )
        if delete_by_email_response:
            self.save_stub("clients_delete_by_email", delete_by_email_response)

        # Re-add for UUID deletion test
        print("\n" + "-"*60)
        print("Re-adding test client for UUID deletion test...")
        self._add_test_client()

        print("\n" + "-"*60)
        print("Deleting test client by UUID...")
        delete_by_uuid_response = self.get_endpoint(
            f"panel/api/inbounds/{TEST_INBOUND_ID}/delClient/{TEST_CLIENT_UUID}",
            method="POST"
        )
        if delete_by_uuid_response:
            self.save_stub("clients_delete_by_uuid", delete_by_uuid_response)

        print("\n" + "="*60)
        print("Stub gathering complete!")
        print("="*60)

    def _add_test_client(self) -> dict | None:
        """
        Helper method to add a test client to the test inbound.
        Returns the API response.
        """
        from datetime import datetime, UTC

        client_data = {
            "id": TEST_INBOUND_ID,
            "settings": json.dumps({
                "clients": [
                    {
                        "id": TEST_CLIENT_UUID,
                        "flow": "",
                        "email": TEST_CLIENT_EMAIL,
                        "limitIp": 0,
                        "totalGB": 0,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": "test_subscription_id",
                        "comment": f"Test client created at {datetime.now(UTC)}",
                        "reset": 0
                    }
                ]
            })
        }
        return self.get_endpoint(
            f"panel/api/inbounds/addClient",
            method="POST",
            data=client_data
        )

    def _update_test_client(self) -> dict | None:
        """
        Helper method to update the test client.
        Returns the API response.
        """
        update_data = {
            "id": TEST_INBOUND_ID,
            "settings": json.dumps({
                "clients": [
                    {
                        "id": TEST_CLIENT_UUID,
                        "flow": "xtls-rprx-vision",
                        "email": TEST_CLIENT_EMAIL,
                        "limitIp": 5,
                        "totalGB": 10,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": "test_subscription_id",
                        "comment": "Test client updated",
                        "reset": 0
                    }
                ]
            })
        }
        return self.get_endpoint(
            f"panel/api/inbounds/updateClient/{TEST_CLIENT_UUID}",
            method="POST",
            data=update_data
        )


def main():
    """Main entry point."""
    print("3x-UI API Response Stub Gatherer")
    print("=" * 60)
    print(f"API Base URL: {BASE_API_URL}")
    print(f"Output Directory: {RESPONSE_STUBS_DIR}")
    print()

    # Ensure output directory exists
    RESPONSE_STUBS_DIR.mkdir(parents=True, exist_ok=True)

    # Gather responses
    gatherer = APIResponseGatherer()
    gatherer.gather_all_responses()


if __name__ == "__main__":
    main()

