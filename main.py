import json

import requests
import dotenv, os
from pydantic_models import Inbound

dotenv.load_dotenv("./.env")
BASE_URL = os.getenv("BASE_URL")
PORT = os.getenv("PORT")
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

with open("response_stub.json", "r", encoding="utf-8") as file:
    b = ResponseStub(json.load(file))

print(b.json())
res: list[dict] = b.json()["obj"]
ob = res[0]
print(ob)

uwu = Inbound.from_response(b, list)
print(uwu)
