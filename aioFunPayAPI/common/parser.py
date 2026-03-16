import json, re

from typing import Optional, Any, cast
from selectolax.lexbor import LexborHTMLParser
from concurrent.futures import ThreadPoolExecutor

from ..types import Category, ChatNode, Subcategory, Contact, ChatBookmarkMessage
  
parser_executor = ThreadPoolExecutor()

def parse_account_data(html: str) -> Optional[tuple[str, float, dict[str, Any]]]:
    tree = LexborHTMLParser(html)
    username = parse_username(tree)
    balance = parse_balance(tree)
    appdata = parse_appdata(tree)

    if username is None or balance is None or appdata is None:
        return None

    return username, balance, appdata

def parse_username(tree: LexborHTMLParser) -> Optional[str]:
    node = tree.css_first("div.user-link-name")
    return node.text(strip=True) if node and node.text() else None

def parse_balance(tree: LexborHTMLParser) -> Optional[float]:
    node = tree.css_first("span.badge-balance")
    if not node:
        return None

    text = node.text(strip=True)
    try:
        value = text.split()[0]
        return float(value)
    except (IndexError, ValueError, TypeError):
        return None

def parse_appdata(tree: LexborHTMLParser) -> Optional[dict[str, Any]]:
    body = tree.css_first("body")
    if not body:
        return None

    raw = body.attributes.get("data-app-data")
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    data = cast(dict[str, Any], parsed)
    return data if data else None

def parse_category(html: str) -> list[Category]:
    tree = LexborHTMLParser(html)
    categories: list[Category] = []

    for game_node in tree.css(".promo-game-item"):
        title_node = game_node.css_first(".game-title a")
        if not title_node:
            continue

        game_title = title_node.text(strip=True) or ""
        game_url = title_node.attributes.get("href") or ""

        game_id_node = game_node.css_first(".game-title")
        if not game_id_node:
            continue

        raw_game_id = game_id_node.attributes.get("data-id")
        if raw_game_id is None:
            continue

        try:
            game_id = int(raw_game_id)
        except (TypeError, ValueError):
            continue

        subcats: list[Subcategory] = []
        ul_node = game_node.css_first("ul.list-inline")
        if ul_node:
            for li in ul_node.css("li a"):
                href = li.attributes.get("href")
                if not href:
                    continue

                subcat_type = "lots" if "/lots/" in href else "chips"
                try:
                    subcat_id = int(href.rstrip("/").split("/")[-1])
                except (TypeError, ValueError):
                    continue

                subcats.append(Subcategory(
                    type=subcat_type,
                    id=subcat_id,
                    name=li.text(strip=True) or "",
                    url=href,
                    game_title=game_title
                ))

        categories.append(Category(
            id=game_id,
            game_title=game_title,
            url=game_url,
            subcategories=subcats
        ))

    return categories


def _parse_int(value: Optional[str], default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_contacts(html: str) -> list[Contact]:
    tree = LexborHTMLParser(html)

    contacts: list[Contact] = []

    for node in tree.css("a.contact-item"):
        node_id = _parse_int(node.attributes.get("data-id"))
        last_message_id = _parse_int(node.attributes.get("data-node-msg"))
        last_read_message_id = _parse_int(node.attributes.get("data-user-msg"))

        username_node = node.css_first(".media-user-name")
        last_message_node = node.css_first(".contact-item-message")
        last_time_node = node.css_first(".contact-item-time")

        username = username_node.text(strip=True) if username_node else ""
        last_message_text = last_message_node.text(strip=True) if last_message_node else ""
        last_message_time = last_time_node.text(strip=True) if last_time_node else ""

        avatar_style: str = ""
        avatar_node = node.css_first(".avatar-photo")
        if avatar_node:
            avatar_style = avatar_node.attributes.get("style") or ""

        avatar_match = re.search(r"url\((.*?)\)", avatar_style)
        if avatar_match:
            avatar = avatar_match.group(1)
        else:
            avatar = ""

        contacts.append(
            Contact(
                node_id=node_id,
                last_message_id=last_message_id,
                last_read_message_id=last_read_message_id,
                avatar=avatar,
                username=username,
                last_message_text=last_message_text,
                last_message_time=last_message_time,
            )
        )

    return contacts

"""<div class="chat-full-header">    <h1>Сообщения <span class="badge badge-primary">1</span></h1></div><div class="contact-list custom-scroll">                    <a href="https://funpay.com/chat/?node=245732163" class="contact-item unread" data-id="245732163" data-node-msg="4451540826" data-user-msg="4447899410">            <div class="contact-item-photo">                <div class="avatar-photo" style="background-image: url(/img/layout/avatar.png);"></div>            </div>            <div class="media-user-name">OpenMMTester</div>                            <div class="contact-item-message">sadasdas</div>                <div class="contact-item-time">01:57</div>                    </a>    </div>"""

def parse_chat_bookmarks(html: str) -> Optional[dict[int, ChatBookmarkMessage]]:
    tree = LexborHTMLParser(html)
    nodes = tree.css("a.contact-item")

    if not nodes:
        return None

    messages: dict[int, ChatBookmarkMessage] = {}
    for node in nodes:
        node_id = _parse_int(node.attributes.get("data-id"))
        last_message_id = _parse_int(node.attributes.get("data-node-msg"))
        last_read_message_id = _parse_int(node.attributes.get("data-user-msg"))

        username_node = node.css_first(".media-user-name")
        last_message_node = node.css_first(".contact-item-message")
        last_time_node = node.css_first(".contact-item-time")

        username = username_node.text(strip=True) if username_node else ""
        last_message_text = last_message_node.text(strip=True) if last_message_node else ""
        last_message_time = last_time_node.text(strip=True) if last_time_node else ""

        avatar_style: str = ""
        avatar_node = node.css_first(".avatar-photo")
        if avatar_node:
            avatar_style = avatar_node.attributes.get("style") or ""

        avatar_match = re.search(r"url\((.*?)\)", avatar_style)
        if avatar_match:
            avatar = avatar_match.group(1)
        else:
            avatar = ""

        chat_url = node.attributes.get("href", "") or ""
        unread = "unread" in (node.attributes.get("class", "") or "")

        messages[node_id] = ChatBookmarkMessage(
            chat_url=chat_url,
            node_id=node_id,
            last_message_id=last_message_id,
            last_read_message_id=last_read_message_id,
            avatar=avatar,
            username=username,
            text=last_message_text,
            time=last_message_time,
            unread=unread
        )

    return messages


#<div class="chat chat-float" data-id="245732163" data-name="users-12423495-19174038" data-user="12423495" data-history="1" data-tag="0oymifmc" data-bookmarks-tag="1jmfjnm7">
def parse_chat_node(html: str) -> ChatNode:
    tree = LexborHTMLParser(html)
    
    chat_node = tree.css_first("div.chat")
    data_name = cast(str, chat_node.attributes.get("data-name")) 
    app_data = parse_appdata(tree)
    if not app_data:
        raise ValueError("App data not found in chat node")
    chat_user_id = "0"
    for part in data_name.split("-"):
        if part.isdigit():
            if app_data["userId"] == int(part):
                continue
            chat_user_id = part
    chat_node_tag = cast(str, chat_node.attributes.get("data-tag"))

    return ChatNode(
        data_name=data_name,
        node_id=_parse_int(chat_node.attributes.get("data-id")),
        user_id=_parse_int(chat_user_id),
        tag=chat_node_tag
    )