"""4-agent: admin bot. Qoralamani egasiga kanalda qanday chiqsa shunday ko'rinishda (media bilan) tugmalar
bilan ko'rsatadi; ostida faqat egasi uchun manba va sifat bahosi. Kanalga faqat postning o'zi chiqadi."""
import hashlib
import html
import json
import re
import os
import time

import httpx

MAX_TEXT = 4096
MAX_CAPTION = 1024


class Bot:
    def __init__(self, token=None):
        self.api = f"https://api.telegram.org/bot{token or os.environ['TELEGRAM_BOT_TOKEN']}"

    def call(self, method, files=None, **params):
        data = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items() if v is not None}
        r = httpx.post(f"{self.api}/{method}", data=data, files=files, timeout=120).json()
        if not r.get("ok"):
            raise RuntimeError(f"{method}: {r.get('description', r)}")
        return r["result"]

    def updates(self, offset):
        """Worker ulangan bo'lsa bosishlar uning navbatidan, aks holda getUpdates orqali olinadi."""
        worker, secret = (os.environ.get("WORKER_URL") or "").strip(), (os.environ.get("HOOK_SECRET") or "").strip()
        if worker and secret:
            # Telegram faqat [A-Za-z0-9_-] ni qabul qiladi, shuning uchun parolning sha256 xeshi yuboriladi.
            secret = hashlib.sha256(secret.encode()).hexdigest()
            self.ensure_webhook(worker, secret)
            r = httpx.get(f"{worker.rstrip('/')}/updates", headers={"x-hook-secret": secret}, timeout=60)
            r.raise_for_status()
            return sorted((u for u in r.json() if u["update_id"] >= offset), key=lambda u: u["update_id"])
        return self.call("getUpdates", offset=offset, timeout=0,
                         allowed_updates=["message", "callback_query"])

    def ensure_webhook(self, worker, secret):
        url = f"{worker.rstrip('/')}/tg"
        # Telegram parolni qaytarib bermaydi, shuning uchun parol o'zgarsa ham mos kelishi uchun har safar o'rnatiladi.
        self.call("setWebhook", url=url, secret_token=secret, allowed_updates=["message", "callback_query"])
        info = self.call("getWebhookInfo")
        if info.get("last_error_message"):
            print(f"Webhook oxirgi xatosi: {info['last_error_message']} (navbatda {info.get('pending_update_count', 0)})")

    # --- media ---
    @staticmethod
    def media_of(item):
        return json.loads(item.get("media") or "[]")

    @staticmethod
    def _download(url):
        for attempt in range(3):
            try:
                r = httpx.get(url, timeout=120, follow_redirects=True)
                r.raise_for_status()
                return r.content
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                time.sleep(3)

    @staticmethod
    def _file_id(msg):
        if msg.get("photo"):
            return msg["photo"][-1]["file_id"]
        return (msg.get("video") or msg.get("animation") or msg.get("document") or {}).get("file_id")

    def send_media(self, chat_id, media, caption=None, keyboard=None):
        """Media'ni yuboradi. m["file_id"] bo'lsa qayta yuklamaydi, bo'lmasa yuklab olib fayl sifatida jo'natadi.
        Qaytaradi: (keyboard qo'yish mumkin bo'lgan xabar yoki None, har bir media'ning file_id si)."""
        cap = {"caption": caption, "parse_mode": "HTML"} if caption else {}
        files, items = {}, []
        for i, m in enumerate(media[:10]):
            if m.get("file_id"):
                items.append((m, m["file_id"]))
            else:
                name = f"f{i}.{'mp4' if m['type'] == 'video' else 'jpg'}"
                files[name] = (name, self._download(m["url"]))
                items.append((m, f"attach://{name}"))
        if len(items) == 1:
            m, ref = items[0]
            method, field = ("sendVideo", "video") if m["type"] == "video" else ("sendPhoto", "photo")
            params = {field: ref} if not ref.startswith("attach://") else {}
            f = {field: files[ref[9:]]} if ref.startswith("attach://") else None
            msg = self.call(method, files=f, chat_id=chat_id, reply_markup=keyboard, **params, **cap)
            return msg, [self._file_id(msg)]
        group = [{"type": m["type"], "media": ref} for m, ref in items]
        if caption:
            group[0].update(caption=caption, parse_mode="HTML")
        msgs = self.call("sendMediaGroup", files=files or None, chat_id=chat_id, media=group)
        return None, [self._file_id(x) for x in msgs]

    def _post(self, chat_id, post, media, keyboard=None):
        """Postni kanalda chiqadigan ko'rinishda yuboradi. Qaytaradi: (tugmali xabar id, file_id lar)."""
        file_ids = []
        if media:
            if len(post) <= MAX_CAPTION:
                msg, file_ids = self.send_media(chat_id, media, caption=post, keyboard=keyboard)
                if msg:
                    return msg["message_id"], file_ids
                if keyboard is None:
                    return None, file_ids
                # albom: tugmalarni alohida xabarga qo'yamiz
                msg = self.call("sendMessage", chat_id=chat_id, text="⬆️ Albom bilan chiqadi", reply_markup=keyboard)
                return msg["message_id"], file_ids
            _, file_ids = self.send_media(chat_id, media)
        msg = self.call("sendMessage", chat_id=chat_id, text=post, parse_mode="HTML",
                        link_preview_options={"is_disabled": True}, reply_markup=keyboard)
        return msg["message_id"], file_ids

    # --- qoralama ---
    @classmethod
    def keyboard(cls, item):
        rows = [[
            {"text": "🔄 Qayta ishlash", "callback_data": f"redom:{item['id']}"},
            {"text": "🗑 Keraksiz", "callback_data": f"junk:{item['id']}"},
        ]]
        posted = (item.get("posted_to") or "").split(",")
        rows.append([
            {"text": "✅ Axmadjanov'ga yuborildi", "callback_data": "noop"} if "main" in posted else
            {"text": "📤 Kanalga yuborish Axmadjanov", "callback_data": f"send:{item['id']}"},
            {"text": "✅ Nodavlat'ga yuborildi", "callback_data": "noop"} if "nodavlat" in posted else
            {"text": "📤 Kanalga yuborish nodavlat", "callback_data": f"sendn:{item['id']}"},
        ])
        media = cls.media_of(item)
        if media:
            label = "🚫 Mediasiz chiqadi (qaytarish)" if item.get("media_off") else f"🖼 Media bilan chiqadi ({len(media)})"
            rows.append([{"text": label, "callback_data": f"media:{item['id']}"}])
        if item.get("prev_draft"):
            rows.append([{"text": "↩️ Avvalgi variantga qaytish", "callback_data": f"back:{item['id']}"}])
        return {"inline_keyboard": rows}

    @staticmethod
    def redo_keyboard(item):
        """"🔄 Qayta ishlash" bosilganda chiqadigan tanlovlar."""
        i = item["id"]
        return {"inline_keyboard": [
            [{"text": "🎩 Rasmiyroq", "callback_data": f"redof:{i}"},
             {"text": "🚫 Emojisiz", "callback_data": f"redop:{i}"}],
            [{"text": "🔄 Qayta ishlash", "callback_data": f"redo:{i}"}],
            [{"text": "⬅️ Orqaga", "callback_data": f"kb:{i}"}],
        ]}

    def set_keyboard(self, chat_id, msg_id, item, keyboard=None):
        self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id,
                  reply_markup=keyboard or self.keyboard(item))

    @staticmethod
    def footer(item, qc, short=False):
        """Faqat egasi uchun: manba va sifat bahosi. Kanalga chiqmaydi."""
        text = f"\n\n— — — — —\n🧾 {html.escape(item['url'] or item['source'])}\n🔎 Sifat: {qc.get('score', '?')}/10"
        if qc.get("agent"):
            text += f"\n✍️ {qc['agent']}-agent yozdi"
        issues = qc.get("issues") or []
        if issues and not short:
            text += "\n⚠️ " + html.escape("; ".join(issues))[:400]
        return text

    def send_draft(self, chat_id, item, post, qc):
        """Qoralama kanaldagi ko'rinishda, ostida manba va baho — bitta xabarda. Qaytaradi: (xabar id, file_id lar)."""
        media = self.media_of(item)
        limit = MAX_CAPTION if media and not item.get("media_off") else MAX_TEXT
        preview = post + self.footer(item, qc)
        if len(preview) > limit:
            preview = post + self.footer(item, qc, short=True)
        separate = len(preview) > limit  # sig'masa manba alohida xabarda
        try:
            msg_id, file_ids = self._post(chat_id, post if separate else preview, media, self.keyboard(item))
        except (RuntimeError, httpx.HTTPError) as e:
            # media yoki HTML xato bo'lsa ham qoralama yo'qolmasin: avval mediasiz, lekin formatlangan holda,
            # u ham bo'lmasa teglarsiz oddiy matn sifatida yuboriladi
            err = "Media yuklanmadi, mediasiz ko'rsatildi" if isinstance(e, httpx.HTTPError) else f"Yuborishda xato: {e}"
            qc = {**qc, "issues": [*qc.get("issues", []), err[:200]]}
            text = (post + self.footer(item, qc))[:MAX_TEXT]
            try:
                msg = self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                                link_preview_options={"is_disabled": True}, reply_markup=self.keyboard(item))
            except RuntimeError:
                msg = self.call("sendMessage", chat_id=chat_id, text=re.sub(r"</?(b|i|a)[^>]*>", "", text),
                                link_preview_options={"is_disabled": True}, reply_markup=self.keyboard(item))
            return msg["message_id"], []
        if separate:
            self.call("sendMessage", chat_id=chat_id, text=self.footer(item, qc).strip(), parse_mode="HTML",
                      reply_parameters={"message_id": msg_id}, link_preview_options={"is_disabled": True})
        return msg_id, file_ids

    def delete(self, chat_id, msg_id):
        """Qoralama xabarini o'chiradi; 48 soatdan eski bo'lsa o'chmaydi, unda belgi qo'yiladi."""
        try:
            self.call("deleteMessage", chat_id=chat_id, message_id=msg_id)
        except RuntimeError:
            self.mark(chat_id, msg_id, "🗑 Qoralamalardan olib tashlandi")

    def mark(self, chat_id, msg_id, note):
        """Tugmalarni olib tashlab, holatni yozib qo'yadi."""
        self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id,
                  reply_markup={"inline_keyboard": [[{"text": note, "callback_data": "noop"}]]})

    def answer(self, callback_id, text=None):
        try:
            self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except RuntimeError:
            pass  # eski tugma bosilgan bo'lsa Telegram rad etadi — muhim emas

    MENU = {"keyboard": [[{"text": "🔄 Yangilash"}]], "resize_keyboard": True, "is_persistent": True}

    def say(self, chat_id, text, menu=False, html_mode=False):
        self.call("sendMessage", chat_id=chat_id, text=text, reply_markup=self.MENU if menu else None,
                  parse_mode="HTML" if html_mode else None)

    def publish(self, channel, post, media=None):
        """Kanalga chiqarish (qoralamadagi file_id lar bilan, qayta yuklamasdan)."""
        try:
            self._post(channel, post, media or [])
        except (RuntimeError, httpx.HTTPError) as e:
            if not media:
                raise
            print(f"Media bilan chiqmadi, faqat matn: {e}")
            self._post(channel, post, [])
