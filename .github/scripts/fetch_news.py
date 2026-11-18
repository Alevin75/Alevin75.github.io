"""
Новости для газеты «ОСТРОВ» — этот скрипт запускает GitHub Action каждый час.

Он берёт ленту Lenta.ru, оставляет только спокойные рубрики (те же, что были
в приложении) и пишет файл news/world.json в этот же репозиторий. Приложение
читает уже готовый файл со своего домена — поэтому в браузере нет проблемы CORS.

Запускается из .github/workflows/news.yml. Вручную: python .github/scripts/fetch_news.py
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

FEED_URL = "https://lenta.ru/rss/news"
UA = ("Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124 Mobile Safari/537.36")
LIMIT = 25
ALLOWED = {"Спорт", "Путешествия", "Наука и техника", "Культура", "Авто",
           "Забота о себе", "Интернет и СМИ"}

# Путь относительно корня репозитория (Action запускается из корня).
OUT_PATH = os.path.join("news", "world.json")

ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ",
            "laquo": "«", "raquo": "»", "ldquo": "“", "rdquo": "”", "mdash": "—",
            "ndash": "–", "hellip": "…", "deg": "°", "times": "×"}


def decode(text: str) -> str:
    def repl(m):
        code = m.group(1)
        if code.lower().startswith("#x"):
            try:
                return chr(int(code[2:], 16))
            except ValueError:
                return m.group(0)
        if code.startswith("#"):
            try:
                return chr(int(code[1:]))
            except ValueError:
                return m.group(0)
        return ENTITIES.get(code.lower(), m.group(0))
    return re.sub(r"&(#x?[0-9a-fA-F]+|[a-zA-Z]+);", repl, text)


def pick(source: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", source)
    if not m:
        return ""
    return m.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def build_items(xml: str):
    items, seen = [], set()
    for chunk in re.split(r"<item[\s>]", xml)[1:]:
        category = pick(chunk, "category")
        if category not in ALLOWED:
            continue
        title = decode(pick(chunk, "title"))
        link = pick(chunk, "link")
        if not title or not link or link in seen:
            continue
        seen.add(link)
        try:
            dt = datetime.strptime(pick(chunk, "pubDate"), "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        items.append({
            "id": link.rstrip("/").split("/")[-1] or link,
            "title": title,
            "link": link,
            "category": category,
            "date": dt.astimezone(timezone.utc).isoformat(),
        })
    items.sort(key=lambda it: it["date"], reverse=True)
    return items[:LIMIT]


def main() -> int:
    try:
        xml = fetch(FEED_URL)
    except Exception as exc:                     # сеть подвела — старый файл не портим
        print(f"лента недоступна: {exc}", file=sys.stderr)
        return 0

    items = build_items(xml)
    if not items:
        print("в ленте не нашлось подходящих рубрик — файл не меняем", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    payload = {
        "source": "Lenta.ru",
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
        handle.write("\n")

    print(f"{OUT_PATH}: {len(items)} новостей, обновлено {payload['updated']}")
    if items:
        print("первая:", items[0]["category"], "|", items[0]["title"][:90])
    return 0


if __name__ == "__main__":
    sys.exit(main())
