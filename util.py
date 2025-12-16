import logging
import re
from typing import TypeAlias, Union, Dict, Any, List
import httpx

JsonType: TypeAlias = Union[Dict[Any, Any], List[Any]]


_RE_CAMEL_TO_SNAKE1 = re.compile("(.)([A-Z][a-z]+)")
_RE_CAMEL_TO_SNAKE2 = re.compile("([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    name = re.sub(_RE_CAMEL_TO_SNAKE1, r"\1_\2", name)
    return re.sub(_RE_CAMEL_TO_SNAKE2, r"\1_\2", name).lower()

async def check_xui_response_validity(response: JsonType) -> str:
    json_resp = response
    if len(json_resp) == 3:
        if tuple(json_resp.keys()) == ("success", "msg", "obj"):
            success: bool = json_resp["success"]
            msg: str = json_resp["msg"]
            obj: JsonType = json_resp["obj"]
            if success:
                return "OK"
            if "database" in msg.lower() and "locked" in msg.lower() and not success:
                logging.log(logging.WARNING, "Database is locked, retrying...")
                return "DB_LOCKED"
    return "ERROR"

class DBLockedError(Exception):
    def __init__(self, message):
        super().__init__(message)