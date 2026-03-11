import orjson, re

from typing import Optional
from selectolax.lexbor import LexborHTMLParser
from concurrent.futures import ThreadPoolExecutor

from ..types import Category, Subcategory, Contact
  
parser_executor = ThreadPoolExecutor()

def parse_account_data(html: str) -> Optional[tuple[str, float, dict]]:
    tree = LexborHTMLParser(html)
    username: Optional[str] = parse_username(tree)
    balance: Optional[float] = parse_balance(tree)
    appdata: Optional[dict] = parse_appdata(tree)
    return username, balance, appdata

def parse_username(tree: LexborHTMLParser) -> Optional[str]:
    node = tree.css_first("div.user-link-name")
    return node.text() if node else None

def parse_balance(tree: LexborHTMLParser) -> Optional[float]:
    node = tree.css_first("span.badge-balance")
    return float(node.text().split()[0]) if node else None

def parse_appdata(tree: LexborHTMLParser) -> Optional[str]:
    node = tree.css_first("body").attributes["data-app-data"]
    node = orjson.loads(node)
    return node if node else None

def parse_category(html: str) -> list[Category]:
    tree = LexborHTMLParser(html)
    categories = []

    for game_node in tree.css(".promo-game-item"):
        title_node = game_node.css_first(".game-title a")
        game_title = title_node.text(strip=True)
        game_url = title_node.attributes["href"]
        game_id = int(game_node.css_first(".game-title").attributes["data-id"])

        subcats = []
        ul_node = game_node.css_first("ul.list-inline")
        for li in ul_node.css("li a"):
            subcats.append(Subcategory(
                type="lots" if "/lots/" in li.attributes["href"] else "chips",
                id=int(li.attributes["href"].rstrip("/").split("/")[-1]),
                name=li.text(strip=True),
                url=li.attributes["href"],
                game_title=game_title
            ))

        categories.append(Category(
            id=game_id,
            game_title=game_title,
            url=game_url,
            subcategories=subcats
        ))

    return categories


def parse_contacts(html: str) -> list[Contact]:
    tree = LexborHTMLParser(html)

    contacts: list[Contact] = []

    for node in tree.css("a.contact-item"):
        node_id = int(node.attributes.get("data-id"))
        last_message_id = int(node.attributes.get("data-node-msg"))
        last_read_message_id = int(node.attributes.get("data-user-msg"))

        username = node.css_first(".media-user-name").text(strip=True)
        last_message_text = node.css_first(".contact-item-message").text(strip=True)
        last_message_time = node.css_first(".contact-item-time").text(strip=True)

        avatar_style = node.css_first(".avatar-photo").attributes.get("style", "")
        avatar = re.search(r"url\((.*?)\)", avatar_style)
        avatar = avatar.group(1) if avatar else ""

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