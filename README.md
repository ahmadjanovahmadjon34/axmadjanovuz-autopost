# @Axmadjanovuz avtomatik post tizimi

4 agent:
1. **Yig'uvchi** — 31 ta Telegram kanal (t.me/s/ ochiq ko'rinishi) va Kun.uz, Daryo.uz, Gazeta.uz RSS'idan oxirgi 6 soatlik yangiliklarni oladi. Kalit so'z bor yangiliklar ustuvor, lekin so'zsiz ta'lim/ijtimoiy yangiliklar ham saqlanadi.
2. **Muharrir** (Claude) — eng muhim yangilikni tanlab, `style_examples.txt` uslubida post yozadi. Muhim yangilik bo'lmasa, post chiqarmaydi.
3. **Sifat nazoratchi** (Claude + qoidalar) — faktlarni manba bilan solishtiradi, imlo, format, imzo. 8/10 dan past bo'lsa muharrirga qaytaradi (3 urinish).
4. **Nashriyotchi** — admin bot orqali kanalga chiqaradi.

Vaqt: har 20 daqiqada tekshiriladi; 07:00–23:00 orasida, kuniga ko'pi bilan 5 ta, postlar orasida kamida 90 daqiqa. Hammasi `config.yaml` da.

## GitHub Actions sozlash
Settings → Secrets and variables → Actions:
- Secrets: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY` (sinov chati botga /start yozganingizda avtomatik topiladi)
- Standart holatda postlar faqat sizga (sinov) keladi. Kanalga chiqarish uchun Variables: `PUBLISH_MODE` = `live`

Qo'lda sinash: Actions → Avtomatik post → Run workflow → `post`.

## Lokal ishga tushirish
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... PUBLISH_MODE=preview PREVIEW_CHAT_ID=...
python main.py post
```
