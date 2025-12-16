import asyncio
import os
import dotenv
import httpx

dotenv.load_dotenv("./.env")
BASE_URL = os.getenv("BASE_URL")
PORT = os.getenv("PORT")
BASE_PATH = os.getenv("BASE_PATH")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")

async def main():
    client = httpx.AsyncClient()

    data = {
        "username": XUI_USERNAME,
        "password": XUI_PASSWORD,
    }
    uwu = await client.post(f"https://{BASE_URL}:{PORT}/{BASE_PATH}/login",
                            follow_redirects=True, data=data)
    print(uwu)
    print(uwu.__dict__)
    print(type(uwu))
    print(uwu.json())

    async def uwu2():
        r = await client.get(f"https://{BASE_URL}:{PORT}/{BASE_PATH}/panel/api/inbounds/list")
        print("uwu2", r.json())

    async def uwu3():
        r = await client.get(f"https://{BASE_URL}:{PORT}/{BASE_PATH}/panel/api/inbounds/get/4")
        print("uwu3", r.json())

    asyncio.create_task(uwu2())
    asyncio.create_task(uwu3())
    asyncio.create_task(uwu3())


    await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())