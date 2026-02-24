import asyncio
import json

import httpx
import requests
import dotenv, os

from python_3xui.api import XUIClient
from python_3xui.models import Inbound, SingleInboundClient

dotenv.load_dotenv("./.env")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT"))
BASE_PATH = os.getenv("BASE_PATH")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")

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

class ResponseStub(requests.Response):
    def __init__(self, js):
        self.js = js

    def json(self):
        return self.js


async def create_client(telegram_id: int):
    """
    for inb in all_needeed_inbounds:
        inb.add_client(uuid, blahblahblah)
    """

async def main():
    async with XUIClient(BASE_URL, PORT, BASE_PATH,
                         xui_username=XUI_USERNAME,
                         xui_password=XUI_PASSWORD) as client:
        await client.create_and_add_prod_client(128124812, "help me")
        await asyncio.sleep(2)
        print("INB CREATED")
        await client.delete_client_by_tgid_all_inbounds(128124812)
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())