"""Bot de veille GTA 6 — alertes Telegram temps réel + brief quotidien.

Usage:
    py -3.12 veille.py               # cycle de veille (envoie ou dry-run si pas de token)
    py -3.12 veille.py --dry-run     # force l'affichage console, aucun envoi
    py -3.12 veille.py --brief       # brief du soir : top 3 angles video des dernieres 24h
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from curl_cffi import requests as cffi_requests

# console Windows en cp1252 : on force l'UTF-8 pour les emojis des messages
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen.json"
MAX_SEEN = 2000
MAX_AGE_HOURS = 48  # on n'alerte jamais sur un item plus vieux que ça

SOURCES = [
    {
        "name": "Rockstar (YouTube)",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6VcWc1rAoWdBCM0JxrRQ3A",
        "needs_filter": False,  # tout ce que poste Rockstar nous intéresse
        "weight": 3,
        "lang": "en",
    },
    {
        "name": "Rockstar Mag' (FR)",
        "url": "https://www.rockstarmag.fr/feed/",
        "needs_filter": True,
        "weight": 2,
        "lang": "fr",
    },
    {
        "name": "GTAboom",
        "url": "https://www.gtaboom.com/feed",
        "needs_filter": True,
        "weight": 2,
        "lang": "en",
    },
    {
        "name": "VGC",
        "url": "https://www.videogameschronicle.com/category/news/feed/",
        "needs_filter": True,
        "weight": 1,
        "lang": "en",
    },
    {
        # Flux utilisé comme radar privé pour le brief de Hugo (usage perso,
        # cf. licence du flux) — les alertes publiques pointent vers l'article source.
        "name": "Google News FR",
        "url": "https://news.google.com/rss/search?q=%22GTA+6%22&hl=fr&gl=FR&ceid=FR:fr",
        "needs_filter": True,
        "weight": 1,
        "lang": "fr",
    },
]

KEYWORDS = re.compile(r"gta\s*(6|vi)\b|grand theft auto|rockstar|take[- ]two", re.I)
HOT = re.compile(
    r"trailer|bande[- ]annonce|date|report[ée]|delay|pr[ée]commande|pre[- ]?order"
    r"|leak|fuite|online|prix|price|record|annonce|reveal|officiel|official",
    re.I,
)


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    # garde les MAX_SEEN entrées les plus récentes
    items = sorted(seen.items(), key=lambda kv: kv[1]["ts"], reverse=True)[:MAX_SEEN]
    SEEN_FILE.write_text(
        json.dumps(dict(items), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def item_id(link: str) -> str:
    return hashlib.sha256(link.encode()).hexdigest()[:16]


def fetch_feed(source: dict):
    """curl_cffi avec empreinte Chrome : passe les WAF qui bloquent requests nu."""
    resp = cffi_requests.get(source["url"], impersonate="chrome", timeout=25)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def entry_timestamp(entry) -> float:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return time.mktime(parsed)
    return time.time()


def translate_fr(text: str) -> str:
    """Traduction best-effort ; en cas d'échec on garde l'original."""
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="fr").translate(text)
    except Exception as exc:  # réseau/quota : jamais bloquant
        log(f"traduction échouée ({exc.__class__.__name__}), titre original conservé")
        return text


def collect_new_items(seen: dict) -> list[dict]:
    now = time.time()
    new_items = []
    for source in SOURCES:
        try:
            feed = fetch_feed(source)
        except Exception as exc:
            log(f"ERREUR source {source['name']}: {exc}")
            continue
        for entry in feed.entries[:30]:
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                continue
            if source["needs_filter"] and not KEYWORDS.search(title):
                continue
            iid = item_id(link)
            if iid in seen:
                continue
            ts = entry_timestamp(entry)
            item = {
                "title": title,
                "link": link,
                "source": source["name"],
                "weight": source["weight"],
                "lang": source["lang"],
                "ts": ts,
                "fresh": (now - ts) <= MAX_AGE_HOURS * 3600,
            }
            seen[iid] = {k: item[k] for k in ("title", "link", "source", "weight", "ts")}
            new_items.append(item)
        log(f"{source['name']}: {len(feed.entries)} entrées lues")
    return new_items


def format_alert(item: dict) -> str:
    title_fr = item["title"] if item["lang"] == "fr" else translate_fr(item["title"])
    hot = "🔥 " if HOT.search(item["title"]) else ""
    return (
        f"{hot}<b>{title_fr}</b>\n"
        f"📰 {item['source']}\n"
        f"🔗 {item['link']}"
    )


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        log(f"ERREUR Telegram {resp.status_code}: {resp.text[:200]}")
        return False
    return True


def deliver(text: str, dry_run: bool) -> None:
    if dry_run or not send_telegram(text):
        print("\n----- MESSAGE (dry-run) -----")
        print(re.sub(r"</?b>", "*", text))
        print("-----------------------------\n")


def run_veille(dry_run: bool) -> None:
    seen = load_seen()
    first_run = not seen
    new_items = collect_new_items(seen)
    save_seen(seen)

    if first_run:
        # amorçage : on marque tout comme vu sans spammer le canal
        log(f"Première exécution : {len(new_items)} items marqués comme vus, aucun envoi.")
        return

    to_send = [i for i in new_items if i["fresh"]]
    log(f"{len(new_items)} nouveaux items, {len(to_send)} assez récents pour alerter.")
    for item in sorted(to_send, key=lambda i: i["ts"]):
        deliver(format_alert(item), dry_run)
        time.sleep(1)  # rythme gentil avec l'API Telegram


def run_brief(dry_run: bool) -> None:
    seen = load_seen()
    cutoff = time.time() - 24 * 3600
    recent = [v for v in seen.values() if v["ts"] >= cutoff]
    if not recent:
        log("Brief : aucune actu sur les dernières 24h.")
        return

    def score(item: dict) -> int:
        return item["weight"] + (2 if HOT.search(item["title"]) else 0)

    top = sorted(recent, key=score, reverse=True)[:3]
    lines = ["🎬 <b>Brief du soir — 3 angles vidéo</b>\n"]
    for rank, item in enumerate(top, 1):
        lines.append(f"{rank}. <b>{item['title']}</b>\n   {item['source']} — {item['link']}")
    lines.append("\n💡 Choisis-en un, donne TON angle : c'est l'originalité qui paie.")
    deliver("\n".join(lines), dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Veille GTA 6")
    parser.add_argument("--dry-run", action="store_true", help="affiche au lieu d'envoyer")
    parser.add_argument("--brief", action="store_true", help="brief du soir (top 3)")
    args = parser.parse_args()

    if args.brief:
        run_brief(args.dry_run)
    else:
        run_veille(args.dry_run)


if __name__ == "__main__":
    main()
