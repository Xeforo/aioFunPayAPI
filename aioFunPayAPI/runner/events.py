from selectolax.lexbor import LexborHTMLParser
from pydantic import BaseModel
from typing import Any, Literal, Union

class ChatBookmarksEvent(BaseModel):
    counter: int
    message_id: int
    order: list[int]
    html: str

class Event(BaseModel):
    type: Literal["chat_bookmarks"]
    account_id: int
    tag: str
    data: Union[Any, Any]