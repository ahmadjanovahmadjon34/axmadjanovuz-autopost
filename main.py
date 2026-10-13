"""@Axmadjanovuz avtomatik post tizimi.

  python main.py run       # asosiy (GitHub Actions har 20 daqiqada):
                           #   1) botdagi tugma bosishlarini bajaradi
                           #   2) 1-agent: yangiliklarni yig'adi
                           #   3) 2-agent: hammasini tahlil qilib, muhimlaridan post yozadi
                           #   4) 3-agent: sifat nazorati
                           #   5) 4-agent: qoralamani sizga tugmalar bilan yuboradi
  python main.py collect   # faqat 1-agent
"""
import json
import os
import sys

import yaml

from agents.bot import Bot
from agents.collector import collect
from agents.reviewer import review
from agents.storage import Store
from agents.writer import select_news, write_post


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def owner_chat(store):
    return os.environ.get("OWNER_CHAT_ID") or store.get("owner_chat_id")


def produce(cfg, item, related, previous=None, improve=False, attempts=3):
    """2- va 3-agent: yozish → tekshirish → kerak bo'lsa qayta yozish. Eng yaxshi variantni qaytaradi."""
    best = None
    post = previous
    feedback = None
    for _ in range(attempts):
        post = write_post(cfg, item, related, feedback, post, improve and feedback is None)
        if not post:
            break
        qc = review(cfg, post, item)
        post = qc.get("fixed_post") or post
        print(f"[3-agent] {item['url']}: {qc.get('score')}/10 {qc['issues']}")
        if best is None or qc.get("score", 0) > best[1].get("score", 0):
            best = (post, qc)
        if qc["ok"]:
            break
        feedback = "\n".join(qc["issues"])
    return best


def handle_updates(cfg, store, bot):
    """Botga kelgan /start va tugma bosishlarini bajaradi."""
    offset = int(store.get("tg_offset", 0))
    for u in bot.updates(offset):
        store.put("tg_offset", u["update_id"] + 1)
        msg = u.get("message")
        if msg and msg.get("chat", {}).get("type") == "private" and msg.get("text", "").startswith("/start"):
            chat = str(msg["chat"]["id"])
            if not owner_chat(store):
                store.put("owner_chat_id", chat)
                bot.say(chat, "✅ Siz bot egasi sifatida ro'yxatdan o'tdingiz. Post qoralamalari shu yerga keladi.")
            elif chat != owner_chat(store):
                bot.say(chat, "Bu bot shaxsiy foydalanish uchun.")
            continue
        cb = u.get("callback_query")
        if not cb:
            continue
        chat = str(cb["message"]["chat"]["id"])
        if chat != owner_chat(store):
            bot.answer(cb["id"], "Ruxsat yo'q")
            continue
        try:
            on_button(cfg, store, bot, cb, chat)
        except Exception as e:
            print(f"Tugmani bajarishda xato: {e}")
            bot.say(chat, f"⚠️ Xato: {e}"[:1000])


def on_button(cfg, store, bot, cb, chat):
    """Tugma: "send" — kanalga chiqarish, "redo" — qayta ishlash."""
    action, _, item_id = cb.get("data", "").partition(":")
    item = store.item(item_id)
    msg_id = cb["message"]["message_id"]
    if not item or action == "noop":
        bot.answer(cb["id"])
        return
    if action == "send":
        if item["status"] == "posted":
            bot.answer(cb["id"], "Allaqachon yuborilgan")
            return
        bot.publish(cfg["channel"], item["draft"], item.get("image"))
        store.set(item_id, status="posted")
        bot.mark(chat, msg_id, "✅ Kanalga yuborildi")
        bot.answer(cb["id"], "Kanalga yuborildi")
        print(f"[4-agent] Kanalga yuborildi: {item['url']}")
    elif action == "redo":
        bot.answer(cb["id"], "Qayta ishlanmoqda...")
        related = [store.item(i) for i in json.loads(item["related"] or "[]")]
        res = produce(cfg, item, [r for r in related if r], previous=item["draft"], improve=True)
        if not res:
            bot.say(chat, "Qayta ishlab bo'lmadi, eski variant qoldi.")
            return
        post, qc = res
        store.set(item_id, draft=post, qc=json.dumps(qc, ensure_ascii=False))
        bot.edit_draft(chat, msg_id, item, post, qc)
        print(f"[2-agent] Qayta ishlandi: {item['url']}")


def make_drafts(cfg, store, bot, chat):
    items = store.new_items(cfg["schedule"]["max_age_hours"])
    if not items:
        print("Yangi yangilik yo'q.")
        return
    picked = select_news(cfg, items, store.recent_topics())
    print(f"[2-agent] {len(items)} ta yangilikdan {len(picked)} tasi tanlandi")
    used = set()
    for item, related, reason in picked:
        if item["id"] in used:
            continue
        used.update([item["id"], *(r["id"] for r in related)])
        res = produce(cfg, item, related)
        if not res:
            store.set(item["id"], status="rejected")
            continue
        post, qc = res
        store.set(item["id"], status="drafted", draft=post, qc=json.dumps(qc, ensure_ascii=False),
                  related=json.dumps([r["id"] for r in related]))
        msg_id = bot.send_draft(chat, item, post, qc)
        store.set(item["id"], msg_id=msg_id)
        print(f"[4-agent] Qoralama yuborildi: {item['url']} — {reason}")
    # tanlanmagan va bog'liq yangiliklar qayta ko'rilmaydi
    store.mark_new_as([i["id"] for i in items if i["id"] not in used], "skipped")
    store.mark_new_as(list(used), "skipped")


def run(cfg, store):
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("ANTHROPIC_API_KEY")):
        collect(cfg, store)
        print("Kalitlar yo'q: faqat yangiliklar yig'ildi.")
        return
    bot = Bot()
    handle_updates(cfg, store, bot)
    collect(cfg, store)
    chat = owner_chat(store)
    if not chat:
        print("Egasi aniqlanmagan: botga shaxsiy chatda /start yozing.")
        return
    make_drafts(cfg, store, bot, chat)
    handle_updates(cfg, store, bot)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg, store = load_config(), Store()
    {"run": lambda: run(cfg, store), "collect": lambda: collect(cfg, store)}[cmd]()
