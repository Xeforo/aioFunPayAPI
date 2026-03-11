import asyncio

from json import dumps
from typing import Callable, Any, Coroutine, Dict, List, Optional, Literal
from httpx import AsyncClient, Proxy, Cookies

from ..account import Account
from ..common.config import BASE_URL, USER_AGENT
from ..types import Contact

from .events import Event, ChatBookmarksEvent

Handler = Callable[..., Coroutine[Any, Any, None]]

class Runner:
    def __init__(self, account: Account):
        self._handlers: Dict[str, List[tuple[Handler, Optional[Callable[[Any], bool]]]]] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._client: Optional[AsyncClient] = None
        self._contacts_cache: Optional[list[Contact]] = None
        self.account: Account = account
        self.proxy: Optional[str] = account.proxy

        self.orders_counters_tag: str = "uno7nb4u"
        self.chat_bookmarks_tag: str = "c8u4zzkm"

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

    async def emit(self, name: str, event: Any):
        for handler, filter_func in self._handlers.get(name, []):
            if filter_func is None or filter_func(event):
                await handler(event)

    async def _get_events(self):
        data = {
            "objects": [],
            "request": "false",
            "csrf_token": self.account.csrf_token
        }
        if self._contacts_cache:
            chat_bookmarks_data = []
            for contact in self._contacts_cache:
                append = [
                    contact.node_id,
                    contact.last_message_id
                ]
                if contact.last_read_message_id != contact.last_message_id:
                    append.append(contact.last_read_message_id)
                chat_bookmarks_data.append(append)


            data["objects"] = dumps([
                {
                    "type": "orders_counters",
                    "id": str(self.account.user_id),
                    "tag": self.orders_counters_tag,
                    "data": False
                },
                {
                    "type": "chat_bookmarks",
                    "id": str(self.account.user_id),
                    "tag": self.chat_bookmarks_tag,
                    "data": chat_bookmarks_data
                }
            ])
        print("Requesting events with data:", data)
        response = await self._method("post", "/runner/", data=data)
        return response

    async def _runner_loop(self):
        while self._running:

            response = await self._get_events()
            if response.status_code != 200:
                await asyncio.sleep(2)
                continue
            print(response.json()) 
            events = [
                
            ]

            for event in events:
                await self.emit(event["type"], event)

            await asyncio.sleep(5) 

    async def start(self):
        if self._running:
            return
        self._running = True
        self._contacts_cache = await self.account.get_contacts()
        self._task = asyncio.create_task(self._runner_loop())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            await self._task
            self._task = None
