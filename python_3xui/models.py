import json
from datetime import datetime, UTC
from typing import Union, TypeAlias, Any, Annotated, Literal, List, Dict, ClassVar

from pydantic import field_validator, Field, field_serializer
from typing_extensions import TypeVar

from . import base_model
from .util import JsonType, auto_s_to_ms_timestamp, auto_ms_to_s_timestamp

timestamp_seconds: TypeAlias = int
ip_address: TypeAlias = str
json_string: TypeAlias = str


def exclude_if_none(field) -> bool:
    """Check if a field value is None for exclusion purposes.

    Args:
        field: The field value to check.

    Returns:
        True if the field is None, False otherwise.
    """
    if field is None:
        return True
    return False


_IntNone = TypeVar("_IntNone", bound=int | None)


# noinspection PyNestedDecorators
class SingleInboundClient(base_model.BaseModel):
    """Represents a single client within a VLESS/VMess inbound.

    This model represents an individual VPN client with all its configuration
    settings including traffic limits, expiry, and authentication details.

    Attributes:
        uuid: The unique identifier for the client (aliased as 'id' in API).
        security: The security protocol used by the client.
        password: The client's password for authentication.
        flow: The VLESS flow type controlling connection behavior.
        email: The client's email identifier.
        limit_ip: Maximum number of simultaneous IP connections.
        limit_gb: Total data limit in gigabytes.
        expiry_time: Client expiry time as UNIX timestamp (0 = no expiry).
        enable: Whether the client is enabled.
        tg_id: Associated Telegram ID for notifications.
        subscription_id: Subscription identifier for URL generation.
        comment: Admin notes or comments for the client.
        created_at: Timestamp of client creation.
        updated_at: Timestamp of last client update.
    """
    TIME_FIELDS: ClassVar[List[str]] = ["expiry_time", "created_at", "updated_at"]
    uuid: Annotated[str, Field(alias="id")]  #yes they really did that...
    security: str = ""
    password: str = ""
    flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"]
    email: str
    limit_ip: Annotated[int, Field(alias="limitIp")] = 20
    reset: int = 0
    #Interestingly, the API expects this value to be called GB but it's actually bytes.
    # I want the pythonic side to be in GB (hence why floats, i.e. 2.5GB), but the API expects bytes.
    limit_gb: Annotated[int, Field(alias="totalGB")] = 0  # total flow
    expiry_time: Annotated[timestamp_seconds, Field(alias="expiryTime")] = 0
    enable: bool = True
    tg_id: Annotated[Union[int, str], Field(alias="tgId")] = ""
    subscription_id: Annotated[str, Field(alias="subId")]
    comment: str = ""
    created_at: Annotated[timestamp_seconds, Field(
        default_factory=(lambda: int(datetime.now(UTC).timestamp())))
    ]
    updated_at: Annotated[timestamp_seconds, Field(
        default_factory=(lambda: int(datetime.now(UTC).timestamp())))
    ]

    @field_validator(TIME_FIELDS[0], *TIME_FIELDS[1:], mode="after")
    @classmethod
    def ensure_s_timestamp(cls, value: _IntNone) -> _IntNone:
        return auto_ms_to_s_timestamp(value)

    @field_serializer(TIME_FIELDS[0], *TIME_FIELDS[1:])
    @classmethod
    def serialize_ms_timestamp(cls, value: int) -> int:
        return auto_s_to_ms_timestamp(value)

    @field_serializer("limit_gb")
    @classmethod
    def serialize_total_gb(cls, value: int) -> int:
        #API expects an integer of bytes.
        return value * (1024 ** 3)

    @field_validator("limit_gb", mode="after")
    @classmethod
    def parse_total_gb(cls, value: int) -> int:
        #Python wants an int/float of GB.
        return value // (1024 ** 3)


class ClientsSettings(base_model.BaseModel):
    """Settings container for inbound clients.

    Attributes:
        clients: List of SingleInboundClient objects.
    """
    clients: list[SingleInboundClient]
    decryption: Annotated[str, Field(exclude_if=lambda x: x == "none")] = "none"
    encryption: Annotated[str, Field(exclude_if=lambda x: x == "none")] = "none"
    fallbacks: Annotated[list | None, Field(exclude_if=exclude_if_none)] = None


class InboundClients(base_model.BaseModel):
    """Represents a collection of clients for an inbound connection.

    This model is used when adding or updating clients on an inbound,
    containing the parent inbound ID and the list of clients.

    Attributes:
        parent_id: The ID of the parent inbound (aliased as 'id').
        settings: The settings object containing the client list.
    """

    parent_id: Annotated[int | None, Field(exclude_if=exclude_if_none, alias="id")] = None
    settings: ClientsSettings

    @field_serializer("settings")
    def stringify_settings(self, value: ClientsSettings) -> str:
        """Serialize the settings object to a JSON string.

        The 3X-UI API expects settings as a JSON string, not an object.
        """
        return json.dumps(value.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)


#class InboundSettings(base_model.BaseModel):
#     clients: list[Clients]
#     decryption: str
#     encryption: str
#     selectedAuth: Annotated[Union[str|None], Field(exclude_if=exclude_if_none)] = None # "X25519, not Post-Quantum"
#
# "StreamSettings Stuff"
#
# class ExternalProxy(base_model.BaseModel):
#     force_tls: Annotated[str, Field(alias="ForceTls")]
#     dest: str
#     port: int
#     remark: str
#
# class StreamRequest(base_model.BaseModel):
#     version: str
#     method: str
#     path: List[str]
#     headers: dict[str, str|int]
#
# class StreamResponse(base_model.BaseModel):
#     version: str
#     status: int
#     reason: str
#     headers: dict[str, str|int]
#
# class TCPSettingsHeader(base_model.BaseModel):
#     type: str
#     request: Annotated[Optional[StreamRequest], Field(exclude_if=exclude_if_none)] = None
#     response: Annotated[Optional[StreamRequest], Field(exclude_if=exclude_if_none)] = None
#
# class TCPSettings(base_model.BaseModel):
#     accept_proxy_protocol: Annotated[bool, Field(alias="acceptProxyProtocol")]
#
# class SockOpt(base_model.BaseModel):
#     acceptProxyProtocol: bool
#     tcpFastOpen: bool
#     mark: int
#     tproxy: str
#     tcpMptcp: bool
#     penetrate: bool
#     domainStrategy: str
#     tcpMaxSeg: int
#     dialerProxy: str
#     tcpKeepAliveInterval: int
#     tcpKeepAliveIdle: int
#     tcpUserTimeout: int
#     tcpcongestion: str
#     V6Only: bool
#     tcpWindowClamp: int
#     interface: str
#
# class StreamSettings(base_model.BaseModel):
#     network_type: Annotated[str, Field(alias="network")]
#     security: str # none, reality, TLS
#     external_proxy: Annotated[list[ExternalProxy], Field(alias="externalProxy")]
#     tcp_settings: TCPSettings

# noinspection PyNestedDecorators
class ClientStats(base_model.BaseModel):
    """Statistics and configuration for a VPN client.

    This model represents client statistics returned by the 3X-UI API,
    including traffic usage, expiry information, and connection details.

    Attributes:
        id: Internal database ID of the client record.
        inboundId: The ID of the inbound this client belongs to.
        enable: Whether the client is currently enabled.
        email: The client's email identifier.
        uuid: The client's unique identifier.
        subId: The subscription ID for URL generation.
        up: Total uploaded bytes.
        down: Total downloaded bytes.
        allTime: Total bytes transferred (up + down).
        expiryTime: Client expiry time as a UNIX timestamp in seconds on the
            Python model, serialized to milliseconds for the API.
        total: Total data limit in bytes.
        reset: Counter for traffic resets.
        lastOnline: UNIX timestamp of last connection in seconds on the
            Python model, serialized to milliseconds for the API.
    """
    TIME_FIELDS: ClassVar[List[str]] = ["expiryTime", "lastOnline"]
    id: int
    inboundId: int
    enable: bool
    email: str
    uuid: str
    subId: str
    up: int  # bytes
    down: int  # bytes
    allTime: int  # bytes
    expiryTime: timestamp_seconds  # UNIX timestamp
    total: int
    reset: int
    lastOnline: timestamp_seconds

    @field_validator(TIME_FIELDS[0], *TIME_FIELDS[1:], mode="after")
    @classmethod
    def ensure_s_timestamp(cls, value: int) -> int:
        return auto_ms_to_s_timestamp(value)

    @field_serializer(TIME_FIELDS[0], *TIME_FIELDS[1:])
    @classmethod
    def serialize_ms_timestamp(cls, value: int) -> int:
        return auto_s_to_ms_timestamp(value)


# noinspection PyNestedDecorators
class Inbound(base_model.BaseModel):
    """Represents a VPN inbound connection configuration.

    An inbound defines how VPN clients connect to the server, including
    the protocol, port, traffic statistics, and client list.

    Attributes:
        id: The unique identifier for this inbound.
        up: Total uploaded bytes through this inbound.
        down: Total downloaded bytes through this inbound.
        total: Total data limit in bytes.
        allTime: Total bytes transferred (up + down).
        remark: Human-readable name/description for the inbound.
        enable: Whether the inbound is currently enabled.
        expiryTime: Inbound expiry time as UNIX timestamp.
        trafficReset: Traffic reset schedule ("Never", "Weekly", "Monthly", "Daily").
        lastTrafficResetTime: UNIX timestamp of last traffic reset.
        clientStats: List of client statistics, or None if no clients.
        listen: The IP address the inbound listens on.
        port: The port number the inbound listens on.
        protocol: The VPN protocol (vless, vmess, trojan, shadowsocks, wireguard).
        settings: JSON configuration for the inbound (auto-parsed from string).
        streamSettings: JSON stream configuration (auto-parsed from string).
        tag: Internal tag identifier for routing.
        sniffing: JSON sniffing configuration (auto-parsed from string).
    """
    TIME_FIELDS: ClassVar[List[str]] = ["expiryTime", "lastTrafficResetTime"]
    id: int
    up: int  # bytes
    down: int  # bytes
    total: int  # bytes
    allTime: int  # bytes
    remark: str
    enable: bool
    expiryTime: timestamp_seconds  # UNIX timestamp
    trafficReset: str  # "Never", "Weekly", "Monthly", "Daily"
    lastTrafficResetTime: timestamp_seconds  # UNIX timestamp
    clientStats: list[ClientStats] | None
    listen: str
    port: int
    #TODO: add trojan, shadowsocks, wireguard back in when they are supported by the API
    protocol: Literal["vless", "vmess"]  #"trojan", "shadowsocks", "wireguard"]  # note: there are some "deprecated" like wireguard
    settings: ClientsSettings  # JSON packed value, stringified
    streamSettings: Union[json_string, Dict[Any, Any]]  # JSON packed value, stringified
    tag: str
    sniffing: Union[json_string, Dict[Any, Any]]  # JSON packed value, stringified

    @field_validator("settings", mode="before")
    @classmethod
    def parse_settings(cls, value: str) -> ClientsSettings:
        if value == "":
            return ClientsSettings(clients=[])
        return ClientsSettings.model_validate_json(value, by_alias=True, extra="ignore")

    @field_serializer("settings")
    @classmethod
    def dump_settings(cls, value: ClientsSettings) -> str:
        return value.model_dump_json(by_alias=True)

    @field_validator('streamSettings', 'sniffing', mode='after')
    @classmethod
    def parse_json_fields(cls, value: str) -> JsonType | Literal[""]:
        """Parse JSON string fields into dictionaries.

        The 3X-UI API returns settings, streamSettings, and sniffing as
        JSON strings. This validator automatically parses them into dicts.
        """
        if value == "":
            return ""
        return json.loads(value)

    @field_serializer("streamSettings", "sniffing")
    @classmethod
    def stringify_json_fields(cls, value: Dict | Literal[""]) -> str:
        """Serialize dictionary fields back to JSON strings.

        When sending data back to the API, these fields must be JSON strings.
        """
        if value == "":
            return ""
        return json.dumps(value, ensure_ascii=False)

    @field_validator(TIME_FIELDS[0], *TIME_FIELDS[1:], mode="after")
    @classmethod
    def ensure_s_timestamp(cls, value: int) -> int:
        return auto_ms_to_s_timestamp(value)

    @field_serializer(TIME_FIELDS[0], *TIME_FIELDS[1:])
    @classmethod
    def serialize_ms_timestamp(cls, value: int) -> int:
        return auto_s_to_ms_timestamp(value)
