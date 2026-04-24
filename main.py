import asyncio
import datetime
import json
import logging

import httpx
import dotenv, os

from python_3xui.api import XUIClient
from python_3xui.models import Inbound, SingleInboundClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

dotenv.load_dotenv("./.env")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT"))
BASE_PATH = os.getenv("BASE_PATH")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")
TWOFA_CODE = os.getenv("XUI_2FA_SECRET")

base_url = f"https://{BASE_URL}:{PORT}/{BASE_PATH}"
data = {
    "username": XUI_USERNAME,
    "password": XUI_PASSWORD
}

# a = requests.post(f"{base_url}/login/", data=data)
#
# print(a.status_code)
# print(a.cookies["3x-ui"])
# print(a.json())

#b = requests.get(f"{base_url}/panel/api/inbounds/list", cookies=cookies)

async def create_client(telegram_id: int):
    """
    for inb in all_needeed_inbounds:
        inb.add_client(uuid, blahblahblah)
    """

async def main():
    async with XUIClient(BASE_URL, PORT, BASE_PATH,
                         username=XUI_USERNAME,
                         password=XUI_PASSWORD,
                         two_fac_code=TWOFA_CODE,
                         custom_prod_string="test3") as client:
        await client.create_and_add_prod_client(128124812, "help me")
        await asyncio.sleep(2)
        print("INB CREATED")
        await client.revoke_client_by_tgid_all_inbounds(128124812)
        while True:
            await asyncio.sleep(1)
            print("epstein")

if __name__ == "__main__":
    asyncio.run(main())