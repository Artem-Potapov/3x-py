import asyncio
import logging

import dotenv
import os

from python_3xui.api import XUIClient
from python_3xui.models import SingleInboundClient, InboundClients, ClientsSettings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
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


async def main():
    async with XUIClient(BASE_URL, PORT, BASE_PATH,
                         username=XUI_USERNAME,
                         password=XUI_PASSWORD,
                         two_fac_code=TWOFA_CODE,
                         custom_prod_string="test3") as client:
        ib = SingleInboundClient(id="wwww", flow="", email="uwu", subId="uwu")
        #up = ClientUpdatePayload(id="swdawdwa", email="dwavwafa")
        uwu = InboundClients(id=7, settings=ClientsSettings(clients=[ib]))
        print(uwu.model_dump_json(exclude_none=True, by_alias=True))
        await client.clients_end.update_single_client(
            7, "9999", email="Pomenyalos", security="", password="",
            flow="", limit_ip=20, limit_gb=20, expiry_time=17777777777,
            enable=True, sub_id="uwu", comment="Сработает ли?")


if __name__ == "__main__":
    asyncio.run(main())