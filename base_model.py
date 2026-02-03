import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union, overload, Self, ClassVar, Annotated, Literal, Callable

import pydantic
import httpx
from functools import cached_property

from pydantic import model_validator
from pydantic.main import IncEx
from pydantic_core.core_schema import ValidationInfo

import util

if TYPE_CHECKING:
    from api import XUIClient

class BaseModel(pydantic.BaseModel):
    ERROR_RETRIES: ClassVar[int] = 5
    ERROR_RETRY_COOLDOWN: ClassVar[int] = 1
    if TYPE_CHECKING:
        ...#client: Annotated[XUIClient, pydantic.Field(exclude=True)]
    else:
        ...#client: Annotated[Any, pydantic.Field(exclude=True)]

    model_config = pydantic.ConfigDict(ignored_types=(cached_property, ))

    def model_post_init(self, context: Any, /) -> None:
        print(f"Model {self.__class__}, {self} inititalized")


    @classmethod
    def from_list(cls, args: List[Dict[str, Any]],
                  client: "XUIClient"
                  ) -> List[Self]:
        uwu = []
        for obj in args:
            tmp = cls(client=client, **obj) #I give up
            uwu.append(tmp)
        return uwu

    @classmethod
    async def from_response(
            cls,
            response: httpx.Response,
            client: "XUIClient",
            expect: list|dict,
            auto_retry: bool = True
    ) -> Union[Self, List[Self]]:
        """If you want to make out a list or dict, please pass an example"""


        json_resp: util.JsonType = response.json()
        valid = util.check_xui_response_validity(json_resp)
        if valid == "OK":
            obj = json_resp["obj"]
            if expect is list:
                return cls.from_list(obj, client=client)
            if expect is dict:
                return cls(**obj, client=client)
        else:
            raise ValueError(f"Invalid 3X-UI response, code {valid}")


uwu = BaseModel(client="121")
uwu2 = BaseModel.from_list([{}], client="121")
print(uwu2[0].model_dump_json())