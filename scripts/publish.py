import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

REVIEW_FILE = DATA_DIR / "review_queue.json"
PUBLISHED_FILE = DATA_DIR / "published.json"
OUTPUT_FILE = OUTPUT_DIR / "index.md"


def load_json(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def build_markdown(items: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Curación de contenidos",
        "",
        f"_Actualizado: {now}_",
        "",
        "## Selección priorizada",
        ""
    ]

    if not items:
        lines.append("No hay contenidos publicados todavía.")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        lines.extend([
            f"### {idx}. {item['title']}",
            "",
            f"- **Fuente:** {item['source_name']}",
            f"- **Dominio:** {item['domain']}",
            f"- **Fecha:** {item['published']}",
            f"- **Score:** {item['score']}",
            f"- **Razones:** {', '.join(item.get('reasons', []))}",
            f"- **Enlace:** {item['link']}",
            "",
            item.get("summary", "")[:500],
            "",
            "---",
            ""
        ])

    return "\n".join(lines)


def main():
    review_items = load_json(REVIEW_FILE)
    published_items = load_json(PUBLISHED_FILE)
    published_ids = {item["id"] for item in published_items if "id" in item}

    candidates = [item for item in review_items if item["id"] not in published_ids]
    top_items = sorted(candidates, key=lambda x: x["score"], reverse=True)[:10]

    updated_published = published_items + top_items
    save_json(PUBLISHED_FILE, updated_published)

    markdown = build_markdown(updated_published[-20:][::-1])
    save_text(OUTPUT_FILE, markdown)

    print(f"Published {len(top_items)} new items. Total: {len(updated_published)}")


if __name__ == "__main__":
    main()
