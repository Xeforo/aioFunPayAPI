from typing import Literal
from pydantic import BaseModel

class Subcategory(BaseModel):
    id: int
    name: str
    type: Literal["lots", "chips"]
    url: str
    game_title: str
 
class Category(BaseModel):
    id: int
    game_title: str
    subcategories: list[Subcategory]
    url: str

class Contact(BaseModel):
    node_id: int
    last_message_id: int
    last_read_message_id: int
    avatar: str
    username: str
    last_message_text: str
    last_message_time: str

class ChatBookmarkMessage(BaseModel):
    chat_url: str
    node_id: int
    last_message_id: int
    last_read_message_id: int
    avatar: str
    username: str
    text: str
    time: str
    unread: bool
    