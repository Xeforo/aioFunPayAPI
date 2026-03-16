from asyncio import get_running_loop
from typing import Optional, Dict, Literal, Any, Union
from httpx import Cookies, Proxy, AsyncClient, Response

from .types import ChatNode, Contact

from .common.config import BASE_URL, USER_AGENT
from .common.parser import parse_account_data, parse_chat_node, parse_contacts, parser_executor

 
class Account:
    def __init__(self, golden_key: str, proxy: Optional[str] = None):
        self.golden_key: Optional[str] = golden_key
        self.proxy: Optional[str] = proxy
        self.phpsessid: Optional[str] = None
        self.csrf_token: Optional[str] = None

        self.username: Optional[str] = None
        self.balance: Optional[float] = None
        self.locale: Optional[str] = None
        self.user_id: Optional[int] = None

        self._client: Optional[AsyncClient] = None

    async def _get_client(self) -> AsyncClient:
        cookies = Cookies()
        if self.golden_key:
            cookies.set("golden_key", self.golden_key)
        proxy = Proxy(self.proxy) if self.proxy else None
        
        if self._client is None:
            self._client = AsyncClient(
                base_url=BASE_URL,
                headers={"User-Agent": USER_AGENT},
                cookies=cookies,
                proxy=proxy,
            )
        return self._client

    async def _method(self, method: Literal["get", "post"], url: str, headers: Optional[Dict[str, str]] = None, 
                     data: Optional[Dict[str, Any]] = None) -> Response:

        client = await self._get_client()
        response = await client.request(method, url, headers=headers, data=data)
        return response

    async def get(self) -> Account:
        response = await self._method("get", "/")
        self.phpsessid = response.cookies.get("PHPSESSID")

        loop = get_running_loop()
        parsed_data = await loop.run_in_executor(parser_executor, parse_account_data, response.text)

        if parsed_data is None:
            return self

        self.username, self.balance, app_data = parsed_data

        if app_data:
            self.locale = app_data.get("locale")
            self.user_id = app_data.get("userId")
            self.csrf_token = app_data.get("csrf-token")

        return self

    async def get_contacts(self) -> list[Contact]:
        response = await self._method("get", "/chat/")
        loop = get_running_loop()
        contacts = await loop.run_in_executor(parser_executor, parse_contacts, response.text)
        return contacts

    async def get_contact(self, contact: Union[int, str]) -> Optional[Contact]:
        contacts = await self.get_contacts()

        if isinstance(contact, int):
            for c in contacts:
                if c.node_id == contact:
                    return c

        for c in contacts:
            if c.username == contact:
                return c
        return None
    
    async def get_chat_node(self, node_id: int) -> ChatNode:
        response = await self._method("get", f"/chat/?node={node_id}")
        loop = get_running_loop()
        chat_data = await loop.run_in_executor(parser_executor, parse_chat_node, response.text)
        return chat_data