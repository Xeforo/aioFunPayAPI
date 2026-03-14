import asyncio

from json import dumps
from typing import Callable, Any, Coroutine, Dict, List, Optional, Literal
from httpx import AsyncClient, Proxy, Cookies

from ..account import Account
from ..common.config import BASE_URL, USER_AGENT
from ..common.parser import parser_executor, parse_chat_bookmarks


Handler = Callable[..., Coroutine[Any, Any, None]]

class Runner:
    def __init__(self, account: Account):
        self._handlers: Dict[str, List[tuple[Handler, Optional[Callable[[Any], bool]]]]] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._client: Optional[AsyncClient] = None

        self._chat_bookmarks_data: Optional[list[list[int]]] = []
        self._chat_nodes_data: Dict[int, str] = {}

        self.account: Account = account
        self.proxy: Optional[str] = account.proxy

        self._orders_counters_tag: str = "HelloFP!"
        self._chat_bookmarks_tag: str = "HelloFP!"

    async def _get_client(self) -> AsyncClient:
        cookies = Cookies()
        cookies.set("golden_key", self.account.golden_key)

        proxy = Proxy(self.proxy) if self.proxy else None
        if self._client is None:
            self._client = AsyncClient(
                base_url=BASE_URL,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "User-Agent": USER_AGENT, 
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", 
                    "X-Requested-With": "XMLHttpRequest"
                },
                cookies=cookies,
                proxy=proxy
            )
        return self._client

    async def _method(self, method: Literal["get", "post"], url: str, data: Optional[Dict[str, Any]] = None):
        client = await self._get_client()
        response = await client.request(method, url, data=data)
        return response

    def event(self, name: str, filter: Optional[Callable[[Any], bool]] = None):
        def decorator(func: Handler):
            self._handlers.setdefault(name, []).append((func, filter))
            return func
        return decorator

    def on_new_message(self, filter: Optional[Callable[[Any], bool]] = None):
        return self.event("new_message", filter)

    def on_new_order(self, filter: Optional[Callable[[Any], bool]] = None):
        return self.event("new_order", filter)

    async def emit(self, name: str, data: Any):
        for handler, filter_func in self._handlers.get(name, []):
            if filter_func is None or filter_func(data):
                asyncio.create_task(handler(data))

    async def _get_events(self):
        data = {
            "objects": [],
            "request": "false",
            "csrf_token": self.account.csrf_token
        }

        data["objects"] = [
            {
                "type": "orders_counters",
                "id": str(self.account.user_id),
                "tag": self._orders_counters_tag,
                "data": False
            },
            {
                "type": "chat_bookmarks",
                "id": str(self.account.user_id),
                "tag": self._chat_bookmarks_tag,
                "data": self._chat_bookmarks_data
            }
        ]

        response = await self._method("post", "/runner/", data=data)

        payload = response.json()
        if payload.get("objects"):
            for obj in payload["objects"]:

                if obj["type"] == "orders_counters":
                    self._orders_counters_tag = obj["tag"]

                elif obj["type"] == "chat_bookmarks":
                    self._chat_bookmarks_tag = obj["tag"]
                    contact_order = obj["data"]["order"]

                    loop = asyncio.get_running_loop()

                    messages_dict = await loop.run_in_executor(parser_executor, parse_chat_bookmarks, obj["data"]["html"])
                    for i, contact_id in enumerate(contact_order):
                        message = messages_dict.get(contact_id)
                        if message is None:
                            contact_order[i] = [contact_id, self._chat_bookmarks_data[i][1]]
                            continue
                        contact_order[i] = [contact_id, message.last_message_id]
                        if message.last_message_id != message.last_read_message_id:
                            contact_order[i].append(message.last_read_message_id)

                    self._chat_bookmarks_data = contact_order

                    if self._chat_bookmarks_data:
                        for contact_id, last_message_id, *rest in self._chat_bookmarks_data:
                            self._chat_nodes_data[contact_id] = {
                                "type": "chat_node",
                                "id": f"users_{self.account.user_id}_{contact_id}",
                            }


                    if self._first_run:
                        self._first_run = False
                        return
                    for msg in messages_dict.values():
                        asyncio.create_task(self.emit("new_message", msg))

        return response

    async def _runner_loop(self):
        while self._running:
            await self._get_events()
            await asyncio.sleep(1) 

    async def start(self, wait: bool = True):
        if self._running:
            return
        self._running = True
        self._first_run = True

        self._task = asyncio.create_task(self._runner_loop())

        if wait:
            await self._task

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            await self._task
            self._task = None

