import json
import os
from pathlib import Path
import hashlib
import tempfile
import unicodedata
import shutil
import sqlite3
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction

CACHE_DIR = os.path.expanduser(
    "~/.cache/ulauncher_luneta-browser-bookmark_favicons")

os.makedirs(CACHE_DIR, exist_ok=True)


class LunetaBrowserBookmark(Extension):
    def __init__(self):
        super(LunetaBrowserBookmark, self).__init__()
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


def append_folder(items, item, base_path, event):
    keyword = event.get_keyword()

    bookmark_name = item.get("name", "Unknown")

    items.append(ExtensionResultItem(
        icon="images/folder.png",
        name=bookmark_name,
        description="Click to enter folder",
        on_enter=SetUserQueryAction(f"{keyword} {base_path}{bookmark_name}/")
    ))


def get_favicon(url, event, extension):
    safe_name = hashlib.md5(url.encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"{safe_name}.png")

    if os.path.exists(cache_file):
        return cache_file

    keyword = event.get_keyword()
    profile_path = extension.preferences.get(
        f"{get_profile_path(keyword, extension)}_path")
    favicon_path = os.path.expanduser(f"{profile_path.rstrip('/')}/Favicons")

    if not Path(favicon_path).exists():
        return "images/chrome.png"

    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        shutil.copy(favicon_path, tmpfile.name)
        temp_db = tmpfile.name

    conn = sqlite3.connect(temp_db)
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

    os.unlink(temp_db)

    if row:
        with open(cache_file, "wb") as f:
            f.write(row[0])
        return cache_file

    return "images/chrome.png"


def append_url(items, item, event, extension):
    keyword = event.get_keyword()

    profile_path = extension.preferences.get(
        f"{get_profile_path(keyword, extension)}_path")

    profile = os.path.basename(os.path.normpath(profile_path))

    bookmark_name = item.get("name", "Unknown")
    bookmark_url = item.get("url", "www.example.com")

    chrome_cmd = f'google-chrome --profile-directory="{profile}" "{bookmark_url}"'

    items.append(ExtensionResultItem(
        icon=get_favicon(bookmark_url, event, extension),
        name=bookmark_name,
        description=remove_url_prefix(bookmark_url),
        on_enter=RunScriptAction(chrome_cmd, [])
    ))


def get_profile_path(keyword, extension):
    pref_id = None
    for pid, value in extension.preferences.items():
        if value == keyword:
            pref_id = pid
            break
    return pref_id


def clear_cache():
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
        return True
    return False


def get_bookmark_items(query="", event=None, extension=None):
    query = query.strip()

    keyword = event.get_keyword()

    if keyword == extension.preferences['kw_clear_favicon_cache']:
        cleaned = clear_cache()
        return [ExtensionResultItem(
            icon="images/logo.png",
            name="Favicon cache cleared" if cleaned else "No favicon cache to clear",
            description="Luneta Browser Bookmark favicon cache has been reset" if cleaned else "There was no favicon cache to clear"
        )]

    profile_path = extension.preferences.get(
        f"{get_profile_path(keyword, extension)}_path")
    bookmarks_path = os.path.expanduser(
        f"{profile_path.rstrip('/')}/Bookmarks")

    with open(bookmarks_path, "r") as f:
        data = json.load(f)

    node = data["roots"]["bookmark_bar"]["children"]
    parts = [p.strip() for p in query.split("/") if p.strip()]
    search_term = None
    base_path = ""

    if query.endswith("/") and parts:
        for part in parts:
            found = None
            for item in node:
                if item.get("type", "") == "folder" and item.get("name", "").lower() == part.lower():
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
                        if item.get("type", "") == "folder" and item.get("name", "").lower() == part.lower():
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
        item_type = item.get("type", "")
        bookmark_name = item.get("name", "Unknown")
        bookmark_url = item.get("url", "")

        if search_term is None:
            if item_type == "folder":
                append_folder(items, item, base_path, event)
            elif item_type == "url":
                append_url(items, item, event, extension)
        else:
            if item_type == "folder":
                if contains_ignore_accents(bookmark_name, search_term):
                    append_folder(items, item, base_path, event)
            elif item_type == "url":
                if contains_ignore_accents(bookmark_name, search_term) or contains_ignore_accents(bookmark_url, search_term):
                    append_url(items, item, event, extension)

    max_results = extension.preferences.get("max_results")

    if max_results and max_results.isdigit():
        return items[:int(max_results)]
    return items


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        items = []

        try:
            items = get_bookmark_items(query, event, extension)

        except Exception as e:
            items.append(ExtensionResultItem(
                icon="images/logo.png",
                name="Error reading bookmarks",
                description=str(e)
            ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    LunetaBrowserBookmark().run()
