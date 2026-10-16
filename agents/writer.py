"""2-agent: barcha yangi yangiliklarni tahlil qiladi, muhimlarini tanlaydi va kanal uslubida post yozadi."""
from pathlib import Path

from .llm import ask_json

AUDIENCE = """@Axmadjanovuz Telegram kanali auditoriyasi: abituriyentlar, talabalar, ota-onalar, o'qituvchilar.
Mavzular: {topics} (asosan ta'lim, qabul, OTM, nodavlat OTMlar, grant/kontrakt, imtiyozlar, ijtimoiy masalalar)."""

TRIAGE = AUDIENCE + """

Vazifa: quyidagi barcha yangi yangiliklarni tahlil qiling va kanal uchun post qilishga arziydiganlarini tanlang.
- Bir xil voqea haqida bir nechta manba bo'lsa, bittasini asosiy qiling, qolganlarini "related" ga qo'shing.
- Kalit so'z bo'lmasa ham muhim ta'lim/ijtimoiy yangilik tanlanishi mumkin.
- Sport, shou-biznes, kriminal, reklama, obunaga chaqiruv, tabriklar va auditoriyaga aloqasizlarini tanlamang.
- Oxirgi chiqqan/tayyorlangan postlarni takrorlamang.
- Kanalda kuniga o'rtacha {avg} ta post chiqadi; bu qat'iy cheklov emas, muhim yangilik ko'p bo'lsa ko'proq
  tanlang, bo'lmasa kamroq. Lekin bitta tahlilda {cap} tadan ko'p tanlamang, eng muhimlarini oling.

Faqat JSON: {{"selected": [{{"index": 3, "related": [7, 12], "reason": "..."}}]}}"""

WRITE = AUDIENCE + """

Vazifa: berilgan yangilikdan kanal uslubida o'zbek tilida (lotin yozuvida) post yozing.

Uslub qoidalari (namunalarga qarang, eng yangi namunalar birinchi turadi):
- Birinchi qator — sarlavha: qisqa, aniq, butunlay <b>qalin</b>, boshida doim ⚡️ yoki ❗️ (emoji va
  sarlavha orasida bo'sh joy yo'q: "⚡️Sarlavha"); boshqa emoji faqat juda zarur holatda.
- Asosiy matn — qisqa xatboshilar (har biri 1–3 gap), oddiy va tushunarli, rasmiy-ishchan ohangda.
  Ro'yxat (➖) faqat bir nechta bir xil band sanalganda ishlatiladi; hamma narsani ro'yxatga aylantirmang.
- Hujjat asosi bo'lsa to'liq nomi bilan yozilsin: "Vazirlar Mahkamasining 2022-yil 15-avgustdagi 447-son
  qaroriga muvofiq". Postga hech qanday manba havolasi yoki "Manba" qatori QO'YILMAYDI
  (egasi talabi: xabarlarga manba kerak emas).
- Kerak bo'lsa, voqeaning fonini 1 xatboshida bering (avval nima bo'lgan, hozir nima o'zgaradi) —
  faqat manbadagi faktlar asosida.
- O'quvchiga amaliy ahamiyati bo'lsa, alohida qatorda savol-sarlavha va qisqa javob bering:
  "Talabalar uchun buning qanday foydasi bor?", "Ariza qayerga topshiriladi?". Javob faqat manbadagi
  faktlarga tayansin; taxmin bo'lsa "...mumkin" deb yozing. Shaxsiy fikr YOZILMAYDI.
- Namunalardagi barcha uslublar amalda: ularni birlashtirib, yangilikka mosini tanlang. 16.10.2026 namunasi
  ham ulardan biri xolos, har postga majburiy emas. Undan olinadigan usullar (mos kelsa): qisqa, bitta fikrli
  sarlavha; rasmiy tadbir/bayonotdan bo'lsa <blockquote>Bu haqda ... ma'lum qilindi.</blockquote> iqtibosi;
  oxirida <i>kursiv</i> bitta gap — chora nimaga qaratilgani ("Bu orqali ... ko'zda tutilmoqda"). Kursiv gap
  faqat manbadagi maqsad yoki undan bevosita kelib chiqadigan mazmunni aytsin, o'ylab topilmasin.
- Amaliy maslahat (qayerda tekshirish, qaysi platforma orqali ariza berish) bo'lsa, aniq yozing:
  "natijalarni my.uzbmb.uz orqali bilish mumkin".
- Rasmiy bayonot matni bo'lsa, oxirida manba idora nomi alohida qatorda: "Prezident matbuot kotibi".
- Qalin (<b>) me'yorida: sarlavha va 2–4 eng muhim raqam/sana/muddat.
- Oxirida bo'sh qatordan keyin "{signature}".
- Telegram HTML: faqat <b>, <i>, <blockquote>. Markdown (** yoki __) ishlatmang. & < > belgilarini
  matnda &amp; &lt; &gt; deb yozing.
- 400–1500 belgi. Yangilikda rasm/video bo'lsa ("Media: bor"), post 850 belgidan oshmasin,
  chunki u media ostiga izoh sifatida chiqadi.
- Manbani so'zma-so'z ko'chirmang, o'z uslubingizda qayta yozing.
- Faqat manbada bor faktlarni yozing, raqam, sana, ismlarni o'zgartirmang, hech narsa o'ylab topmang.
- Telegram HTML: faqat <b>, <i>, <blockquote>. Markdown (** yoki __) ishlatmang. & < > belgilarini
  matnda &amp; &lt; &gt; deb yozing.
- 300–1500 belgi. Yangilikda rasm/video bo'lsa ("Media: bor"), post 850 belgidan oshmasin,
  chunki u media ostiga izoh sifatida chiqadi.
- Manbani so'zma-so'z ko'chirmang, o'z uslubingizda qayta yozing.

Kanal uslubidan namunalar:
{examples}

Faqat JSON: {{"post": "<post>"}}"""


def load_examples(path):
    p = Path(path)
    if not p.exists():
        return "(namuna yo'q)"
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return "\n".join(lines).strip() or "(namuna yo'q)"


def _fmt(i, c, limit):
    media = "bor" if c.get("media") and c["media"] != "[]" else "yo'q"
    return (f"[{i}] {c['source']} | {c['url']} | {c['published'][:16]} | Media: {media}\n"
            f"{c['title']}\n{c['text'][:limit]}")


def select_news(cfg, items, recent):
    """Barcha yangi yangiliklarni bo'laklab tahlil qiladi. Qaytaradi: [(asosiy, [bog'liqlar], sabab)]."""
    out = []
    cap = cfg["review"]["max_drafts_per_run"]
    system = TRIAGE.format(topics=", ".join(cfg["topics"]), avg=cfg["review"]["avg_posts_per_day"], cap=cap)
    for start in range(0, len(items), 40):
        chunk = items[start:start + 40]
        user = "Yangiliklar:\n\n" + "\n\n".join(_fmt(i, c, 600) for i, c in enumerate(chunk))
        if recent:
            user += "\n\nOxirgi chiqqan/tayyorlangan postlar:\n- " + "\n- ".join(recent)
        res = ask_json(cfg["model"], system, user, max_tokens=2000)
        for s in res.get("selected", []):
            i = s.get("index")
            if isinstance(i, int) and 0 <= i < len(chunk):
                rel = [chunk[j] for j in s.get("related", []) if isinstance(j, int) and 0 <= j < len(chunk) and j != i]
                out.append((chunk[i], rel, s.get("reason", "")))
    return out[:cap]


# "🔄 Qayta ishlash" ichidagi tanlovlar (redo_mode)
REDO_TASKS = {
    "improve": ("Kanal egasi buni qayta ishlashni so'radi. Ancha yaxshiroq variant yozing: sarlavhani kuchliroq,"
                " faktlarni aniqroq va o'quvchi uchun foydaliroq joylashtiring, faktlarni saqlang."),
    "formal": ("Kanal egasi postni rasmiyroq qilishni so'radi. Rasmiy-ishchan uslubda qayta yozing: so'zlashuv"
               " iboralari, undovlar va ortiqcha emojisiz, aniq va vazmin jumlalar bilan. Faktlarni saqlang."),
    "no_emoji": ("Kanal egasi postni emojisiz qilishni so'radi. Matn va faktlarni saqlab, sarlavha va matndagi"
                 " barcha emojilarni olib tashlang (ro'yxat belgisi kerak bo'lsa \"—\" ishlating)."
                 " Faqat oxiridagi imzo o'zgarmaydi."),
}


# Yozuvchilar jamoasi (2-, 5-, 6-agent) qayta ishlashda: avval kamchiliklarni topib, keyin tuzatadi.
REDO_AGENT = ("Qayta ishlash: avval oldingi variantning kamchiliklarini aniqlang (zaif sarlavha, ortiqcha"
              " so'z, yashirin qolgan muhim fakt, noto'g'ri tartib), keyin ularni tuzatib, egasi tanlagan usulda yozing.")


def write_post(cfg, item, related=(), feedback=None, previous=None, improve=False):
    system = WRITE.format(topics=", ".join(cfg["topics"]), signature=cfg["signature"],
                          examples=load_examples(cfg["style_examples_file"]))
    user = "Asosiy manba:\n" + _fmt(0, item, 4000)
    if related:
        user += "\n\nShu voqea haqida boshqa manbalar:\n" + "\n\n".join(_fmt(i + 1, r, 1500) for i, r in enumerate(related))
    if previous and improve:
        user += (f"\n\nOldingi variant:\n{previous}\n\n" + REDO_AGENT + "\n"
                 + REDO_TASKS.get(improve, REDO_TASKS["improve"]))
    if feedback:
        user += f"\n\nOldingi variant:\n{previous}\n\nSifat nazoratchisi e'tirozlari, tuzatib qayta yozing:\n{feedback}"
    return ask_json(cfg["model"], system, user, max_tokens=3000).get("post", "")
