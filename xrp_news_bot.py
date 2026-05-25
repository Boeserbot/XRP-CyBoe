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
    /trump   - Nur Trump & Crypto Politik News
    /hilfe   - Befehlsuebersicht
"""

import asyncio
import json
import logging
import socket
import os
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
SEEN_XRP_FILE = os.path.join(DATA_DIR, "seen_xrp.json")
SEEN_TRUMP_FILE = os.path.join(DATA_DIR, "seen_trump.json")

# Automatische News: Uhrzeit in Berliner Zeit
AUTO_HOUR_1   = int(os.environ.get("AUTO_HOUR_1", "13"))  # 13:00 Uhr
AUTO_HOUR_2   = int(os.environ.get("AUTO_HOUR_2", "23"))  # 23:00 Uhr

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

# ── Gesehene Artikel (verhindert Duplikate) ───────────────────────────────────
def load_seen(path: str) -> set:
    """Laedt bereits gesehene Artikel-Links aus Datei."""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_seen(path: str, seen: set, max_size: int = 500) -> None:
    """Speichert gesehene Links atomar. Behaelt nur die neuesten max_size Eintraege."""
    # sorted() fuer deterministische Reihenfolge; neueste bleiben erhalten
    lst = sorted(seen)[-max_size:]
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(lst, f)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"Fehler beim Speichern seen: {e}")


# ── Logging ────────────────────────────────────────────────────────────────────
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


# ── News abrufen ───────────────────────────────────────────────────────────────
def fetch_news(feeds: list, keywords: list, count: int = 10,
               seen_file: str = None, mark_seen: bool = False) -> list:
    """
    Holt News aus RSS-Feeds und filtert nach Keywords.
    seen_file: Pfad zur Datei mit bereits gesehenen Links (verhindert Duplikate).
    mark_seen: Wenn True, werden neue Links als gesehen markiert und gespeichert.
    """
    entries  = []
    seen     = set()
    seen_old = load_seen(seen_file) if seen_file else set()

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

                if link in seen or link in seen_old or not title:
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

                if len(entries) >= count * 2:
                    break

        except Exception as e:
            log.error(f"Feed-Fehler {feed_url}: {e}")

    # Neueste zuerst sortieren
    entries.sort(
        key=lambda e: e.get("published_parsed") or (0,0,0,0,0,0,0,0,0),
        reverse=True
    )
    result = entries[:count]
    # Neue Links als gesehen speichern
    if seen_file and mark_seen and result:
        new_seen = seen_old | {e["link"] for e in result}
        save_seen(seen_file, new_seen)
    return result


def translate_batch(texts: list) -> list:
    """Uebersetzt Liste von Texten ins Deutsche (ein Request)."""
    if not texts:
        return texts
    try:
        results = GoogleTranslator(source="auto", target="de").translate_batch(texts)
        # zip-safe: falls Google weniger Ergebnisse liefert, Original-Text als Fallback
        translated = [r if r else t for r, t in zip(results, texts)]
        # Fehlende Eintraege mit Originaltexten auffuellen
        if len(translated) < len(texts):
            translated += texts[len(translated):]
        return translated
    except Exception as e:
        log.warning(f"Uebersetzungsfehler: {e}")
        return texts


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
            with open(users_file, "w") as f:
                json.dump(users, f)
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
        "• /hilfe - Befehlsuebersicht",
        parse_mode="Markdown",
    )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alle News: XRP + Ripple + Trump Crypto."""
    await update.message.reply_text("⏳ Hole aktuelle News...")
    try:
        loop = asyncio.get_running_loop()

        # Beide Kategorien parallel abrufen
        xrp_entries, trump_entries = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: fetch_news(
                    XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                    seen_file=SEEN_XRP_FILE, mark_seen=True
                )),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: fetch_news(
                    TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                    seen_file=SEEN_TRUMP_FILE, mark_seen=True
                )),
                timeout=30.0
            ),
        )

        # Beide formatieren (Uebersetzung)
        xrp_msg, trump_msg = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(xrp_entries, "XRP & Ripple News")),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(trump_entries, "Trump & Crypto Politik")),
                timeout=30.0
            ),
        )

        for msg in [xrp_msg, trump_msg]:
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
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                seen_file=SEEN_XRP_FILE, mark_seen=True
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
        entries = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fetch_news(
                TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                seen_file=SEEN_TRUMP_FILE, mark_seen=True
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
        "/start - Willkommen\n\n"
        "🌍 Alle News automatisch auf Deutsch\n"
        "📍 Zeitzone: Europa/Berlin",
        parse_mode="Markdown",
    )


# ── Automatische News-Jobs ────────────────────────────────────────────────────
async def auto_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sendet automatisch News 2x taeglich an alle bekannten User."""
    # Alle User die jemals den Bot gestartet haben
    users_file = os.path.join(DATA_DIR, "users.json")
    if not os.path.exists(users_file):
        log.info("auto_news_job: Keine User-Datei gefunden")
        return
    try:
        with open(users_file) as f:
            users = json.load(f)
    except Exception as e:
        log.error(f"auto_news_job: Fehler beim Laden der User: {e}")
        return

    loop = asyncio.get_running_loop()
    try:
        xrp_entries, trump_entries = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: fetch_news(
                    XRP_FEEDS, XRP_KEYWORDS, NEWS_COUNT,
                    seen_file=SEEN_XRP_FILE, mark_seen=True
                )),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: fetch_news(
                    TRUMP_FEEDS, TRUMP_KEYWORDS, NEWS_COUNT,
                    seen_file=SEEN_TRUMP_FILE, mark_seen=True
                )),
                timeout=30.0
            ),
        )
        xrp_msg, trump_msg = await asyncio.gather(
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(xrp_entries, "XRP & Ripple News")),
                timeout=30.0
            ),
            asyncio.wait_for(
                loop.run_in_executor(None, lambda: format_news_msg(trump_entries, "Trump & Crypto Politik")),
                timeout=30.0
            ),
        )
    except asyncio.TimeoutError:
        log.error("auto_news_job: Zeitueberschreitung")
        return
    except Exception as e:
        log.error(f"auto_news_job: Fehler: {e}")
        return

    if not xrp_entries and not trump_entries:
        log.info("auto_news_job: Keine neuen Artikel")
        return

    for chat_id in users:
        for msg in [xrp_msg, trump_msg]:
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
            except Exception as e:
                log.error(f"auto_news_job: Sendefehler {chat_id}: {e}")


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
    app.add_handler(CommandHandler("hilfe", cmd_hilfe))

    # Automatische News 2x taeglich (BERLIN und dtime als Top-Level)
    app.job_queue.run_daily(
        auto_news_job,
        time=dtime(hour=AUTO_HOUR_1, minute=0, tzinfo=BERLIN),
        name="auto_news_13"
    )
    app.job_queue.run_daily(
        auto_news_job,
        time=dtime(hour=AUTO_HOUR_2, minute=0, tzinfo=BERLIN),
        name="auto_news_23"
    )

    log.info("XRP News Bot gestartet ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
