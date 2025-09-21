import json
import os
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ResultItem import ResultItem
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction

BOOKMARKS_PATH = os.path.expanduser("~/.config/google-chrome/Default/Bookmarks")

class ChromeBookmarksExtension(Extension):
    def __init__(self):
        super(ChromeBookmarksExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

def remove_url_prefix(url: str) -> str:
    prefixes = ["http://www.", "https://www.", "http://", "https://"]
    for prefix in prefixes:
        if url.startswith(prefix):
            return url[len(prefix):]
    return url

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = (event.get_argument() or "").lower()
        items = []

        try:
            with open(BOOKMARKS_PATH, "r") as f:
                data = json.load(f)

            bookmarks = data["roots"]["bookmark_bar"]["children"]

            for bm in bookmarks:
                if bm["type"] != "url":
                    continue
                name = bm["name"]
                url = remove_url_prefix(bm["url"])
                if query in name.lower() or query in url.lower():
                    items.append(ExtensionResultItem(
                        icon="icons/icon.png",
                        name=name,
                        description=url,
                        on_enter=OpenUrlAction(url)
                    ))

        except Exception as e:
            items.append(ExtensionResultItem(
                icon="icons/icon.png",
                name="Error reading bookmarks",
                description=str(e)
            ))

        return RenderResultListAction(items)

if __name__ == "__main__":
    ChromeBookmarksExtension().run()
