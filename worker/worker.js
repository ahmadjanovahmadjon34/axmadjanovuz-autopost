// Cloudflare Worker: bot tugmalarini darhol qabul qiladi va GitHub'dagi ishni shu zahoti ishga tushiradi.
// KV binding nomi: QUEUE. Sozlamalar BOT_TOKEN, GH_TOKEN, HOOK_SECRET, GH_REPO Worker o'zgaruvchisi
// sifatida yoki shu KV ichida kalit sifatida saqlanadi (o'zgaruvchi bo'lsa, u ustun).
const KEYS = ["BOT_TOKEN", "GH_TOKEN", "HOOK_SECRET", "GH_REPO"];

// Har bir kanal posti ostidagi izohga qo'yiladigan tugmalar (kanal username'i kichik harflarda).
const SOCIAL = {
  axmadjanovuz: [
    { text: "Instagram", url: "https://www.instagram.com/axmadjanov.uz/" },
    { text: "Telegram", url: "https://t.me/Axmadjanovuz" },
  ],
  nodavlattalim: [
    { text: "Instagram", url: "https://www.instagram.com/nodavlattalim" },
    { text: "Telegram", url: "https://t.me/nodavlattalim" },
    { text: "Veb-sayt", url: "https://nodavlattalim.uz" },
  ],
};

// "Yuborish" tugmalari shu kanallarga chiqaradi.
const CHANNELS = { main: "@Axmadjanovuz", nodavlat: "@nodavlattalim" };
const MAX_CAPTION = 1024;
const REDO = { redo: 1, redof: 1, redop: 1 };

async function config(env) {
  const c = {};
  for (const k of KEYS) c[k] = env[k] || (await env.QUEUE.get(k)) || "";
  for (const k of KEYS) c[k] = c[k].trim();
  // Telegram va GitHub Actions parolning o'zini emas, sha256 xeshini yuboradi.
  if (c.HOOK_SECRET) {
    const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(c.HOOK_SECRET));
    c.HOOK_SECRET = [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  if (!c.GH_REPO) c.GH_REPO = "ahmadjanovahmadjon34/axmadjanovuz-autopost";
  c.QUEUE = env.QUEUE;
  return c;
}

async function tg(env, method, body) {
  return fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
}

async function tgOk(env, method, body) {
  const r = await (await tg(env, method, body)).json();
  if (!r.ok) throw new Error(`${method}: ${r.description}`);
  return r.result;
}

// Kanalga chiqarish (GitHub'dagi bot.publish bilan bir xil tartib).
async function publish(env, chat, text, media) {
  const textMsg = () => tgOk(env, "sendMessage", {
    chat_id: chat, text, parse_mode: "HTML", link_preview_options: { is_disabled: true },
  });
  if (!media.length) return textMsg();
  try {
    const fits = [...text].length <= MAX_CAPTION;
    const cap = fits ? { caption: text, parse_mode: "HTML" } : {};
    if (media.length === 1) {
      const m = media[0];
      const field = m.type === "video" ? "video" : "photo";
      await tgOk(env, m.type === "video" ? "sendVideo" : "sendPhoto", { chat_id: chat, [field]: m.file_id, ...cap });
    } else {
      const group = media.slice(0, 10).map((m, i) => ({ type: m.type, media: m.file_id, ...(i === 0 ? cap : {}) }));
      await tgOk(env, "sendMediaGroup", { chat_id: chat, media: group });
    }
    if (!fits) await textMsg();
  } catch (e) {
    await textMsg();  // media bilan chiqmasa, matn baribir chiqsin
  }
}

function redoKeyboard(id) {
  return { inline_keyboard: [
    [{ text: "🎩 Rasmiyroq", callback_data: `redof:${id}` }, { text: "🚫 Emojisiz", callback_data: `redop:${id}` }],
    [{ text: "🔄 Qayta ishlash", callback_data: `redo:${id}` }],
    [{ text: "⬅️ Orqaga", callback_data: `kb:${id}` }],
  ] };
}

const mark = (note) => ({ inline_keyboard: [[{ text: note, callback_data: "noop" }]] });

// Tugmani GitHub'ni kutmasdan bajaradi. Qaytaradi: {text} — bajarildi, null — GitHub bajaradi.
async function instant(env, cb) {
  const [action, id] = [cb.data.split(":")[0], cb.data.slice(cb.data.indexOf(":") + 1)];
  const where = { chat_id: cb.message.chat.id, message_id: cb.message.message_id };
  const setKb = (reply_markup) => tg(env, "editMessageReplyMarkup", { ...where, reply_markup });
  if (REDO[action]) { await setKb(mark("🔄 Qayta ishlanmoqda...")); return { text: "Navbatga qo'yildi, 15 daqiqagacha qayta yoziladi" }; }
  if (action === "junk") { await setKb(mark("🗑 Keraksiz deb topildi")); return { text: "Yaroqsiz deb belgilandi" }; }
  if (action === "redom") { await setKb(redoKeyboard(id)); return { text: "Qanday qayta ishlansin?" }; }
  const raw = await env.QUEUE.get(`d:${id}`);
  if (!raw) return null;
  const d = JSON.parse(raw);
  if (action === "kb") { await setKb(d.keyboard); return { text: "" }; }
  if (action === "media" && d.has_media) {
    d.media_off = !d.media_off;
    for (const row of d.keyboard.inline_keyboard) for (const b of row) {
      if (b.callback_data === `media:${id}`) b.text = d.media_off ? "🚫 Mediasiz chiqadi (qaytarish)" : `🖼 Media bilan chiqadi (${d.media.length})`;
    }
    await env.QUEUE.put(`d:${id}`, JSON.stringify(d), { expirationTtl: 604800 });
    await setKb(d.keyboard);
    return { text: d.media_off ? "Mediasiz chiqadi" : "Media bilan chiqadi" };
  }
  if (action !== "send" && action !== "sendn") return null;
  const target = action === "send" ? "main" : "nodavlat";
  const posted = d.posted_to ? d.posted_to.split(",") : [];
  if (posted.includes(target)) return { text: "Allaqachon yuborilgan" };
  // media o'chirilgan bo'lsa yoki file_id lar yo'q bo'lsa — matn o'zi
  const media = d.media_off ? [] : d.media;
  await publish(env, CHANNELS[target], d.posts[target], media);
  // kanalga chiqdi: bundan keyingi xato GitHub'ga qayta chiqartirmasligi kerak
  try { await afterSend(env, d, id, action, target, posted, setKb); } catch (e) { /* tugma ko'rinishi GitHub'da tuzaladi */ }
  return { text: target === "main" ? "Axmadjanov kanaliga yuborildi" : "Nodavlat kanaliga yuborildi", sent: true };
}

async function afterSend(env, d, id, action, target, posted, setKb) {
  posted.push(target);
  d.posted_to = posted.join(",");
  for (const row of d.keyboard.inline_keyboard) for (const b of row) {
    if (b.callback_data === `${action}:${id}`) Object.assign(b, {
      text: target === "main" ? "✅ Axmadjanov'ga yuborildi" : "✅ Nodavlat'ga yuborildi", callback_data: "noop" });
  }
  await env.QUEUE.put(`d:${id}`, JSON.stringify(d), { expirationTtl: 604800 });
  await setKb(posted.length === 2 ? mark("✅ Ikkala kanalga yuborildi") : d.keyboard);
}

async function dispatch(env) {
  return fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/post.yml/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`, accept: "application/vnd.github+json",
      "user-agent": "axmadjanovuz-autopost-worker",
    },
    body: JSON.stringify({ ref: "main", inputs: { command: "run" } }),
  });
}

export default {
  async fetch(req, rawEnv) {
    const url = new URL(req.url);
    if (!["/tg", "/updates", "/stash"].includes(url.pathname)) return new Response("ok");
    const env = await config(rawEnv);
    if (!env.HOOK_SECRET) return new Response("not configured", { status: 503 });

    // Telegram webhook
    if (url.pathname === "/tg" && req.method === "POST") {
      if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.HOOK_SECRET) {
        return new Response("forbidden", { status: 403 });
      }
      const u = await req.json();
      const cb = u.callback_query;
      if (cb && cb.data === "noop") { await tg(env, "answerCallbackQuery", { callback_query_id: cb.id }); return new Response("ok"); }
      if (cb) {
        let done = null;
        try { done = await instant(env, cb); } catch (e) { done = null; }
        await tg(env, "answerCallbackQuery", {
          callback_query_id: cb.id, text: done ? done.text : "⏳ Qabul qilindi, 1 daqiqada bajariladi",
        });
        // GitHub baribir holatni yozadi; worker bajarganini qayta bajarmasligi uchun belgi qo'yamiz
        if (done) { cb.worker = true; if (done.sent) cb.worker_sent = true; }
      }
      // Kanalda yangi post chiqdi: izohlarga darhol birinchi bo'lib ijtimoiy tarmoqlar tugmalarini qoldiramiz.
      const origin = ((u.message && u.message.is_automatic_forward && u.message.forward_origin &&
        u.message.forward_origin.chat && u.message.forward_origin.chat.username) || "").toLowerCase();
      const social = SOCIAL[origin];
      if (social) {
        await tg(env, "sendMessage", {
          chat_id: u.message.chat.id, text: "📢 Bizni barcha ijtimoiy tarmoqlarda kuzatib boring:",
          reply_parameters: { message_id: u.message.message_id },
          reply_markup: { inline_keyboard: [social] },
        });
        return new Response("ok");
      }
      await env.QUEUE.put(`u:${String(u.update_id).padStart(12, "0")}`, JSON.stringify(u), { expirationTtl: 259200 });
      // Guruh izohlari navbatda kutadi (keyingi rejali ishda olinadi), GitHub daqiqalarini tejash uchun
      // ishni faqat tugma bosilganda yoki botga shaxsiy xabar kelganda darhol ishga tushiramiz.
      if (u.callback_query || (u.message && u.message.chat && u.message.chat.type === "private")) await dispatch(env);
      return new Response("ok");
    }

    // GitHub Actions tayyor qoralamani shu yerga beradi
    if (url.pathname === "/stash" && req.method === "POST" && req.headers.get("x-hook-secret") === env.HOOK_SECRET) {
      const d = await req.json();
      await env.QUEUE.put(`d:${d.id}`, JSON.stringify(d), { expirationTtl: 604800 });
      return Response.json({ stored: true });
    }

    // GitHub Actions navbatdagi bosishlarni shu yerdan oladi
    if (url.pathname === "/updates" && req.headers.get("x-hook-secret") === env.HOOK_SECRET) {
      const list = await env.QUEUE.list({ prefix: "u:" });
      const out = [];
      for (const k of list.keys) {
        const v = await env.QUEUE.get(k.name);
        if (v) out.push(JSON.parse(v));
        await env.QUEUE.delete(k.name);
      }
      return Response.json(out);
    }

    return new Response("ok");
  },
};
