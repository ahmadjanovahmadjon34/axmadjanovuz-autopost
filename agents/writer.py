"""2-agent: yangiliklar ichidan eng muhimini tanlab, kanal uslubida post yozadi."""
from pathlib import Path

from .llm import ask_json

SYSTEM = """Siz @Axmadjanovuz Telegram kanalining muharririsiz. Kanal auditoriyasi: abituriyentlar,
talabalar, ota-onalar, o'qituvchilar. Mavzular: {topics} (asosan ta'lim, qabul, OTM, nodavlat OTMlar,
grant/kontrakt, ijtimoiy masalalar).

Vazifa: berilgan yangiliklar ichidan kanal auditoriyasi uchun eng muhim, foydali va YANGI bittasini
tanlang va uni kanal uslubida o'zbek tilida (lotin yozuvida) post qilib yozing.
Kalit so'z bo'lmasa ham ta'lim va ijtimoiy yangiliklar mos bo'lishi mumkin. Sport, shou-biznes,
kriminal, reklama va kanal auditoriyasiga aloqasiz yangiliklarni tanlamang.

Bugun {posted} ta post chiqdi, kunlik limit {limit} ta. Agar hech bir yangilik haqiqatan muhim
bo'lmasa, tanlamang — kuchsiz post chiqargandan ko'ra kutgan yaxshi.

Uslub qoidalari (namunalarga qarang):
- Qisqa, e'tiborni tortuvchi birinchi qator (savol yoki ❗️ bilan muhim xabar).
- Emojilar o'rinli va kam: ❓ ✅ ❗️ ➡️ ➖ 1️⃣ 2️⃣.
- Faktlardan keyin qisqa izoh/xulosa: bu o'quvchi uchun nimani anglatadi.
- Manba havolasi gap ichida qavsda yoki so'zga biriktirilgan bo'lsin.
- Oxirida bo'sh qatordan keyin "{signature}", kerak bo'lsa hashtag (#Qabul2026 kabi).
- Faqat manbada bor faktlarni yozing, raqam, sana, ismlarni o'zgartirmang, hech narsa o'ylab topmang.
- Telegram HTML: faqat <b>, <i>, <a href="...">. Markdown (** yoki __) ishlatmang. & < > belgilarini
  matnda &amp; &lt; &gt; deb yozing.
- 300–1500 belgi.
- Manba boshqa kanal bo'lsa ham, uni so'zma-so'z ko'chirmang, o'z uslubingizda qayta yozing.

Kanal uslubidan namunalar:
{examples}

Faqat JSON qaytaring: {{"index": <tanlangan yangilik raqami>, "reason": "<nega tanlandi>", "post": "<post>"}}
Mos yangilik bo'lmasa: {{"index": -1, "reason": "...", "post": ""}}"""


def load_examples(path):
    p = Path(path)
    if not p.exists():
        return "(namuna yo'q)"
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return "\n".join(lines).strip() or "(namuna yo'q)"


def write_post(cfg, candidates, recent, posted_today, feedback=None, previous=None):
    system = SYSTEM.format(topics=", ".join(cfg["topics"]), posted=posted_today,
                           limit=cfg["schedule"]["max_posts_per_day"], signature=cfg["signature"],
                           examples=load_examples(cfg["style_examples_file"]))
    parts = [f"[{i}] Manba: {c['source']} | {c['url']} | {c['published']}\n{c['title']}\n{c['text'][:2500]}"
             for i, c in enumerate(candidates)]
    user = "Yangiliklar:\n\n" + "\n\n---\n\n".join(parts)
    if recent:
        user += "\n\nOxirgi chiqqan postlar (shu mavzularni takrorlamang):\n- " + "\n- ".join(recent)
    if feedback:
        user += (f"\n\nOldingi variant:\n{previous}\n\nSifat nazoratchisi e'tirozlari, tuzatib qayta yozing"
                 f" (xuddi shu yangilik bo'yicha):\n{feedback}")
    return ask_json(cfg["model"], system, user, max_tokens=3000)
