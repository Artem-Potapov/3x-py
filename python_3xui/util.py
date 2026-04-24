"""Utility functions and helpers for the VPNAPIHandler.

This module provides common utilities used across the API handler including:
- String conversion helpers (camelCase to snake_case)
- Async generators
- Base64 encoding utilities
- Telegram ID-based UUID/email generation
- Response validation
"""

import asyncio
import base64
import logging
import random
import re
from datetime import UTC, datetime, tzinfo
from typing import TypeAlias, Union, Dict, Any, List, dataclass_transform

import httpx

JsonType: TypeAlias = Union[Dict[Any, Any], List[Any]]

_RE_CAMEL_TO_SNAKE1 = re.compile("(.)([A-Z][a-z]+)")
_RE_CAMEL_TO_SNAKE2 = re.compile("([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    """Convert a camelCase string to snake_case.

    Args:
        name: The camelCase string to convert.

    Returns:
        The converted snake_case string.

    Examples:
        >>> camel_to_snake("camelCase")
        'camel_case'
        >>> camel_to_snake("XMLParser")
        'xml_parser'
    """
    name = re.sub(_RE_CAMEL_TO_SNAKE1, r"\1_\2", name)
    return re.sub(_RE_CAMEL_TO_SNAKE2, r"\1_\2", name).lower()


async def async_range(start, stop=None, step=1):
    """Async generator that yields values from a range.

    This is an async version of the built-in range() function that yields
    control back to the event loop between iterations.

    Args:
        start: The start value (or stop value if stop is None).
        stop: The stop value. If None, start is used as stop and 0 as start.
        step: The step increment between values.

    Yields:
        int: The next value in the range sequence.
    """
    if stop:
        range_ = range(start, stop, step)
    else:
        range_ = range(start)
    for i in range_:
        yield i
        await asyncio.sleep(0)


def base64_from_string(string: str, omit_trailing_equals: bool = False) -> str:
    """Encode a string to base64.

    Args:
        string: The input string to encode.
        omit_trailing_equals: If True, removes trailing '=' padding characters.

    Returns:
        The base64 encoded string.
    """
    return base64.b64encode(bytes(str(string).encode("utf-8"))).decode()


def sub_from_tgid(telegram_id: int) -> str:
    """Generate a subscription ID from a Telegram ID.

    Args:
        telegram_id: The Telegram user ID.

    Returns:
        A base64 encoded subscription ID derived from the Telegram ID.
    """
    return base64_from_string(str(telegram_id))


ensure_2_digits = lambda x: str(x) if x >= 10 else f"0{x}"


def get_uuid_from_tgid(telegram_id: int, fixed: bool = True) -> str:
    """Generate a UUID v4 format string from a Telegram ID.

    Creates a deterministic UUID based on the Telegram ID, useful for
    identifying clients across the VPN system.

    Args:
        telegram_id: The Telegram user ID.
        fixed: If True, uses a fixed prefix (11111111-1111-1111-1111-).
            If False, uses a timestamp-based prefix.

    Returns:
        A UUID-formatted string with the Telegram ID embedded in the last segment.

    Examples:
        >>> get_uuid_from_tgid(12345)
        '11111111-1111-1111-1111-0000000012345'
        >>> get_uuid_from_tgid(12345, fixed=False)  # Uses current timestamp
        '20260222-1230-1111-1111-0000000012345'
    """
    zeros = 12 - len(str(telegram_id))
    resid = f"{zeros * '0'}{telegram_id}"
    if fixed:
        return f"11111111-1111-1111-1111-{resid}"
    now = datetime.now(UTC)
    mon, day = ensure_2_digits(now.month), ensure_2_digits(now.day)
    hr, mn = ensure_2_digits(now.hour), ensure_2_digits(now.minute)
    return f"{now.year}{mon}{day}-{hr}{mn}-1111-1111-{resid}"


def generate_random_email(length: int = 8) -> str:
    """Generate a random alphanumeric email identifier.

    Args:
        length: The length of the generated email string.

    Returns:
        A random string of alphanumeric characters.

    Examples:
        >>> generate_random_email(8)  # Random output like 'aB3xY9zQ'
    """
    s = ""
    for i in range(length):
        s += random.choice("1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return s


def generate_email_from_tgid_inbid(telegram_id: int, /, inbound_id: int) -> str:
    """Generate a deterministic email from Telegram ID and inbound ID.

    Creates a unique email identifier that combines the Telegram ID and
    inbound ID, useful for tracking which inbound a client belongs to.

    Args:
        telegram_id: The Telegram user ID.
        inbound_id: The ID of the inbound connection.

    Returns:
        A formatted email string in the format 'TG{telegram_id}IB{inbound_id}'.

    Examples:
        >>> generate_email_from_tgid_inbid(12345, 3)
        'TG12345IB3'
    """
    return f"TG{telegram_id}IB{inbound_id}"


def generate_new_subscription(length: int = 16):
    """Generate a random subscription ID.

    Args:
        length: The length of the generated subscription string.

    Returns:
        A random alphanumeric string for use as a subscription ID.

    Examples:
        >>> generate_new_subscription(16)  # Random output like 'aB3xY9zQmNpL2kJh'
    """
    s = ""
    for i in range(length):
        s += random.choice("1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return s


async def check_xui_response(response: JsonType | httpx.Response) -> str:
    """Validate a 3X-UI API response.

    Checks if the response follows the expected 3X-UI API format with
    'success', 'msg', and 'obj' keys, and determines the response status.

    Args:
        response: Either a JSON response dict/list or an httpx Response object.

    Returns:
        str: One of three status strings:
            - "OK": Response is valid and successful.
            - "DB_LOCKED": Database is locked, operation should be retried.
            - "FAIL": Operation was unsuccessful.

    Raises:
        RuntimeError: If the response doesn't match the expected 3X-UI format.

    Examples:
        >>> check_xui_response({"success": True, "msg": "", "obj": {}})
        'OK'
        >>> check_xui_response({"success": False, "msg": "database is locked", "obj": None})
        'DB_LOCKED'
    """
    #TODO: this is trying to do too much. We'll just check if DB is locked, and then use case-to-case basis to see how they are.
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
            return "FAIL"
    raise RuntimeError("Validator got something very unexpected (Please don't shove responses with non-20X status codes in here...)")

def get_days_until_expiry(expiry_time: int) -> float:
    """Calculate the number of days until a client expires.

    Args:
        expiry_time: Client expiry time as UNIX timestamp (in seconds).

    Returns:
        Number of days until expiry. Returns negative value if already expired.
        Returns a very 0 if expiry_time is 0 (no expiry).

    Examples:
        >>> get_days_until_expiry(int(datetime.now(UTC).timestamp()) + 86400)  # 1 day from now
        1.0
        >>> get_days_until_expiry(0)  # No expiry
        inf
    """
    if expiry_time == 0:
        return 0

    current_timestamp = datetime.now(UTC).timestamp()
    seconds_remaining = expiry_time - current_timestamp
    days_remaining = seconds_remaining / 86400  # 86400 seconds in a day

    return days_remaining


class DBLockedError(Exception):
    """Exception raised when the 3X-UI database is locked.

    This exception is raised when an operation fails because the SQLite
    database used by 3X-UI is locked by another operation.
    """

    def __init__(self, message: str):
        """Initialize the DBLockedError.

        Args:
            message: Explanation of the error.
        """
        super().__init__(message)

def s_to_ms_timestamp(s: int|float) -> int:
    """Convert a UNIX timestamp in seconds to milliseconds."""
    return int(s * 1000)

def ms_to_s_timestamp(ms: int|float) -> int:
    """Convert a UNIX timestamp in milliseconds to seconds."""
    return ms // 1000

def auto_s_to_ms_timestamp(s_or_ms: int) -> int:
    """Automatically convert a UNIX timestamp to milliseconds if it's in seconds."""
    if s_or_ms < 1e12:  # If the timestamp is less than 1 trillion, it's likely in seconds
        return s_to_ms_timestamp(s_or_ms)
    return s_or_ms

def auto_ms_to_s_timestamp(ms_or_s: int) -> int:
    """Automatically convert a UNIX timestamp to seconds if it's in milliseconds."""
    if ms_or_s > 1e12:  # If the timestamp is greater than 1 trillion, it's likely in milliseconds
        return ms_to_s_timestamp(ms_or_s)
    return ms_or_s

def datetime_now_ms(tzinfo: tzinfo|None) -> int:
    """Get the current time as a UNIX timestamp in milliseconds."""
    return int(datetime.now(tzinfo).timestamp()) * 1000
