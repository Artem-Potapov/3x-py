from typing import Generic, Type

from pydantic.main import ModelT

from api import XUIClient
from util import camel_to_snake
from pydantic_models import Inbound


class BaseEndpoint(Generic[ModelT]):
    _model: Type[ModelT]
    _url: str

    def __init__(self, client: "XUIClient") -> None:
        self.client = client



class Inbounds(BaseEndpoint):
    _model = Inbound
    _url = "/panel/api/inbounds"

    async def get(self):
        endpoint = "/list"
