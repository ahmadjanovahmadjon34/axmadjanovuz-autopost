# @Axmadjanovuz avtomatik post tizimi

Har 20 daqiqada (07:00–23:00, Toshkent) GitHub Actions ishga tushadi:

1. **Yig'uvchi** — 31 ta Telegram kanal (t.me/s/ ochiq ko'rinishi) va Kun.uz, Daryo.uz, Gazeta.uz'dan oxirgi 6 soatlik yangiliklarni oladi. Kalit so'z bor yangiliklar ustuvor, so'zsiz ta'lim/ijtimoiy yangiliklar ham saqlanadi.
2. **Muharrir** (Claude) — barcha yangi yangiliklarni tahlil qiladi, bir voqea haqidagi manbalarni birlashtiradi, muhimlarini tanlab `style_examples.txt` uslubida post yozadi. Kuniga o'rtacha 5 ta (cheklov emas).
3. **Sifat nazoratchi** (Claude + qoidalar) — faktlarni manba bilan solishtiradi, imlo, format, imzo. 8/10 dan past bo'lsa muharrirga qaytaradi.
4. **Admin bot** — qoralamani sizga shaxsiy chatda ikki tugma bilan yuboradi:
   - 🔄 **Qayta ishlash** — post yaxshiroq qilib qayta yoziladi (keyingi ishga tushishda, ≤20 daqiqa)
   - ✅ **Kanalga yuborish** — post kanalga chiqadi

Kanalga hech narsa sizning tasdig'ingizsiz chiqmaydi.

## Sozlash
Settings → Secrets and variables → Actions → Secrets:
- `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`
- Botga shaxsiy chatda `/start` yozing: birinchi yozgan odam bot egasi bo'ladi (yoki `OWNER_CHAT_ID` secret bilan qat'iy belgilang).
- Bot @Axmadjanovuz kanalida "Xabar yuborish" huquqi bilan admin bo'lishi kerak.

Manbalar, kalit so'zlar, imzo — `config.yaml`; uslub namunalari — `style_examples.txt`.
Qo'lda ishga tushirish: Actions → Avtomatik post → Run workflow.
