import json
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

SOURCES_FILE = CONFIG_DIR / "sources.json"
ITEMS_FILE = DATA_DIR / "items.json"


def load_json(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_url(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ContentCurator/1.0"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def build_id(link: str, title: str) -> str:
    raw = f"{link}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def text_or_empty(elem, tag_names):
    for tag in tag_names:
        found = elem.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_rss(xml_bytes: bytes):
    items = []
    root = ET.fromstring(xml_bytes)

    for item in root.findall(".//channel/item"):
        title = text_or_empty(item, ["title"])
        link = text_or_empty(item, ["link"])
        summary = text_or_empty(item, ["description"])
        published = text_or_empty(item, ["pubDate"]) or datetime.now(timezone.utc).isoformat()

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": published
        })

    if items:
        return items

    # Atom fallback
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = text_or_empty(entry, ["{http://www.w3.org/2005/Atom}title"])
        summary = text_or_empty(entry, [
            "{http://www.w3.org/2005/Atom}summary",
            "{http://www.w3.org/2005/Atom}content"
        ])

        link = ""
        for link_elem in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = link_elem.attrib.get("href", "").strip()
            if href:
                link = href
                break

        published = text_or_empty(entry, [
            "{http://www.w3.org/2005/Atom}published",
            "{http://www.w3.org/2005/Atom}updated"
        ]) or datetime.now(timezone.utc).isoformat()

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": published
        })

    return items


def normalize_entry(source_meta: dict, entry: dict) -> dict:
    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()
    summary = entry.get("summary", "").strip()
    published = entry.get("published", "").strip() or datetime.now(timezone.utc).isoformat()

    return {
        "id": build_id(link, title),
        "title": title,
        "link": link,
        "summary": summary,
        "published": published,
        "source_name": source_meta["name"],
        "source_url": source_meta["url"],
        "source_type": source_meta.get("type", "rss"),
        "authority_weight": source_meta.get("authority_weight", 0),
        "source_tags": source_meta.get("tags", []),
        "domain": domain_from_url(link),
        "status": "fetched"
    }


def main():
    config = load_json(SOURCES_FILE)
    sources = config.get("sources", [])
    existing_items = load_json(ITEMS_FILE)
    existing_ids = {item["id"] for item in existing_items if "id" in item}

    new_items = []

    for source in sources:
        if source.get("type") != "rss":
            continue

        try:
            xml_bytes = fetch_url(source["url"])
            entries = parse_rss(xml_bytes)
        except Exception as e:
            print(f"ERROR fetching {source['name']}: {e}")
            continue

        for entry in entries:
            item = normalize_entry(source, entry)

            if not item["title"] or not item["link"]:
                continue

            if item["id"] in existing_ids:
                continue

            new_items.append(item)
            existing_ids.add(item["id"])

    all_items = existing_items + new_items
    save_json(ITEMS_FILE, all_items)
    print(f"Fetched {len(new_items)} new items. Total: {len(all_items)}")


if __name__ == "__main__":
    main()
