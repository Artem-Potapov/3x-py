import datetime
import json
from pydantic import field_validator, Field, field_serializer

import base_model
import pydantic
from types import NoneType
from typing import Union, Optional, TypeAlias, Any, Annotated, Literal, List, Dict

from util import JsonType

timestamp: TypeAlias = int
ip_address: TypeAlias = str
json_string: TypeAlias = str

def exclude_if_none(field) -> bool:
    if field is None:
        return True
    return False

class SingleInboundClient(pydantic.BaseModel):
    id: str #uuid
    security: str = ""
    password: str = ""
    flow: Literal["", "xtls-rprx-vision", "xtls-rprx-vision-udp443"]
    description: Annotated[str, Field(alias="email")]
    limit_ip: Annotated[int, Field(alias="limitIp")] = 20
    limit_gb: Annotated[int, Field(alias="totalGB")] # total flow
    expiry_time: Annotated[timestamp, Field(alias="expiryTime")]
    enable: bool
    tg_id: Annotated[Union[int, str], Field(alias="tgId")] = ""
    subscription_id: Annotated[str, Field(alias="subId")]
    comment: str
    created_at: Annotated[timestamp, Field(default_factory=(lambda: int(datetime.datetime.now().timestamp())))]
    updated_at: Annotated[timestamp, Field(default_factory=(lambda: int(datetime.datetime.now().timestamp())))]

class InboundClients(pydantic.BaseModel):
    class Settings(pydantic.BaseModel):
        clients: list[SingleInboundClient]

    parent_id: Annotated[int|None, Field(exclude_if=exclude_if_none, alias="id")] = None
    settings: Settings


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





class ClientStats(base_model.BaseModel):
    id: int
    inboundId: int
    enable: bool
    email: str
    uuid: str
    subId: str
    up: int  # bytes
    down: int  # bytes
    allTime: int  # bytes
    expiryTime: timestamp  # UNIX timestamp
    total: int
    reset: int
    lastOnline: timestamp


class Inbound(base_model.BaseModel):
    id: int
    up: int  # bytes
    down: int  # bytes
    total: int  # bytes
    allTime: int  # bytes
    remark: str
    enable: bool
    expiryTime: timestamp  # UNIX timestamp
    trafficReset: str  # "Never", "Weekly", "Monthly", "Daily"
    lastTrafficResetTime: timestamp  # UNIX timestamp
    clientStats: Union[list[ClientStats], None]
    listen: str
    port: int
    protocol: Literal["vless", "vmess", "trojan", "shadowsocks"]  # note: there are some "deprecated" like wireguard
    settings: Union[json_string, Dict[Any, Any]]  # JSON packed value, stringified
    streamSettings: Union[json_string, Dict[Any, Any]]  # JSON packed value, stringified
    tag: str
    sniffing: Union[json_string, Dict[Any, Any]]  # JSON packed value, stringified

    # noinspection PyNestedDecorators
    @field_validator('settings', 'streamSettings', 'sniffing', mode='after')
    @classmethod
    def parse_json_fields(cls, value: str) -> JsonType:
        return json.loads(value)

    # noinspection PyNestedDecorators
    @field_serializer("settings", "streamSettings", "sniffing")
    @classmethod
    def stringify_json_fields(cls, value: Dict):
        return json.dumps(value, ensure_ascii=False)


# file = open("./lalala/tripi.json", "r")
# a = json.load(file)
# cl1 = InboundClients.model_validate(a)
# cl1.parent_id = 4
# print(cl1.model_dump_json(by_alias=True))
# file.close()