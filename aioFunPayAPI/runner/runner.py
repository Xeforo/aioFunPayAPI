import asyncio

from json import dumps
from typing import Callable, Any, Coroutine, Dict, List, Optional, Literal, cast
from httpx import AsyncClient, Proxy, Cookies

from ..account import Account
from ..common.config import BASE_URL, USER_AGENT
from ..common.parser import parser_executor, parse_chat_bookmarks


Handler = Callable[..., Coroutine[Any, Any, None]]

class Runner:
    def __init__(self, account: Account):
        self._handlers: Dict[str, List[tuple[Handler, Optional[Callable[[Any], bool]]]]] = {}
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._client: Optional[AsyncClient] = None

        self._chat_bookmarks_data: List[List[int]] = []
        self._chat_nodes_data: Dict[int, dict[str, Any]] = {}

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
        data: Dict[str, Any] = {
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

        if self._chat_nodes_data:
            for chat_bookmark_data in self._chat_bookmarks_data:
                node_id = chat_bookmark_data[0]
                chat_node_data = self._chat_nodes_data.get(node_id)
                if chat_node_data:
                    cast(List[dict[str, Any]], data["objects"]).append(chat_node_data)

        data["objects"] = dumps(data["objects"])

        print("Sending events request with data:", data)

        response = await self._method("post", "/runner/", data=data)
        print("Received events response:", response.json())

        payload = cast(dict[str, Any], response.json())
        objects = cast(List[dict[str, Any]], payload.get("objects") or [])
        for obj in objects:

            obj_type = obj.get("type")
            if obj_type == "orders_counters":
                self._orders_counters_tag = cast(str, obj.get("tag", self._orders_counters_tag))

            elif obj_type == "chat_bookmarks":
                self._chat_bookmarks_tag = cast(str, obj.get("tag", self._chat_bookmarks_tag))
                data_obj_raw = obj.get("data")
                data_obj = cast(dict[str, Any], data_obj_raw if isinstance(data_obj_raw, dict) else {})

                contact_order_raw = data_obj.get("order")
                contact_order = cast(List[int], contact_order_raw if isinstance(contact_order_raw, list) else [])

                loop = asyncio.get_running_loop()

                message_html = cast(str, data_obj.get("html", ""))
                messages_dict = await loop.run_in_executor(
                    parser_executor,
                    parse_chat_bookmarks,
                    message_html
                )

                messages_dict = messages_dict or {}

                chat_bookmarks: List[List[int]] = []
                for i, node_id in enumerate(contact_order):
                    message = messages_dict.get(node_id)
                    if message is None:
                        print(f"Warning: No message data found for node_id {node_id} in contact_order")
                        if i < len(self._chat_bookmarks_data) and len(self._chat_bookmarks_data[i]) > 1:
                            print(f"Preserving last_message_id for node_id {node_id} as {self._chat_bookmarks_data[i][1]}")
                            self._chat_bookmarks_data[i] = [node_id, self._chat_bookmarks_data[i][1]]
                        continue

                    item: List[int] = [node_id, message.last_message_id]
                    if message.last_message_id != message.last_read_message_id:
                        item.append(message.last_read_message_id)

                    chat_bookmarks.append(item)

                filtered_chat_bookmarks: List[List[int]] = []
                for raw_entry in chat_bookmarks:

                    entry = cast(List[Any], raw_entry)
                    if len(entry) < 2:
                        continue

                    node_id = entry[0]
                    last_message_id = entry[1]
                    if not isinstance(node_id, int) or not isinstance(last_message_id, int):
                        continue

                    filtered_chat_bookmarks.append([node_id, last_message_id])

                self._chat_bookmarks_data = filtered_chat_bookmarks

                if self._chat_bookmarks_data:
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

                if getattr(self, "_first_run", False):
                    self._first_run = False
                    return

                for msg in messages_dict.values():
                    asyncio.create_task(self.emit("new_message", msg))


                    if self._first_run:
                        self._first_run = False
                        return
                    for msg in messages_dict.values():
                        asyncio.create_task(self.emit("new_message", msg))

        return response

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

