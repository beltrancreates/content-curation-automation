import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

RULES_FILE = CONFIG_DIR / "rules.json"
ITEMS_FILE = DATA_DIR / "items.json"
REVIEW_FILE = DATA_DIR / "review_queue.json"


def load_json(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(item: dict) -> str:
    title = item.get("title", "")
    summary = item.get("summary", "")
    tags = " ".join(item.get("source_tags", []))
    return f"{title} {summary} {tags}".lower()


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def parse_date(date_str: str):
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def age_in_days(date_str: str) -> int:
    dt = parse_date(date_str)
    if dt is None:
        return 9999
    return (datetime.now(timezone.utc) - dt).days


def is_duplicate(item: dict, seen_titles: set, seen_links: set) -> bool:
    title_key = item.get("title", "").strip().lower()
    link_key = item.get("link", "").strip().lower()

    if title_key in seen_titles or link_key in seen_links:
        return True

    seen_titles.add(title_key)
    seen_links.add(link_key)
    return False


def score_item(item: dict, rules: dict, scoring: dict):
    text = normalize_text(item)
    domain = item.get("domain") or extract_domain(item.get("link", ""))
    age_days = age_in_days(item.get("published", ""))

    score = 0
    reasons = []

    include_keywords = [k.lower() for k in rules.get("include_keywords", [])]
    exclude_keywords = [k.lower() for k in rules.get("exclude_keywords", [])]
    preferred_domains = [d.lower() for d in rules.get("preferred_domains", [])]
    blocked_domains = [d.lower() for d in rules.get("blocked_domains", [])]

    if domain in blocked_domains:
        return -999, ["blocked_domain"]

    keyword_hits = [kw for kw in include_keywords if kw in text]
    if keyword_hits:
        score += len(keyword_hits) * scoring.get("keyword_match", 2)
        reasons.append("keyword_hits:" + ",".join(keyword_hits[:5]))

    exclude_hits = [kw for kw in exclude_keywords if kw in text]
    if exclude_hits:
        score += scoring.get("exclude_penalty", -10)
        reasons.append("exclude_hits:" + ",".join(exclude_hits[:5]))

    if domain in preferred_domains:
        score += scoring.get("preferred_domain", 3)
        reasons.append("preferred_domain")

    authority_weight = item.get("authority_weight", 0)
    authority_score = round(authority_weight * scoring.get("authority_multiplier", 0.3), 2)
    score += authority_score
    reasons.append(f"authority:{authority_weight}")

    max_age_days = rules.get("max_age_days", 30)
    if age_days <= max_age_days:
        score += scoring.get("recent_bonus", 2)
        reasons.append(f"recent:{age_days}d")
    else:
        reasons.append(f"old:{age_days}d")

    return score, reasons


def main():
    cfg = load_json(RULES_FILE)
    rules = cfg.get("rules", {})
    scoring = cfg.get("scoring", {})

    items = load_json(ITEMS_FILE)
    existing_review = load_json(REVIEW_FILE)
    existing_review_ids = {item["id"] for item in existing_review if "id" in item}

    seen_titles = set()
    seen_links = set()
    selected = []

    for item in sorted(items, key=lambda x: x.get("published", ""), reverse=True):
        score, reasons = score_item(item, rules, scoring)

        if is_duplicate(item, seen_titles, seen_links):
            score += scoring.get("duplicate_penalty", -4)
            reasons.append("duplicate")

        enriched = {
            **item,
            "score": score,
            "reasons": reasons,
            "status": "review" if score >= rules.get("min_score", 5) else "discarded"
        }

        if enriched["status"] == "review" and enriched["id"] not in existing_review_ids:
            selected.append(enriched)
            existing_review_ids.add(enriched["id"])

    final_review_queue = sorted(existing_review + selected, key=lambda x: x["score"], reverse=True)
    save_json(REVIEW_FILE, final_review_queue)
    print(f"Added {len(selected)} items to review queue. Total: {len(final_review_queue)}")


if __name__ == "__main__":
    main()
