import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union, overload, Self, ClassVar, Annotated, Literal, Callable

import pydantic
import httpx
from functools import cached_property

import util

if TYPE_CHECKING:
    from api import XUIClient

class BaseModel(pydantic.BaseModel):
    """Base model for all 3X-UI API data models.

    Provides common functionality for parsing API responses and maintaining
    references to the XUIClient instance.

    Attributes:
        ERROR_RETRIES: Class variable for number of retry attempts on errors.
        ERROR_RETRY_COOLDOWN: Class variable for cooldown between retries in seconds.
    """
    ERROR_RETRIES: ClassVar[int] = 5
    ERROR_RETRY_COOLDOWN: ClassVar[int] = 1
    if TYPE_CHECKING:
        client: Annotated[XUIClient, pydantic.Field(exclude=True)]
    else:
        client: Annotated[Any, pydantic.Field(exclude=True)]

    model_config = pydantic.ConfigDict(ignored_types=(cached_property, ))

    def model_post_init(self, context: Any, /) -> None:
        print(f"Model {self.__class__}, {self} initialized")


    @classmethod
    def from_list(cls, args: List[Dict[str, Any]],
                  client: "XUIClient"
                  ) -> List[Self]:
        """Create a list of model instances from a list of dictionaries.

        Args:
            args: A list of dictionaries containing model data.
            client: The XUIClient instance to associate with each model.

        Returns:
            A list of model instances initialized with the provided data.

        Examples:
            inbounds = Inbound.from_list([{"id": 1}, {"id": 2}], client=xui_client)
        """
        return [cls(client=client, **obj) for obj in args]

    @classmethod
    async def from_response(
            cls,
            response: httpx.Response,
            client: "XUIClient",
            expect: list|dict,
            auto_retry: bool = True
    ) -> Union[Self, List[Self]]:
        """Create model instance(s) from an HTTP response.

        Parses the response JSON and creates model instance(s) based on the
        expected type. Handles automatic retry for database lock errors.

        Args:
            response: The httpx Response object from an API request.
            client: The XUIClient instance to associate with the model(s).
            expect: The expected type - either `list` or `dict`. Used to
                determine whether to parse a single object or a list.
            auto_retry: Whether to automatically retry on database lock errors.
                Defaults to True.

        Returns:
            Either a single model instance (if expect is dict) or a list of
            model instances (if expect is list).

        Raises:
            ValueError: If the response is invalid or the operation failed.

        Examples:
            inbound = await Inbound.from_response(response, client, dict)
            inbounds = await Inbound.from_response(response, client, list)
        """
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