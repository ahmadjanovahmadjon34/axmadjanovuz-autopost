"""@Axmadjanovuz avtomatik post tizimi.

  python main.py run       # asosiy (GitHub Actions har 5 daqiqada):
                           #   1) botdagi tugma bosishlarini bajaradi
                           #   2) 1-agent: yangiliklarni yig'adi
                           #   3) 2-agent: hammasini tahlil qilib, muhimlaridan post yozadi
                           #   4) 3-agent: sifat nazorati
                           #   5) 4-agent: qoralamani sizga tugmalar bilan yuboradi
  python main.py collect   # faqat 1-agent
  python main.py export    # Claude routine uchun vazifa (ROUTINE.md ga qarang)
"""
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import sys

import yaml

from agents.bot import Bot
from agents.collector import collect
from agents.reviewer import review, rule_check
from agents.storage import Store, utcnow

OWNER_SOURCE = "📩 Siz yuborgan xabar"
TASHKENT = timezone(timedelta(hours=5))
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
        if msg and msg.get("chat", {}).get("type") == "private":
            chat = str(msg["chat"]["id"])
            if msg.get("text", "").startswith("/start"):
                if not owner_chat(store):
                    store.put("owner_chat_id", chat)
                    bot.say(chat, "✅ Siz bot egasi sifatida ro'yxatdan o'tdingiz. Post qoralamalari shu yerga keladi.",
                            menu=True)
                    store.put("menu_v1", 1)
                elif chat != owner_chat(store):
                    bot.say(chat, "Bu bot shaxsiy foydalanish uchun.")
                continue
            if chat != owner_chat(store):
                continue
            try:
                if msg.get("text") == "🔄 Yangilash":
                    bot.say(chat, status_text(store), menu=True, html_mode=True)
                else:
                    on_owner_message(store, bot, msg, chat)
            except Exception as e:
                print(f"Xabarni bajarishda xato: {e}")
                bot.say(chat, f"⚠️ Xato: {e}"[:1000])
            continue
        if msg and msg.get("chat", {}).get("type") in ("group", "supergroup"):
            on_group_message(cfg, store, bot, msg)
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


def _local(iso):
    if not iso:
        return None
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    mins = int((utcnow() - t).total_seconds() // 60)
    ago = f"{mins} daqiqa oldin" if mins < 60 else f"{mins // 60} soat {mins % 60} daqiqa oldin"
    return f"<b>{t.astimezone(TASHKENT):%d.%m %H:%M}</b> ({ago})"


def status_text(store):
    """"🔄 Yangilash" tugmasi: agentlar oxirgi marta qachon ishlagani."""
    collected = _local(store.get("last_collect"))
    analysed = _local(store.get("last_analysis"))
    waiting = len(store.by_status("drafted")) + len(store.by_status("redo"))
    lines = ["🔄 <b>Holat</b> (Toshkent vaqti)", ""]
    lines.append(f"🔎 1-agent yangiliklarni oxirgi marta izladi: {collected or 'hali yo‘q'}"
                 + (f", {store.get('last_collect_added', 0)} ta yangi topildi" if collected else ""))
    lines.append(f"✍️ Yozuvchilar jamoasi (2-, 5-, 6-agent) va 3-agent oxirgi marta ishladi: {analysed or 'hali yo‘q'}")
    lines.append(f"📋 Qaroringizni kutayotgan qoralamalar: {waiting} ta")
    by = {a: int(store.get(f"posted_by_{a}", 0)) for a in ("2", "5", "6")}
    lines += ["", f"📤 Kanalga chiqqan postlar: 2-agent {by['2']}, 5-agent {by['5']}, 6-agent {by['6']}"]
    lines += ["", f"1-agent har 5 daqiqada izlaydi; 2-3-agent har 15 daqiqada tahlil qiladi (navbatdagisi {next_analysis(quick=True)})."]
    return "\n".join(lines)


def next_analysis(quick=False):
    """Claude routine har soatning 07-daqiqasida to'liq tahlil qiladi; 22/37/52-daqiqalarda esa faqat
    qayta ishlash va siz yuborgan xabarlarni bajaradi (Toshkent vaqti)."""
    now = utcnow().astimezone(TASHKENT)
    t = now.replace(minute=7, second=0, microsecond=0)
    while t <= now:
        t += timedelta(minutes=15 if quick else 60)
    return f"soat {t:%H:%M} da"


def on_group_message(cfg, store, bot, msg):
    """Kanal izoh guruhidagi har qanday xabar: keyingi tahlilda yozuvchilar jamoasi javob yozadi va bot avtomatik qo'yadi."""
    if msg.get("is_automatic_forward"):
        # kanalda yangi post chiqdi: bot izohlarda birinchi bo'lib ijtimoiy tarmoqlar tugmalarini qoldiradi
        sc = cfg.get("social_comment")
        origin = ((msg.get("forward_origin") or {}).get("chat") or {}).get("username", "")
        if sc and origin.lower() == cfg["channel"].lstrip("@").lower():
            try:
                bot.call("sendMessage", chat_id=msg["chat"]["id"], text=sc["text"],
                         reply_parameters={"message_id": msg["message_id"]},
                         reply_markup={"inline_keyboard": [[{"text": b["text"], "url": b["url"]} for b in sc["buttons"]]]})
            except RuntimeError as e:
                print(f"Ijtimoiy tarmoqlar izohi yuborilmadi: {e}")
        return
    text = (msg.get("text") or msg.get("caption") or "").strip()
    sender = msg.get("from") or {}
    if not text or sender.get("is_bot") or msg.get("sender_chat") or msg.get("is_automatic_forward"):
        return
    parent = msg.get("reply_to_message") or {}
    chat_id = str(msg["chat"]["id"])
    store.add_comment({"id": f"{chat_id}:{msg['message_id']}", "chat_id": chat_id, "message_id": msg["message_id"],
                       "author": sender.get("first_name", ""), "text": text[:2000],
                       "post": (parent.get("text") or parent.get("caption") or "")[:1500],
                       "created": utcnow().isoformat()})


def on_owner_message(store, bot, msg, chat):
    """Egasi botga yuborgan (yoki forward qilgan) xabar: 2- va 3-agent undan post tayyorlaydi."""
    text = msg.get("text") or msg.get("caption") or ""
    media = []
    if msg.get("photo"):
        media = [{"type": "photo", "file_id": msg["photo"][-1]["file_id"]}]
    elif msg.get("video"):
        media = [{"type": "video", "file_id": msg["video"]["file_id"]}]
    key = f"bot:{chat}:{msg.get('media_group_id') or msg['message_id']}"
    item_id = key
    if store.exists(item_id):
        # albomning keyingi qismlari bitta yangilikka qo'shiladi
        item = store.item(item_id)
        store.set(item_id, media=json.dumps(Bot.media_of(item) + media))
        if text and not item["text"]:
            store.set(item_id, text=text, title=text.strip().split("\n")[0][:200])
        return
    origin = msg.get("forward_origin") or {}
    oc = origin.get("chat") or {}
    if (oc.get("username") or "").lower() == "nodavlattalim":
        # kanal imzosidagi premium gerb: id sini eslab qolamiz
        for e in (msg.get("entities") or []) + (msg.get("caption_entities") or []):
            if e.get("type") == "custom_emoji":
                store.put("nodavlat_emoji_id", e["custom_emoji_id"])
                break
    url = f"https://t.me/{oc['username']}/{origin.get('message_id')}" if oc.get("username") else ""
    store.add({"id": item_id, "source": OWNER_SOURCE, "url": url, "title": text.strip().split("\n")[0][:200],
               "text": text, "image": None, "media": json.dumps(media), "published": utcnow().isoformat(),
               "score": 100})
    Path(".fire_routine").touch()  # GitHub Actions 2-agentni darhol chaqiradi
    bot.say(chat, f"📥 Qabul qilindi. 2-agent navbatdagi tahlilda ({next_analysis(quick=True)}) birinchi bo'lib undan post "
                  "tayyorlaydi, 3-agent tekshirgach shu yerga keladi.", menu=True)


def publish_nodavlat(cfg, store, bot, post, media):
    """@nodavlattalim: post imzosiz chiqadi (Axmadjanovuz imzosi olib tashlanadi; kanal imzosini boshqa bot qo'yadi)."""
    bot.publish(cfg["channel2"], post.replace(cfg["signature"], "").rstrip(), media)


# "🔄 Qayta ishlash" ichidagi tanlovlar: tugma → routine'ga boriladigan redo_mode
REDO_MODES = {"redo": "improve", "redof": "formal", "redop": "no_emoji"}


def on_button(cfg, store, bot, cb, chat):
    """Tugma: "send" — kanalga chiqarish, "redo" — qayta ishlash."""
    action, _, item_id = cb.get("data", "").partition(":")
    item = store.item(item_id)
    msg_id = cb["message"]["message_id"]
    if not item or action == "noop":
        bot.answer(cb["id"])
        return
    if action in ("send", "sendn"):
        target = "main" if action == "send" else "nodavlat"
        posted = [c for c in (item["posted_to"] or ("main" if item["status"] == "posted" else "")).split(",") if c]
        if target in posted:
            bot.answer(cb["id"], "Allaqachon yuborilgan")
            return
        media = [] if item["media_off"] else Bot.media_of(item)
        if target == "main":
            bot.publish(cfg["channel"], item["draft"], media)
        else:
            publish_nodavlat(cfg, store, bot, item["draft"], media)
        posted.append(target)
        store.set(item_id, status="posted", posted_to=",".join(posted))
        agent = json.loads(item["qc"] or "{}").get("agent")
        if agent and len(posted) == 1:
            store.put(f"posted_by_{agent}", int(store.get(f"posted_by_{agent}", 0)) + 1)
        name = "Axmadjanov" if target == "main" else "Nodavlat"
        if len(posted) == 2:
            bot.mark(chat, msg_id, "✅ Ikkala kanalga yuborildi")
        else:
            bot.set_keyboard(chat, msg_id, store.item(item_id))
        bot.answer(cb["id"], f"{name} kanaliga yuborildi")
        print(f"[4-agent] {name} kanaliga yuborildi: {item['url']}")
    elif action == "junk":
        store.set(item_id, status="rejected")
        bot.mark(chat, msg_id, "🗑 Keraksiz deb topildi")
        bot.answer(cb["id"], "Yaroqsiz deb belgilandi")
    elif action == "back":
        if not item.get("prev_draft"):
            bot.answer(cb["id"], "Avvalgi variant yo'q")
            return
        # variantlarni almashtiramiz: avvalgisi yangi xabar bo'lib keladi, undan yana qaytish mumkin
        store.set(item_id, status="drafted", draft=item["prev_draft"], qc=item["prev_qc"],
                  prev_draft=item["draft"], prev_qc=item["qc"], msg_id=None)
        bot.mark(chat, msg_id, "↩️ Avvalgi variant pastda")
        bot.answer(cb["id"], "Avvalgi variant qaytarildi")
        send_unsent(store, bot, chat)
    elif action == "media":
        store.set(item_id, media_off=0 if item["media_off"] else 1)
        item = store.item(item_id)
        bot.set_keyboard(chat, msg_id, item)
        bot.answer(cb["id"], "Mediasiz chiqadi" if item["media_off"] else "Media bilan chiqadi")
    elif action == "redom":
        bot.set_keyboard(chat, msg_id, item, Bot.redo_keyboard(item))
        bot.answer(cb["id"], "Qanday qayta ishlansin?")
    elif action == "kb":
        bot.set_keyboard(chat, msg_id, item)
        bot.answer(cb["id"])
    elif action in REDO_MODES and not os.environ.get("ANTHROPIC_API_KEY"):
        # post yozuvchi Claude routine keyingi ishga tushishida qayta yozadi
        store.set(item_id, status="redo", redo_mode=REDO_MODES[action])
        bot.answer(cb["id"], f"Navbatga qo'yildi: {next_analysis(quick=True)} qayta yoziladi")
        bot.mark(chat, msg_id, "🔄 Qayta ishlanmoqda...")
    elif action in REDO_MODES:
        bot.answer(cb["id"], "Qayta ishlanmoqda...")
        related = [store.item(i) for i in json.loads(item["related"] or "[]")]
        res = produce(cfg, item, [r for r in related if r], previous=item["draft"], improve=REDO_MODES[action])
        if not res:
            bot.say(chat, "Qayta ishlab bo'lmadi, eski variant qoldi.")
            return
        post, qc = res
        store.set(item_id, draft=post, qc=json.dumps(qc, ensure_ascii=False), msg_id=None,
                  prev_draft=item["draft"], prev_qc=item["qc"])
        bot.mark(chat, msg_id, "♻️ Yangi variant pastda")
        send_unsent(store, bot, chat)
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
        save_sent(store, item, *bot.send_draft(chat, item, post, qc))
        print(f"[4-agent] Qoralama yuborildi: {item['url']} — {reason}")
    # tanlanmagan va bog'liq yangiliklar qayta ko'rilmaydi
    store.mark_new_as([i["id"] for i in items if i["id"] not in used], "skipped")
    store.mark_new_as(list(used), "skipped")


def ingest_inbox(store, bot, chat):
    """Claude routine (Pro obuna) yozgan qoralamalarni inbox/ dan oladi va sizga yuboradi."""
    for f in sorted(Path("inbox").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        store.mark_new_as(data.get("processed_ids", []), "skipped")
        # egasi so'ragan: kutilayotgan qoralamalarni botdan olib tashlash
        for rid in data.get("reject_ids", []):
            item = store.item(rid)
            if not item or item["status"] not in ("drafted", "redo"):
                continue
            store.set(rid, status="rejected")
            if item["msg_id"]:
                try:
                    bot.delete(chat, item["msg_id"])
                except RuntimeError:
                    pass
        for r in data.get("comment_replies", []):
            c = store.comment(r.get("id", ""))
            if not c or c["status"] != "new":
                continue
            if not r.get("reply"):
                store.set_comment(c["id"], status="skipped")
                continue
            try:
                bot.call("sendMessage", chat_id=c["chat_id"], text=r["reply"], parse_mode="HTML",
                         reply_parameters={"message_id": c["message_id"]}, link_preview_options={"is_disabled": True})
                store.set_comment(c["id"], status="answered", reply=r["reply"])
            except RuntimeError as e:
                store.set_comment(c["id"], status="failed", reply=str(e)[:300])
                print(f"Izohga javob berib bo'lmadi: {e}")
        for d in data.get("drafts", []):
            item = store.item(d["id"])
            # "revive": egasi keraksiz deb belgilagan postni qayta yuborishni so'ragan
            if not item or not d.get("post") or item["status"] == "posted" \
                    or (item["status"] == "rejected" and not d.get("revive")):
                continue
            qc = d.get("qc") or {}
            for k in ("agent",):
                if d.get(k) is not None:
                    qc[k] = d[k]
            qc["issues"] = rule_check(d["post"], bool(Bot.media_of(item)), item["url"]) + qc.get("issues", [])
            fields = dict(draft=d["post"], qc=json.dumps(qc, ensure_ascii=False))
            if d.get("related"):
                fields["related"] = json.dumps(d["related"])
            if d.get("prev_draft"):
                fields.update(prev_draft=d["prev_draft"], prev_qc=json.dumps(d.get("prev_qc") or {}, ensure_ascii=False))
            elif item["msg_id"] and item["draft"] and item["draft"] != d["post"]:
                fields.update(prev_draft=item["draft"], prev_qc=item["qc"])
            if item["msg_id"]:
                # qayta ishlangan/yangilangan variant: eskisini belgilab, yangisini yuboramiz
                try:
                    bot.mark(chat, item["msg_id"], "♻️ Yangi variant pastda")
                except RuntimeError:
                    pass
            store.set(item["id"], status="drafted", msg_id=None, **fields)
        try:
            store.put("last_analysis", datetime.strptime(f.stem[:15], "%Y%m%dT%H%M%S")
                      .replace(tzinfo=timezone.utc).isoformat())
        except ValueError:
            store.put("last_analysis", utcnow().isoformat())
        f.unlink()
    send_unsent(store, bot, chat)


def save_sent(store, item, msg_id, file_ids):
    media = Bot.media_of(item)
    if media and len(file_ids) == len(media):
        media = [{**m, "file_id": fid} for m, fid in zip(media, file_ids)]
        store.set(item["id"], media=json.dumps(media))
    store.set(item["id"], msg_id=msg_id)


def send_unsent(store, bot, chat):
    for item in store.unsent_drafts():
        save_sent(store, item, *bot.send_draft(chat, item, item["draft"], json.loads(item["qc"] or "{}")))
        print(f"[4-agent] Qoralama yuborildi: {item['url']}")


def export_task(cfg, store):
    """Claude routine uchun: tahlil qilinadigan yangiliklar va qayta ishlash so'rovlari."""
    pending = set()
    for f in Path("inbox").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        pending.update(data.get("processed_ids", []))
        pending.update(d["id"] for d in data.get("drafts", []))
        pending.update(r["id"] for r in data.get("comment_replies", []))
    fields = ("id", "source", "url", "title", "text", "published", "score", "media")
    fresh = store.new_items(cfg["schedule"]["max_age_hours"])
    # egasi yuborgan xabarlar eskirgan bo'lsa ham albatta ko'riladi
    fresh += [i for i in store.by_status("new") if i["source"] == OWNER_SOURCE and i not in fresh]
    items = [{k: i[k] for k in fields} for i in fresh if i["id"] not in pending]
    redo = []
    for i in store.by_status("redo"):
        if i["id"] in pending:
            continue
        related = [store.item(r) for r in json.loads(i["related"] or "[]")]
        redo.append({**{k: i[k] for k in fields}, "previous_draft": i["draft"], "redo_mode": i["redo_mode"] or "improve",
                     "related": [{k: r[k] for k in fields} for r in related if r]})
    comments = [{k: c[k] for k in ("id", "author", "text", "post")} for c in store.comments()
                if c["id"] not in pending]
    task = {"owner_source": OWNER_SOURCE, "new_items": items, "redo": redo, "comments": comments, "recent_posts": store.recent_topics(),
            "signature": cfg["signature"], "avg_posts_per_day": cfg["review"]["avg_posts_per_day"],
            "max_drafts": cfg["review"]["max_drafts_per_run"], "min_quality_score": cfg["min_quality_score"]}
    print(json.dumps(task, ensure_ascii=False, indent=1))


def run(cfg, store):
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        collect(cfg, store)
        print("Bot tokeni yo'q: faqat yangiliklar yig'ildi.")
        return
    bot = Bot()
    try:
        handle_updates(cfg, store, bot)
    except Exception as e:  # tugmalardagi xato yangi qoralamalarni to'xtatib qo'ymasin
        print(f"XATO (tugmalar): {e}")
    added = collect(cfg, store)
    store.put("last_collect", utcnow().isoformat())
    store.put("last_collect_added", added or 0)
    chat = owner_chat(store)
    if chat and not store.get("menu_v1"):
        bot.say(chat, "Pastda 🔄 Yangilash tugmasi paydo bo'ldi: bossangiz agentlar oxirgi marta qachon "
                      "ishlaganini ko'rsatadi. Botga istalgan xabarni yuborsangiz yoki forward qilsangiz, "
                      "undan post tayyorlanadi.", menu=True)
        store.put("menu_v1", 1)
    if not chat:
        print("Egasi aniqlanmagan: botga shaxsiy chatda /start yozing.")
        return
    if not store.get("kb_v3"):
        # kutayotgan eski qoralamalarga ham yangi tugmalarni (ikki kanal, qayta ishlash tanlovlari) qo'yamiz
        for item in store.by_status("drafted"):
            if item["msg_id"]:
                try:
                    bot.set_keyboard(chat, item["msg_id"], item)
                except RuntimeError:
                    pass
        store.put("kb_v3", 1)
    ingest_inbox(store, bot, chat)
    if os.environ.get("ANTHROPIC_API_KEY"):
        # API kaliti bo'lsa, 2- va 3-agent shu yerda ishlaydi (aks holda Claude routine bajaradi)
        make_drafts(cfg, store, bot, chat)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg, store = load_config(), Store()
    {"run": lambda: run(cfg, store), "collect": lambda: collect(cfg, store),
     "export": lambda: export_task(cfg, store)}[cmd]()
