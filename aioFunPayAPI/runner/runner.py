import asyncio
from json import dumps
from typing import Callable, Any, Coroutine, Optional, Literal

from httpx import AsyncClient, Proxy, Cookies

from ..account import Account
from ..common.config import BASE_URL, USER_AGENT
from ..common.parser import parser_executor, parse_chat_bookmarks

Handler = Callable[..., Coroutine[Any, Any, None]]

class Runner:
    def __init__(self, account: Account):
        self._handlers: dict[str, list[tuple[Handler, Optional[Callable[[Any], bool]]]]] = {}
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._first_run = False
        self._client: Optional[AsyncClient] = None

        self._chat_bookmarks_data: list[list[int]] = []
        self._chat_nodes_data: dict[int, dict[str, Any]] = {}

        self.account: Account = account
        self.proxy: Optional[str] = account.proxy

        self._orders_counters_tag: str = "HelloFP!"
        self._chat_bookmarks_tag: str = "HelloFP!"

    async def _get_client(self) -> AsyncClient:
        cookies = Cookies()
        if self.account.golden_key:
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

    async def _method(self, method: Literal["get", "post"], url: str, data: Optional[dict[str, Any]] = None):
        client = await self._get_client()
        return await client.request(method, url, data=data)

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
        request_data: dict[str, Any] = {
            "objects": [
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
            ],
            "request": "false",
            "csrf_token": self.account.csrf_token
        }

        if self._chat_nodes_data:
            objects_list: list[dict[str, Any]] = request_data["objects"]
            for node_id in self._chat_bookmarks_data:
                chat_node_data = self._chat_nodes_data.get(node_id[0])
                if chat_node_data:
                    objects_list.append(chat_node_data)

        request_data["objects"] = dumps(request_data["objects"])
        response = await self._method("post", "/runner/", data=request_data)
        payload = response.json()

        for obj in payload.get("objects", []):
            await self._handle_event(obj)

        return response

    async def _handle_event(self, obj: dict[str, Any]) -> None:
        obj_type = obj.get("type")

        if obj_type == "orders_counters":
            self._orders_counters_tag = obj.get("tag", self._orders_counters_tag)

        elif obj_type == "chat_bookmarks":
            self._chat_bookmarks_tag = obj.get("tag", self._chat_bookmarks_tag)
            await self._handle_chat_bookmarks(obj)

    async def _handle_chat_bookmarks(self, obj: dict[str, Any]) -> None:
        data_obj: dict[str, Any] = {}
        if isinstance(obj.get("data"), dict):
            data_obj = obj["data"]  # type: ignore

        contact_order: list[Any] = []
        if isinstance(data_obj.get("order"), list):
            contact_order = data_obj["order"]  # type: ignore

        message_html: str = ""
        if isinstance(data_obj.get("html"), str):
            message_html = data_obj["html"]

        loop = asyncio.get_running_loop()
        messages_dict_result = await loop.run_in_executor(
            parser_executor,
            parse_chat_bookmarks,
            message_html
        )
        messages_dict: dict[int, Any] = messages_dict_result or {}

        chat_bookmarks = self._build_chat_bookmarks(contact_order, messages_dict)
        self._chat_bookmarks_data = self._filter_chat_bookmarks(chat_bookmarks)

        await self._update_chat_nodes()

        if not self._first_run:
            for msg in messages_dict.values():
                asyncio.create_task(self.emit("new_message", msg))
        else:
            self._first_run = False

    def _build_chat_bookmarks(self, contact_order: list[Any], messages_dict: dict[int, Any]) -> list[list[int]]:
        chat_bookmarks: list[list[int]] = []
        for i, node_id in enumerate(contact_order):
            message = messages_dict.get(node_id)
            if message is None:
                if i < len(self._chat_bookmarks_data) and len(self._chat_bookmarks_data[i]) > 1:
                    self._chat_bookmarks_data[i] = [node_id, self._chat_bookmarks_data[i][1]]
                continue

            item = [node_id, message.last_message_id]
            if message.last_message_id != message.last_read_message_id:
                item.append(message.last_read_message_id)

            chat_bookmarks.append(item)

        return chat_bookmarks

    def _filter_chat_bookmarks(self, chat_bookmarks: list[list[int]]) -> list[list[int]]:
        filtered: list[list[int]] = []
        for entry in chat_bookmarks:
            if len(entry) < 2:
                continue

            node_id, last_message_id = entry[0], entry[1]
            filtered.append([node_id, last_message_id])

        return filtered

    async def _update_chat_nodes(self) -> None:
        if not self._chat_bookmarks_data:
            return

        for item in self._chat_bookmarks_data:
            node_id = item[0]
            if node_id not in self._chat_nodes_data:
                chat_node = await self.account.get_chat_node(node_id)
                self._chat_nodes_data[node_id] = {
                    "type": "chat_node",
                    "id": chat_node.data_name,
                    "tag": chat_node.tag,
                    "data": {
                        "node": chat_node.data_name,
                        "last_message_id": item[1],
                        "content": ""
                    }
                }

    async def _runner_loop(self, interval: float = 1.0):
        while self._running:
            await self._get_events()
            await asyncio.sleep(interval)

    async def start(self, wait: bool = True, interval: float = 1.0):
        if self._running:
            return
        self._running = True
        self._first_run = True

        self._task = asyncio.create_task(self._runner_loop(interval))

        if wait:
            await self._task

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            await self._task
            self._task = None

