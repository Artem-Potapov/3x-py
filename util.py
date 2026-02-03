import asyncio
import base64
import logging
import random
import re
from datetime import UTC, datetime
from typing import TypeAlias, Union, Dict, Any, List, overload
import httpx

JsonType: TypeAlias = Union[Dict[Any, Any], List[Any]]

_RE_CAMEL_TO_SNAKE1 = re.compile("(.)([A-Z][a-z]+)")
_RE_CAMEL_TO_SNAKE2 = re.compile("([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    name = re.sub(_RE_CAMEL_TO_SNAKE1, r"\1_\2", name)
    return re.sub(_RE_CAMEL_TO_SNAKE2, r"\1_\2", name).lower()


async def async_range(start, stop=None, step=1):
    if stop:
        range_ = range(start, stop, step)
    else:
        range_ = range(start)
    for i in range_:
        yield i
        await asyncio.sleep(0)


def base64_from_string(string: str, omit_trailing_equals: bool = False) -> str:
    return base64.b64encode(bytes(str(string).encode("utf-8"))).decode()


def sub_from_tgid(telegram_id: int) -> str:
    return base64_from_string(str(telegram_id))


ensure_2_digits = lambda x: str(x) if x >= 10 else f"0{x}"


def new_telegram_uuid(telegram_id: int, fixed: bool = True) -> str:
    zeros = 12 - len(str(telegram_id))
    resid = f"{zeros * '0'}{telegram_id}"
    if fixed:
        return f"11111111-1111-1111-1111-{resid}"
    now = datetime.now(UTC)
    mon, day = ensure_2_digits(now.month), ensure_2_digits(now.day)
    hr, mn = ensure_2_digits(now.hour), ensure_2_digits(now.minute)
    return f"{now.year}{mon}{day}-{hr}{mn}-1111-1111-{resid}"


def generate_random_email(length: int = 8) -> str:
    s = ""
    for i in range(length):
        s += random.choice("1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return s


def generate_email_from_tgid_inbid(telegram_id: int, inbound_id: int) -> str:
    return f"TG{telegram_id}IB{inbound_id}"


def generate_new_subscription(length: int = 16):
    s = ""
    for i in range(length):
        s += random.choice("1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return s


async def check_xui_response_validity(response: JsonType | httpx.Response) -> str:
    if isinstance(response, httpx.Response):
        json_resp = response.json()
    else:
        json_resp = response

    if len(json_resp) == 3:
        if tuple(json_resp.keys()) == ("success", "msg", "obj"):
            success: bool = json_resp["success"]
            msg: str = json_resp["msg"]
            if success:
                return "OK"
            if "database" in msg.lower() and "locked" in msg.lower() and not success:
                logging.log(logging.WARNING, "Database is locked, retrying...")
                return "DB_LOCKED"
            print(f"Unsuccessful operation! Message: {json_resp["msg"]}")
            return "ERROR"
    raise RuntimeError("Validator got something very unexpected (Please don't shove responses with non-20X status codes in here...)")


class DBLockedError(Exception):
    def __init__(self, message):
        super().__init__(message)
