import json
import os
from pathlib import Path
from urllib.parse import quote
import tempfile
import unicodedata
import shutil
import sqlite3
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction

BOOKMARKS_PATH = os.path.expanduser(
    "~/.config/google-chrome/Default/Bookmarks")

FAVICONS_DB = os.path.expanduser("~/.config/google-chrome/Default/Favicons")

MAX_ITEMS = 10

CACHE_DIR = os.path.expanduser("~/.cache/ulauncher_favicons")

os.makedirs(CACHE_DIR, exist_ok=True)


class ChromeBookmarksExtension(Extension):
    def __init__(self):
        super(ChromeBookmarksExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


def remove_url_prefix(url):
    prefixes = ["http://www.", "https://www.", "http://", "https://"]
    for prefix in prefixes:
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def remove_accents(text):
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def contains_ignore_accents(a, b):
    a_norm = remove_accents(a).lower()
    b_norm = remove_accents(b).lower()
    return b_norm in a_norm


def append_folder(items, item, base_path):
    items.append(ExtensionResultItem(
        icon="icons/folder.png",
        name=item["name"],
        description="Click to enter folder",
        on_enter=SetUserQueryAction(f"pitura {base_path}{item["name"]}/")
    ))


def get_favicon(url):
    safe_name = quote(url, safe="")
    cache_file = os.path.join(CACHE_DIR, f"{safe_name}.png")

    if os.path.exists(cache_file):
        return cache_file

    if not Path(FAVICONS_DB).exists():
        return "icons/chrome.png"

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            shutil.copy(FAVICONS_DB, tmpfile.name)
            TEMP_DB = tmpfile.name

        conn = sqlite3.connect(TEMP_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT fb.image_data
            FROM icon_mapping im
            JOIN favicon_bitmaps fb ON im.icon_id = fb.icon_id
            WHERE im.page_url LIKE ?
            ORDER BY fb.width DESC, fb.last_updated DESC
            LIMIT 1
        """, (f"%{url}%",))
        row = cur.fetchone()
        conn.close()

        os.unlink(TEMP_DB)

        if row:
            with open(cache_file, "wb") as f:
                f.write(row[0])
            return cache_file
    except Exception as e:
        print("Error reading Chrome favicon:", e)

    return "icons/chrome.png"


def append_url(items, item):
    items.append(ExtensionResultItem(
        icon=get_favicon(item["url"]),
        name=item["name"],
        description=remove_url_prefix(item["url"]),
        on_enter=OpenUrlAction(item["url"])
    ))


def get_bookmark_items(query=""):
    query = query.strip()

    with open(BOOKMARKS_PATH, "r") as f:
        data = json.load(f)

    node = data["roots"]["bookmark_bar"]["children"]
    parts = [p.strip() for p in query.split("/") if p.strip()]
    search_term = None
    base_path = ""

    if query.endswith("/") and parts:
        for part in parts:
            found = None
            for item in node:
                if item["type"] == "folder" and item["name"].lower() == part.lower():
                    found = item.get("children", [])
                    break
            if found is None:
                return []
            node = found
        base_path = "/".join(parts) + "/"
    else:
        if parts:
            *folders, last = parts
            if folders:
                for part in folders:
                    found = None
                    for item in node:
                        if item["type"] == "folder" and item["name"].lower() == part.lower():
                            found = item.get("children", [])
                            break
                    if found is None:
                        return []
                    node = found
                base_path = "/".join(folders) + "/"
            else:
                base_path = ""
            search_term = last.lower()
        else:
            search_term = None
            base_path = ""

    items = []
    for item in node:
        if search_term is None:
            if item["type"] == "folder":
                append_folder(items, item, base_path)
            elif item["type"] == "url":
                append_url(items, item)
        else:
            if item["type"] == "folder":
                if contains_ignore_accents(item["name"], search_term):
                    append_folder(items, item, base_path)
            elif item["type"] == "url":
                if contains_ignore_accents(item["name"], search_term) or contains_ignore_accents(item["url"], search_term):
                    append_url(items, item)

    return items[:MAX_ITEMS]


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        items = []

        try:
            items = get_bookmark_items(query)

        except Exception as e:
            items.append(ExtensionResultItem(
                icon="icons/chrome.png",
                name="Error reading bookmarks",
                description=str(e)
            ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    ChromeBookmarksExtension().run()
