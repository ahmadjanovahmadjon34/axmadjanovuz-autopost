import json
import re

import anthropic

_client = None


def ask_json(model, system, user, max_tokens=2000):
    global _client
    _client = _client or anthropic.Anthropic()
    msg = _client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                  messages=[{"role": "user", "content": user}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)
