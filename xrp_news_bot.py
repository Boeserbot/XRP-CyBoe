#!/usr/bin/env python3
"""
XRP / Ripple / Trump Crypto News Bot
=====================================
Holt aktuelle News zu XRP, Ripple und Trump Crypto
und uebersetzt sie automatisch ins Deutsche.

Installation:
    pip install "python-telegram-bot[job-queue]" feedparser deep-translator

Starten:
    python xrp_news_bot.py

Befehle:
    /start   - Willkommen
    /news    - Alle News (XRP + Ripple + Trump Crypto)
    /xrp     - Nur XRP & Ripple News
    /trump         - Nur Trump & Crypto Politik News
    /asiabrics     - Asien & BRICS Crypto News
    /institutionen - Elon Musk, BlackRock, JP Morgan & Co.
    /resetnews     - News-Verlauf zuruecksetzen
    /hilfe         - Befehlsuebersicht
"""

import asyncio
import json
import logging
import socket
import os
import time as _time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import feedparser
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Konfiguration ──────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("NEWS_BOT_TOKEN", "")
NEWS_COUNT  = int(os.environ.get("NEWS_COUNT", "5"))
BERLIN      = ZoneInfo("Europe/Berlin")

DATA_DIR      = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))
LOG_FILE      = os.path.join(DATA_DIR, "news_bot.log")
# Seen-Dateien werden pro User gespeichert: seen_xrp_<chat_id>.json
def seen_xrp_file(chat_id: str) -> str:
    return os.path.join(DATA_DIR, f"seen_xrp_{chat_id}.json")

def seen_trump_file(chat_id: str) -> str:
    return os.path.join(DATA_DIR, f"seen_trump_{chat_id}.json")

def seen_asia_file(chat_id: str) -> str:
    return os.path.join(DATA_DIR, f"seen_asia_{chat_id}.json")

def seen_inst_file(chat_id: str) -> str:
    return os.path.join(DATA_DIR, f"seen_inst_{chat_id}.json")

# Automatische News: Uhrzeit in Berliner Zeit
AUTO_HOUR_1   = int(os.environ.get("AUTO_HOUR_1", "7"))   # 07:00 Uhr
CACHE_TTL_MIN = int(os.environ.get("CACHE_TTL_MIN", "30")) # Cache-Lebenszeit in Minuten
AUTO_HOUR_2   = int(os.environ.get("AUTO_HOUR_2", "13"))  # 13:00 Uhr
AUTO_HOUR_3   = int(os.environ.get("AUTO_HOUR_3", "23"))  # 23:00 Uhr

# ── News-Quellen ───────────────────────────────────────────────────────────────
XRP_FEEDS = [
    # Crypto-Quellen
    "https://cointelegraph.com/rss/tag/ripple",
    "https://cryptonews.com/news/ripple-news/feed/",
    "https://www.newsbtc.com/feed/",
    "https://coinjournal.net/feed/",
    "https://ambcrypto.com/feed/",
    # Grosse US-Medien
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://feeds.washingtonpost.com/rss/business/technology",
    "https://feeds.washingtonpost.com/rss/business",
]
XRP_KEYWORDS = ["xrp", "ripple", "sec ripple", "xrp etf", "xrp ledger", "brad garlinghouse"]

TRUMP_FEEDS = [
    # Crypto-Quellen
    "https://cointelegraph.com/rss/tag/regulation",
    "https://cointelegraph.com/rss/tag/government",
    "https://decrypt.co/feed",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://www.newsbtc.com/feed/",
    # Grosse US-Medien (Politik + Wirtschaft)
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://feeds.washingtonpost.com/rss/politics",
    "https://feeds.washingtonpost.com/rss/business",
    "https://feeds.washingtonpost.com/rss/business/technology",
]
TRUMP_KEYWORDS = [
    "trump", "crypto reserve", "bitcoin reserve", "digital asset",
    "crypto policy", "white house crypto", "strategic reserve",
    "crypto regulation", "sec crypto", "coinbase sec",
]

# Asien & BRICS Crypto-News
ASIA_BRICS_FEEDS = [
    # Asien – Crypto-Medien
    "https://forkast.news/feed/",              # Hong Kong / Asien Fokus
    "https://www.theblock.co/rss.xml",          # The Block
    "https://blockworks.co/feed",               # Blockworks
    "https://coinpost.jp/?feed=rss2",           # CoinPost Japan
    # Indien
    "https://economictimes.indiatimes.com/tech/technology/rssfeeds/13357270.cms",
    "https://www.livemint.com/rss/markets",     # Mint Indien
    # China / Hongkong
    "https://www.scmp.com/rss/91/feed",         # South China Morning Post
    # Russland / BRICS
    "https://www.rt.com/rss/business/",         # RT Business
    # Brasilien
    "https://www.criptofacil.com/feed/",        # CriptoFacil Brasilien
    # Sued-Afrika
    "https://businesstech.co.za/news/feed/",    # BusinessTech SA
    # Allgemeine Crypto mit Asien-Fokus
    "https://cointelegraph.com/rss/tag/asia",
    "https://cointelegraph.com/rss/tag/brics",
]
ASIA_BRICS_KEYWORDS = [
    "xrp", "ripple", "cbdc", "digital yuan", "e-rupee", "e-cny",
    "brics", "brics currency", "brics digital", "brics crypto",
    "crypto asia", "blockchain asia", "ripple asia", "xrp asia",
    "digital rupee", "crypto india", "crypto china", "crypto russia",
    "crypto brazil", "crypto africa", "ripple partnership",
    "central bank digital", "cross-border payment",
]

# Institutionelle & Prominente Crypto-News
INSTITUTION_FEEDS = [
    "https://cointelegraph.com/rss/tag/elon-musk",
    "https://cointelegraph.com/rss/tag/institutional-adoption",
    "https://cointelegraph.com/rss/tag/blackrock",
    "https://cointelegraph.com/rss/tag/etf",
    "https://decrypt.co/feed",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://www.newsbtc.com/feed/",
    "https://blockworks.co/feed",
    "https://www.theblock.co/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://feeds.washingtonpost.com/rss/business",
]
INSTITUTION_KEYWORDS = [
    # Elon Musk
    "elon musk", "musk crypto", "musk bitcoin", "musk xrp", "doge musk",
    "elon musk ripple", "tesla crypto", "spacex crypto",
    # Evernode
    "evernode", "evernote crypto", "xahau", "evr token",
    # Ripple Prime
    "ripple prime", "ripple custody", "ripple enterprise",
    # BlackRock
    "blackrock crypto", "blackrock bitcoin", "blackrock xrp",
    "blackrock etf", "blackrock ripple", "blackrock digital",
    "larry fink", "blackrock blockchain",
    # JP Morgan
    "jp morgan crypto", "jpmorgan crypto", "jp morgan bitcoin",
    "jp morgan blockchain", "jpmorgan digital", "jamie dimon",
    "jp morgan xrp", "onyx blockchain",
    # Franklin Templeton
    "franklin templeton crypto", "franklin templeton bitcoin",
    "franklin templeton etf", "franklin templeton xrp",
    "franklin templeton blockchain", "benji token",
    # Allgemein Institutionell
    "institutional crypto", "wall street crypto",
    "asset manager crypto", "etf approval",
]

# ── Logging (muss vor allen Funktionen stehen die log nutzen) ─────────────────
_handlers = [logging.StreamHandler()]
try:
    _handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
except OSError as e:
    print(f"Log-Datei Fehler: {e}")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=_handlers,
)
log = logging.getLogger(__name__)


# ── Gesehene Artikel (verhindert Duplikate) ───────────────────────────────────
SEEN_MAX_DAYS = int(os.environ.get("SEEN_MAX_DAYS", "7"))  # Artikel nach X Tagen vergessen

def load_seen(path: str) -> set:
    """Laedt gesehene Links. Eintraege aelter als SEEN_MAX_DAYS Tage werden ignoriert."""
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        # Neues Format: {link: timestamp} – altes Format: [link, ...]
        if isinstance(data, list):
            return set(data)  # Altes Format ohne Zeitstempel
        cutoff = _time.time() - SEEN_MAX_DAYS * 86400
        return {link for link, ts in data.items() if ts > cutoff}
    except Exception:
        return set()

def save_seen(path: str, seen_links: set, max_size: int = 500) -> None:
    """Speichert gesehene Links mit Zeitstempel atomar."""
    # Bestehendes Dict laden (mit Zeitstempeln)
    existing = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                existing = raw
        except Exception:
            pass
    now = _time.time()
    for link in seen_links:
        existing[link] = now
    # Zu grosse Datei: aelteste Eintraege entfernen
    if len(existing) > max_size:
        sorted_items = sorted(existing.items(), key=lambda x: x[1])
        existing = dict(sorted_items[-max_size:])
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(existing, f)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"Fehler beim Speichern seen: {e}")


# ── News-Cache (verhindert zu viele RSS/Translate Anfragen bei vielen Usern) ──
class NewsCache:
    """Einfacher In-Memory Cache mit TTL fuer RSS-Artikel + Uebersetzungen."""
    def __init__(self, ttl_minutes: int = 30):
        self._ttl     = ttl_minutes * 60
        self._store   = {}  # key -> (value, timestamp)

    def get(self, key: str):
        if key in self._store:
            value, ts = self._store[key]
            if _time.monotonic() - ts < self._ttl:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value) -> None:
        self._store[key] = (value, _time.monotonic())

    def clear(self) -> None:
        self._store.clear()


_cache = NewsCache(ttl_minutes=CACHE_TTL_MIN)


# ── News abrufen ───────────────────────────────────────────────────────────────
def _fetch_news_raw(feeds: list, keywords: list, count: int = 10) -> list:
    """Interner RSS-Fetch ohne Cache und ohne Seen-Filter."""
    entries = []
    seen    = set()

    for feed_url in feeds:
        try:
            socket.setdefaulttimeout(8)
            try:
                feed = feedparser.parse(feed_url)
            finally:
                socket.setdefaulttimeout(None)

            for entry in feed.entries:
                title   = entry.get("title", "")
                link    = entry.get("link", "")
                summary = entry.get("summary", entry.get("description", ""))

                if link in seen or not title:
                    continue

                combined = (title + " " + summary).lower()
                if not any(kw in combined for kw in keywords):
                    continue

                seen.add(link)
                entries.append({
                    "title":           title,
                    "link":            link,
                    "source":          feed.feed.get("title", feed_url),
                    "published_parsed": entry.get("published_parsed"),
                })

                if len(entries) >= count * 4:
                    break

        except Exception as e:
            log.error(f"Feed-Fehler {feed_url}: {e}")

        # Genug Artikel gesammelt – restliche Feeds ueberspringen
        if len(entries) >= count * 4:
            break

    # Neueste zuerst sortieren
    entries.sort(
        key=lambda e: e.get("published_parsed") or (0,0,0,0,0,0,0,0,0),
        reverse=True
    )
    return entries[:count]


def fetch_news(feeds: list, keywords: list, count: int = 10,
               seen_file: str = None, mark_seen: bool = False) -> list:
    """
    Cache-gestützter Fetch: RSS wird max. alle CACHE_TTL_MIN Minuten abgerufen.
    Viele User teilen denselben Cache – drastisch weniger RSS-Anfragen.
    Seen-Filter bleibt pro User individuell.
    """
    cache_key   = f"news_{id(feeds)}_{count}"
    all_entries = _cache.get(cache_key)
    if all_entries is None:
        all_entries = _fetch_news_raw(feeds, keywords, count * 6)
        _cache.set(cache_key, all_entries)
        log.info(f"Cache MISS: {len(all_entries)} Artikel geladen")
    else:
        log.info(f"Cache HIT: {len(all_entries)} Artikel aus Cache")

    seen_old = load_seen(seen_file) if seen_file else set()
    result   = [e for e in all_entries if e["link"] not in seen_old][:count]

    if seen_file and mark_seen and result:
        save_seen(seen_file, seen_old | {e["link"] for e in result})

    return result


def translate_batch(texts: list) -> list:
    """
    Uebersetzt Texte ins Deutsche mit Cache.
    Gleiche Titel werden nie zweimal uebersetzt – spart Google-Anfragen.
    """
    if not texts:
        return texts
    results      = [None] * len(texts)
    to_translate = []
    indices      = []
    for i, t in enumerate(texts):
        cached = _cache.get(f"tr_{t[:60]}")
        if cached:
            results[i] = cached
        else:
            to_translate.append(t)
            indices.append(i)
    if to_translate:
        try:
            translated = GoogleTranslator(source="auto", target="de").translate_batch(to_translate)
            if len(translated) < len(to_translate):
                translated += to_translate[len(translated):]
            for idx, tr in zip(indices, translated):
                results[idx] = tr if tr else texts[idx]
                _cache.set(f"tr_{texts[idx][:60]}", results[idx])
        except Exception as e:
            log.warning(f"Uebersetzungsfehler: {e}")
            for idx in indices:
                results[idx] = texts[idx]
    return results


def escape_md(text: str) -> str:
    """Entfernt Telegram-Markdown-Sonderzeichen."""
    for ch in ["*", "_", "`", "[", "]", "(", ")", "~", ">", "#", "+", "=", "|", "{", "}", "!"]:
        text = text.replace(ch, "")
    return text.strip()


def format_news_msg(entries: list, titel: str) -> str:
    """Formatiert News-Liste als Telegram-Nachricht."""
    if not entries:
        return f"❌ Keine aktuellen {titel} News gefunden."

    titles    = [e["title"] for e in entries]
    titles_de = translate_batch(titles)

    lines = [f"📰 {titel}\n{datetime.now(BERLIN).strftime('%d.%m.%Y %H:%M')} Uhr\n"]
    for i, (e, title_de) in enumerate(zip(entries, titles_de), 1):
        # Quelle kennzeichnen
        src_name = e["source"]
        if "nytimes" in e["link"] or "New York Times" in src_name:
            label = "NYT"
        elif "washingtonpost" in e["link"] or "Washington Post" in src_name:
            label = "WaPo"
        elif "cointelegraph" in e["link"]:
            label = "CT"
        elif "decrypt" in e["link"]:
            label = "Decrypt"
        elif "coindesk" in e["link"]:
            label = "CoinDesk"
        else:
            label = "News"
        lines.append(f"{i}. [{label}] {escape_md(title_de)}")
        lines.append(f"   {e['link']}\n")

    return "\n".join(lines)


# ── Telegram Befehle ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # User-ID speichern fuer automatische News
    chat_id    = str(update.effective_chat.id)
    users_file = os.path.join(DATA_DIR, "users.json")
    try:
        if os.path.exists(users_file):
            with open(users_file) as f:
                users = json.load(f)
        else:
            users = []
        if chat_id not in users:
            users.append(chat_id)
            tmp = users_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(users, f)
            os.replace(tmp, users_file)
    except Exception as e:
        log.error(f"User speichern Fehler: {e}")

    await update.message.reply_text(
        "📰 *XRP & Trump Crypto News Bot*\n\n"
        "Aktuelle Nachrichten zu XRP, Ripple und Trump Crypto-Politik "
        "- automatisch ins Deutsche uebersetzt.\n\n"
        "📋 *Befehle:*\n"
        "• /news  - Alle News (XRP + Trump Crypto)\n"
        "• /xrp   - Nur XRP & Ripple News\n"
        "• /trump - Nur Trump & Crypto Politik\n"
        "• /resetnews - Verlauf zuruecksetzen\n"
        "• /hilfe - Befehlsuebersicht",
        parse_mode="Markdown",
    )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alle News: XRP + Ripple + Trump + Asien/BRICS + Institutionen."""
    await update.message.reply_text("⏳ Hole aktuelle News...")
    try:
        loop = asyncio.get_running_loop()

        # Alle 4 Kategorien parallel abrufen
        cid = str(update.effective_chat.id)
        xrp_entries, trump_entries, asia_entries, inst_entries = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda c=cid: fetch_news(
                    XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                    seen_file=seen_xrp_file(c), mark_seen=True
                )),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda c=cid: fetch_news(
                    TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                    seen_file=seen_trump_file(c), mark_seen=True
                )),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda c=cid: fetch_news(
                    ASIA_BRICS_FEEDS, ASIA_BRICS_KEYWORDS, NEWS_COUNT,
                    seen_file=seen_asia_file(c), mark_seen=True
                )),
                timeout=45.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda c=cid: fetch_news(
                    INSTITUTION_FEEDS, INSTITUTION_KEYWORDS, NEWS_COUNT,
                    seen_file=seen_inst_file(c), mark_seen=True
                )),
                timeout=45.0
            ),
        )

        # Alle 4 formatieren
        xrp_msg, trump_msg, asia_msg, inst_msg = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(xrp_entries, "XRP & Ripple News")),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(trump_entries, "Trump & Crypto Politik")),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(asia_entries, "Asien & BRICS Crypto")),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(inst_entries, "Institutionen & Elon Musk")),
                timeout=30.0
            ),
        )

        for msg in [xrp_msg, trump_msg, asia_msg, inst_msg]:
            if len(msg) > 4096:
                msg = msg[:4090] + "..."
            await update.message.reply_text(msg, disable_web_page_preview=True)

    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Zeitueberschreitung - bitte spaeter versuchen.")
    except Exception as e:
        log.error(f"News-Fehler: {e}")
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_xrp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nur XRP & Ripple News."""
    await update.message.reply_text("⏳ Hole XRP & Ripple News...")
    try:
        loop    = asyncio.get_running_loop()
        cid     = str(update.effective_chat.id)
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                seen_file=seen_xrp_file(cid), mark_seen=True
            )),
            timeout=30.0
        )
        msg = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: format_news_msg(entries, "XRP & Ripple News")),
            timeout=30.0
        )
        if len(msg) > 4096:
            msg = msg[:4090] + "..."
        await update.message.reply_text(msg, disable_web_page_preview=True)
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Zeitueberschreitung - bitte spaeter versuchen.")
    except Exception as e:
        log.error(f"XRP-News-Fehler: {e}")
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_trump(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nur Trump & Crypto Politik News."""
    await update.message.reply_text("⏳ Hole Trump & Crypto Politik News...")
    try:
        loop    = asyncio.get_running_loop()
        cid     = str(update.effective_chat.id)
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                seen_file=seen_trump_file(cid), mark_seen=True
            )),
            timeout=30.0
        )
        msg = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: format_news_msg(entries, "Trump & Crypto Politik")),
            timeout=30.0
        )
        if len(msg) > 4096:
            msg = msg[:4090] + "..."
        await update.message.reply_text(msg, disable_web_page_preview=True)
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Zeitueberschreitung - bitte spaeter versuchen.")
    except Exception as e:
        log.error(f"Trump-News-Fehler: {e}")
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_asiabrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Crypto News aus Asien und BRICS-Laendern rund um XRP & Ripple."""
    await update.message.reply_text("⏳ Hole Asien & BRICS Crypto News...")
    try:
        loop = asyncio.get_running_loop()
        cid  = str(update.effective_chat.id)
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                ASIA_BRICS_FEEDS, ASIA_BRICS_KEYWORDS, NEWS_COUNT,
                seen_file=seen_asia_file(cid), mark_seen=True
            )),
            timeout=45.0
        )
        msg = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: format_news_msg(
                entries, "Asien & BRICS Crypto News"
            )),
            timeout=30.0
        )
        if len(msg) > 4096:
            msg = msg[:4090] + "..."
        await update.message.reply_text(msg, disable_web_page_preview=True)
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Zeitueberschreitung - bitte spaeter versuchen.")
    except Exception as e:
        log.error(f"AsiaBrics-Fehler: {e}")
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_institutionen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Crypto News rund um Elon Musk, BlackRock, JP Morgan, Franklin Templeton, Evernode."""
    await update.message.reply_text(
        "⏳ Hole News zu Elon Musk, BlackRock, JP Morgan, Franklin Templeton & Evernode..."
    )
    try:
        loop = asyncio.get_running_loop()
        cid  = str(update.effective_chat.id)
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                INSTITUTION_FEEDS, INSTITUTION_KEYWORDS, NEWS_COUNT,
                seen_file=seen_inst_file(cid), mark_seen=True
            )),
            timeout=45.0
        )
        msg = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: format_news_msg(
                entries, "Institutionen & Elon Musk Crypto"
            )),
            timeout=30.0
        )
        if len(msg) > 4096:
            msg = msg[:4090] + "..."
        await update.message.reply_text(msg, disable_web_page_preview=True)
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Zeitueberschreitung - bitte spaeter versuchen.")
    except Exception as e:
        log.error(f"Institutionen-Fehler: {e}")
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_resetnews(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Setzt den Gesehen-Status zurueck – alle News erscheinen wieder neu."""
    chat_id = str(update.effective_chat.id)
    deleted = 0
    for path in [seen_xrp_file(chat_id), seen_trump_file(chat_id), seen_asia_file(chat_id), seen_inst_file(chat_id)]:
        if os.path.exists(path):
            os.remove(path)
            deleted += 1
    _cache.clear()  # Auch In-Memory Cache leeren
    await update.message.reply_text(
        "🔄 Gesehen-Status zurueckgesetzt!\n\n"
        "Beim naechsten /news oder /xrp erscheinen wieder alle aktuellen Artikel."
    )
    log.info(f"Seen-Reset fuer {chat_id}: {deleted} Dateien geloescht")


async def cmd_hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Befehlsuebersicht*\n\n"
        "/news  - Alle News auf einmal\n"
        "        XRP + Ripple + Trump Crypto\n\n"
        "/xrp   - Nur XRP & Ripple News\n"
        "        Quellen: CoinTelegraph, CryptoNews,\n"
        "        NewsBTC, NY Times, Washington Post\n\n"
        "/trump - Nur Trump & Crypto Politik\n"
        "        Quellen: CoinTelegraph, Decrypt,\n"
        "        CoinDesk, NY Times, Washington Post\n\n"
        "/start - Willkommen\n"
        "/resetnews - News-Verlauf zuruecksetzen\n\n"
        "🌍 Alle News automatisch auf Deutsch\n"
        "⏰ Automatisch um 07:00, 13:00 und 23:00 Uhr\n"
        "📍 Zeitzone: Europa/Berlin",
        parse_mode="Markdown",
    )


# ── Automatische News-Jobs ────────────────────────────────────────────────────
async def auto_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sendet automatisch News 3x taeglich an alle User.
    FIX: Kein 'update' in Job-Callbacks – nur 'context' verfuegbar.
    FIX: Pro User eigene seen-Datei -> jeder sieht nur seine neuen Artikel.
    """
    users_file = os.path.join(DATA_DIR, "users.json")
    if not os.path.exists(users_file):
        log.info("auto_news_job: Keine User-Datei – niemand hat /start getippt")
        return
    try:
        with open(users_file) as f:
            users = json.load(f)
    except Exception as e:
        log.error(f"auto_news_job: Fehler beim Laden der User: {e}")
        return

    if not users:
        return

    loop = asyncio.get_running_loop()

    # Pro User separat – jeder hat eigene seen-Datei
    for chat_id in users:
        cid = str(chat_id)
        try:
            xrp_entries, trump_entries, asia_entries, inst_entries = await asyncio.gather(
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda c=cid: fetch_news(
                        XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                        seen_file=seen_xrp_file(c), mark_seen=True
                    )),
                    timeout=30.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda c=cid: fetch_news(
                        TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                        seen_file=seen_trump_file(c), mark_seen=True
                    )),
                    timeout=30.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda c=cid: fetch_news(
                        ASIA_BRICS_FEEDS, ASIA_BRICS_KEYWORDS, NEWS_COUNT,
                        seen_file=seen_asia_file(c), mark_seen=True
                    )),
                    timeout=45.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda c=cid: fetch_news(
                        INSTITUTION_FEEDS, INSTITUTION_KEYWORDS, NEWS_COUNT,
                        seen_file=seen_inst_file(c), mark_seen=True
                    )),
                    timeout=45.0
                ),
            )
        except asyncio.TimeoutError:
            log.error(f"auto_news_job: Timeout fuer {cid}")
            continue
        except Exception as e:
            log.error(f"auto_news_job: Fetch-Fehler fuer {cid}: {e}")
            continue

        if not xrp_entries and not trump_entries and not asia_entries and not inst_entries:
            log.info(f"auto_news_job: Keine neuen Artikel fuer {cid}")
            continue

        try:
            xrp_msg, trump_msg, asia_msg, inst_msg = await asyncio.gather(
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda: format_news_msg(xrp_entries, "XRP & Ripple News")),
                    timeout=30.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda: format_news_msg(trump_entries, "Trump & Crypto Politik")),
                    timeout=30.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda: format_news_msg(asia_entries, "Asien & BRICS Crypto")),
                    timeout=30.0
                ),
                asyncio.wait_for(
                    loop.run_in_executor(None, lambda: format_news_msg(inst_entries, "Institutionen & Elon Musk")),
                    timeout=30.0
                ),
            )
        except asyncio.TimeoutError:
            log.error(f"auto_news_job: Format-Timeout fuer {cid}")
            continue
        except Exception as e:
            log.error(f"auto_news_job: Format-Fehler fuer {cid}: {e}")
            continue

        for msg in [xrp_msg, trump_msg, asia_msg, inst_msg]:
            if "Keine aktuellen" in msg:
                continue
            if len(msg) > 4096:
                msg = msg[:4090] + "..."
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=msg,
                    disable_web_page_preview=True,
                )
                log.info(f"auto_news_job: Gesendet an {cid}")
            except Exception as e:
                log.error(f"auto_news_job: Sendefehler {cid}: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    if not BOT_TOKEN:
        print("❌ NEWS_BOT_TOKEN nicht gesetzt!")
        print("   Railway: Variables -> NEWS_BOT_TOKEN = dein_token")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("news",  cmd_news))
    app.add_handler(CommandHandler("xrp",   cmd_xrp))
    app.add_handler(CommandHandler("trump", cmd_trump))
    app.add_handler(CommandHandler("hilfe",      cmd_hilfe))
    app.add_handler(CommandHandler("asiabrics",      cmd_asiabrics))
    app.add_handler(CommandHandler("institutionen",  cmd_institutionen))
    app.add_handler(CommandHandler("resetnews", cmd_resetnews))

    # Automatische News 3x taeglich (BERLIN und dtime als Top-Level)
    app.job_queue.run_daily(
        auto_news_job,
        time=dtime(hour=AUTO_HOUR_1, minute=0, tzinfo=BERLIN),
        name="auto_news_07"
    )
    app.job_queue.run_daily(
        auto_news_job,
        time=dtime(hour=AUTO_HOUR_2, minute=0, tzinfo=BERLIN),
        name="auto_news_13"
    )
    app.job_queue.run_daily(
        auto_news_job,
        time=dtime(hour=AUTO_HOUR_3, minute=0, tzinfo=BERLIN),
        name="auto_news_23"
    )

    log.info("XRP News Bot gestartet ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
