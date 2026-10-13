"""1-agent: filtrlar bo'yicha Telegram kanallar va rasmiy saytlardan yangilik izlaydi."""
from datetime import datetime, timedelta, timezone
import json
import re

import feedparser
import httpx
from bs4 import BeautifulSoup

from .storage import Store

HEADERS = {"User-Agent": "Mozilla/5.0 (axmadjanov.uz news bot)"}


def _norm(s):
    return s.lower().replace("‘", "'").replace("’", "'").replace("ʻ", "'").replace("ʼ", "'")


def _utc(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def keyword_score(text, kw):
    t = _norm(text)
    if any(_norm(x) in t for x in kw.get("exclude", [])):
        return -1
    return sum(1 for x in kw.get("include", []) if _norm(x) in t)


def fetch_telegram(channel, client):
    """Ochiq kanalning veb-ko'rinishidan (t.me/s/...) oxirgi postlarni oladi."""
    r = client.get(f"https://t.me/s/{channel}")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")  # html.parser t.me sahifasida ichma-ich joylashuvni buzadi
    for msg in soup.select(".tgme_widget_message"):
        body = msg.select_one(".tgme_widget_message_text")
        if not body:
            continue
        link = msg.get("data-post")
        when = msg.select_one(".tgme_widget_message_date time[datetime]")
        if not when and link:
            # html.parser ba'zan ichma-ich joylashuvni buzadi: vaqtni post havolasi orqali topamiz
            a = soup.find("a", class_="tgme_widget_message_date", href=f"https://t.me/{link}")
            when = a.find("time") if a else None
        media = []
        for el in msg.select(".tgme_widget_message_photo_wrap, video.tgme_widget_message_video, .tgme_widget_message_video_player video"):
            if el.name == "video":
                if el.get("src"):
                    media.append({"type": "video", "url": el["src"]})
            elif m := re.search(r"url\('(.+?)'\)", el.get("style", "")):
                media.append({"type": "photo", "url": m.group(1)})
        media = [x for i, x in enumerate(media) if x not in media[:i]][:10]
        yield {
            "source": f"t.me/{channel}",
            "url": f"https://t.me/{link}" if link else None,
            "title": "",
            "text": body.get_text("\n", strip=True),
            "image": media[0]["url"] if media else None,
            "media": json.dumps(media),
            "published": _utc(when.get("datetime")) if when else None,
        }


def fetch_rss(site, client):
    r = client.get(site["rss"])
    feed = feedparser.parse(r.content)
    for e in feed.entries:
        published = None
        if getattr(e, "published_parsed", None):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        summary = BeautifulSoup(e.get("summary", ""), "html.parser").get_text(" ", strip=True)
        yield {"source": site["name"], "url": e.get("link"), "title": e.get("title", ""),
               "text": summary, "image": None, "media": "[]", "published": published}


def fetch_page(site, client):
    """RSS bo'lmagan saytlar uchun: yangiliklar sahifasidagi sarlavha-havolalar."""
    r = client.get(site["url"])
    soup = BeautifulSoup(r.text, "html.parser")
    base = httpx.URL(site["url"])
    today = datetime.now(timezone.utc).date()
    seen = set()
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        href = base.join(a["href"])
        if len(title) < 40 or str(href) in seen or href.host != base.host:
            continue
        # maqola havolasida sana bo'ladi (/2026/10/13/...): eski yoki sanasiz bo'lim havolalarini tashlaymiz
        m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", href.path)
        if not m or (today - datetime(*map(int, m.groups())).date()).days > 1:
            continue
        seen.add(str(href))
        yield {"source": site["name"], "url": str(href), "title": title, "text": title,
               "image": None, "media": "[]", "published": None}


def fetch_article_text(url, client):
    """Sayt maqolasining to'liq matnini olishga urinadi (2-agentga ko'proq ma'lumot)."""
    try:
        soup = BeautifulSoup(client.get(url).text, "html.parser")
        paras = [p.get_text(" ", strip=True) for p in soup.select("article p, .content p, p")]
        return "\n".join(p for p in paras if len(p) > 60)[:6000]
    except Exception:
        return ""


def collect(cfg, store: Store, log=print):
    kw = cfg["keywords"]
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=cfg["schedule"]["max_age_hours"])).isoformat()
    added = 0
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        jobs = [(fetch_telegram, ch) for ch in cfg["sources"].get("telegram", [])]
        for site in cfg["sources"].get("sites", []):
            jobs.append((fetch_rss if site.get("rss") else fetch_page, site))
        for fn, arg in jobs:
            try:
                items = list(fn(arg, client))
            except Exception as e:
                log(f"[1-agent] {arg}: xato {e}")
                continue
            with_media = sum(1 for it in items if it.get("media", "[]") != "[]")
            if fn is fetch_telegram:
                log(f"[1-agent] {arg}: {len(items)} post, {with_media} tasida media")
            for it in items:
                it["published"] = it["published"] or now.isoformat()
                if it["published"] < cutoff:
                    continue
                # Kalit so'z bo'lmasa ham saqlanadi (ijtimoiy/ta'lim yangiligi bo'lishi mumkin),
                # faqat istisno so'z bo'lsa tashlanadi.
                score = keyword_score(it["title"] + " " + it["text"], kw)
                if score < 0 or len(it["text"]) < 40:
                    continue
                it["score"] = score
                it["id"] = Store.make_id(it["url"], it["text"])
                if store.exists(it["id"]):
                    store.fill_media(it["id"], it.get("media", "[]"))
                    continue
                if fn is not fetch_telegram and it["url"] and len(it["text"]) < 300 and score > 0:
                    it["text"] = fetch_article_text(it["url"], client) or it["text"]
                added += store.add(it)
    store.prune()
    log(f"[1-agent] {added} ta yangi yangilik saqlandi")
    return added
