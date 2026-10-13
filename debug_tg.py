import httpx
r = httpx.get("https://t.me/s/nodavlattalim", headers={"User-Agent": "Mozilla/5.0 (axmadjanov.uz news bot)"}, follow_redirects=True)
t = r.text
i = t.find("tgme_widget_message_date")
print(r.status_code, len(t), t.count("<time"), t.count("tgme_widget_message_text"))
print(t[i-200:i+400])
