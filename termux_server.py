#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Локальний Termux-сервер: опитує Telegram та офіційну тривогу, віддає карту.

Запуск:  python termux_server.py
Карта:   http://127.0.0.1:8080  (лише локально, без доступу ззовні)
Сервер читає ті самі словники, що і Android-застосунок:
  app/src/main/assets/dictionaries.json
  app/src/main/assets/settlements.json
"""
import json
import os
import re
import sys
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "app", "src", "main", "assets")

CHANNELS = ["dnepr_nagladach", "eyes_everywhere_dnipro", "PmSDnepra", "TesterbotTrevoga"]
CHANNEL_UK = {
    "dnepr_nagladach": "Наглядач Дніпра",
    "eyes_everywhere_dnipro": "Очі Всюди",
    "PmSDnepra": "ПмС",
    "TesterbotTrevoga": "Тест",
}
ALERT_URL = "https://ubilling.net.ua/aerialalerts/"
POLL_CHANNELS = 20
POLL_ALERT = 60
PORT = 8080

LATIN_TO_CYR = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "y": "у", "i": "і", "b": "в"}


def normalize(text):
    t = (text or "").lower().replace("ё", "е").replace("ы", "и").replace("й", "і")
    t = t.replace("ъ", "").replace("'", "").replace("’", "").replace("`", "")
    out = []
    cyr = re.search(r"[а-яіїєґ]", t)
    for ch in t:
        if cyr and ch in LATIN_TO_CYR:
            out.append(LATIN_TO_CYR[ch])
        else:
            out.append(ch)
    return "".join(out).strip()


def load_json(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


try:
    DICT = load_json("dictionaries.json")
    SETTLEMENTS = load_json("settlements.json")
except Exception as e:
    print("Немає словників у %s: %s" % (ASSETS, e), file=sys.stderr)
    sys.exit(1)


STATUS_KEYS = ["overhead", "approach", "all_clear", "loiter", "lost", "redetected",
               "left", "transit", "no_threat", "tracked", "detected"]


def root_hits(norm, roots):
    words = norm.split()
    for root in roots:
        r = normalize(root)
        if " " in r:
            if r in norm:
                return True
        elif norm.startswith(r) or any(w.startswith(r) for w in words):
            return True
    return False


def status_of(norm):
    st = DICT.get("статуси", {})
    for sid in STATUS_KEYS:
        if root_hits(norm, st.get(sid, [])):
            return sid
    return "unknown"


def type_of(norm):
    for tid, roots in DICT.get("типи", {}).items():
        if root_hits(norm, roots):
            return tid
    return "ціль"


def direction_of(norm):
    for did, roots in DICT.get("напрямки", {}).items():
        if root_hits(norm, roots):
            return did
    return None


def is_noise(text):
    n = normalize(text)
    if re.search(r"\d{12,}", text):
        return True
    for m in DICT.get("шум", []):
        if normalize(m) in n:
            return True
    return False


def alert_echo(text):
    n = normalize(text)
    if "тривог" not in n and "тревог" not in n and "трiвог" not in n:
        return None
    off = ("відбій" in n or "отбой" in n or "зелен" in n or "🟢" in text)
    return {"kind": "alert_echo", "on": not off}


def build_index():
    idx = []
    for p in SETTLEMENTS:
        for a in [p.get("name", "")] + p.get("aliases", []):
            if a:
                idx.append((normalize(a).lower(), p))
    idx.sort(key=lambda x: -len(x[0]))
    return idx


GEO_IDX = build_index()


def geo_match(norm):
    found = []
    used = [False] * len(norm)
    for alias, place in GEO_IDX:
        pos = norm.find(alias)
        while pos >= 0:
            if not any(used[pos:pos + len(alias)]):
                for i in range(pos, pos + len(alias)):
                    used[i] = True
                found.append((pos, place))
                break
            pos = norm.find(alias, pos + 1)
    found.sort(key=lambda x: x[0])
    return [p for _, p in found]


def parse_message(raw, channel, ts):
    if is_noise(raw):
        return None
    n = normalize(raw)
    echo = alert_echo(raw)
    if echo:
        return {"kind": echo["kind"], "channel": channel, "raw": raw, "time": ts,
                "text": raw, "alert_on": echo["on"]}
    places = geo_match(n)
    new_markers = [normalize(x) for x in DICT.get("нова_ціль", [])]
    same_markers = [normalize(x) for x in DICT.get("той_самий", [])]
    parsed = {
        "kind": "target" if places else "feed",
        "channel": channel, "raw": raw, "text": raw, "time": ts,
        "type": type_of(n),
        "status": status_of(n),
        "direction": direction_of(n),
        "places": [p.get("name") for p in places],
        "coords": [(p["lat"], p["lon"]) for p in places],
        "count": None,
        "altitude": None,
        "new_hint": bool(re.search(r"\+\s?\d", raw)) or any(m in n for m in new_markers),
        "same_hint": any(m in n for m in same_markers),
    }
    m = re.search(r"\+\s?(\d)|(\d)х", raw)
    if m:
        parsed["count"] = int(m.group(1) or m.group(2))
    elif "пара" in n:
        parsed["count"] = 2
    ma = re.search(r"(висот|высот)[^0-9]{0,24}(\d{2,5})", n)
    if ma:
        parsed["altitude"] = int(ma.group(2))
    return parsed


class TrackStore:
    SAFE = {"no_threat", "left", "all_clear"}

    def __init__(self):
        self.tracks = []
        self.seq = 0

    def apply(self, parsed):
        if parsed["kind"] != "target":
            return
        if not parsed["coords"]:
            return
        target = None
        if parsed["same_hint"]:
            target = self._last()
        elif parsed["new_hint"] or not self.tracks:
            target = self._new()
        else:
            target = self._last()
        if target is None:
            return
        if parsed["status"] in self.SAFE and target["status"] not in self.SAFE:
            target["status"] = parsed["status"]
        else:
            target["status"] = parsed["status"]
        target["type"] = parsed["type"] if parsed["type"] != "ціль" else target["type"]
        target["count"] = parsed["count"] or target["count"]
        if parsed.get("direction"):
            target["heading"] = parsed["direction"]
        target["altitude_m"] = parsed["altitude"] or target.get("altitude_m")
        target["last_text"] = parsed["raw"]
        target["last_update"] = parsed["time"]
        target["channel"] = parsed["channel"]
        for name, (lat, lon) in zip(parsed["places"], parsed["coords"]):
            target["locations"].append({"name": name, "lat": lat, "lon": lon, "t": parsed["time"]})
        target["locations"] = target["locations"][-12:]

    def _new(self):
        self.seq += 1
        t = {"id": "t%d" % self.seq, "type": "ціль", "status": "unknown", "count": None,
             "altitude_m": None, "channel": "", "last_text": "", "last_update": 0,
             "locations": []}
        self.tracks.append(t)
        return t

    def _last(self):
        return self.tracks[-1] if self.tracks else None

    def prune(self):
        now = time.time()
        keep = []
        for t in self.tracks:
            age = now - (t["last_update"] or 0)
            limit = 2700 if t["status"] in self.SAFE else 8100
            if age < limit:
                keep.append(t)
        self.tracks = keep


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.tracks = TrackStore()
        self.feed = []
        self.alert_state = ""
        self.updated = int(time.time())
        self.sources = {}

    def snapshot(self):
        with self.lock:
            return {
                "updated": self.updated,
                "alerts": {"state": self.alert_state, "updated": self.updated},
                "tracks": list(self.tracks.tracks),
                "feed": list(self.feed)[-40:],
                "sources": [
                    {"name": k, "ok": v["ok"], "err": v["err"], "time": v["time"]}
                    for k, v in list(self.sources.items())
                ],
            }


STATE = State()


def tg_fetch(channel):
    url = "https://t.me/s/%s" % channel
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "replace")
    msgs = []
    for m in re.finditer(
            r'data-post="[^"]*?(\d+)".*?class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</', html, re.S):
        mid, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        text = (text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&nbsp;", " ")).strip()
        tm = re.search(r'datetime="([^"]+)"', html[max(0, m.start() - 2000):m.start()])
        ts = int(time.time())
        if tm:
            try:
                ts = int(time.mktime(time.strptime(tm.group(1)[:16], "%Y-%m-%dT%H:%M")))
            except Exception:
                pass
        msgs.append({"id": mid, "time": ts, "text": text})
    return msgs


def poll_channels():
    seen = {}
    while True:
        for ch in CHANNELS:
            try:
                for msg in tg_fetch(ch):
                    parsed = parse_message(msg["text"], ch, msg["time"])
                    with STATE.lock:
                        if msg["id"] not in seen or len(msg["text"]) > seen[msg["id"]]:
                            seen[msg["id"]] = len(msg["text"])
                            STATE.feed.append({
                                "channel": ch, "time": msg["time"],
                                "kind": parsed["kind"] if parsed else "noise",
                                "text": msg["text"],
                            })
                            if parsed and "alert_on" in parsed:
                                STATE.alert_state = "on" if parsed["alert_on"] else STATE.alert_state
                        if parsed and parsed["kind"] == "target":
                            prev = STATE.tracks.tracks[-1]["status"] if STATE.tracks.tracks else ""
                            STATE.tracks.apply(parsed)
                            cur = STATE.tracks.tracks[-1]["status"] if STATE.tracks.tracks else ""
                            if cur != prev and cur in ("approach", "overhead"):
                                notify(cur)
                STATE.tracks.prune()
            except Exception as e:
                print("poll %s: %s" % (ch, e), file=sys.stderr)
                STATE.sources[ch] = {"ok": False, "err": str(e)[:120], "time": int(time.time())}
            else:
                STATE.sources[ch] = {"ok": True, "err": "", "time": int(time.time())}
        with STATE.lock:
            STATE.updated = int(time.time())
            STATE.feed = STATE.feed[-40:]
        time.sleep(POLL_CHANNELS)


def notify(status):
    try:
        import subprocess
        uk = "Наближення цілі!" if status == "approach" else "Ціль над вами!"
        subprocess.Popen(["termux-notification", "--title", "Карта загроз", "--content", uk],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def poll_alert():
    while True:
        try:
            req = urllib.request.Request(ALERT_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            on = None
            for key, st in (data.get("states") or {}).items():
                if "ніпропетр" in key.lower() or "нiпропетр" in key.lower():
                    on = st.get("alertnow")
                    break
            with STATE.lock:
                if on is True or on is False:
                    STATE.alert_state = "on" if on else "off"
                STATE.sources["тривога"] = {"ok": True, "err": "", "time": int(time.time())}
        except Exception as e:
            print("alert: %s" % e, file=sys.stderr)
            with STATE.lock:
                STATE.sources["тривога"] = {"ok": False, "err": str(e)[:120], "time": int(time.time())}
        time.sleep(POLL_ALERT)


SHIM = ("<script>window.Android={getState:function(){var x=new XMLHttpRequest();"
        'x.open("GET","state.json?_="+Date.now(),false);x.send(null);'
        "return x.responseText;}};</script>")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/state.json":
            body = json.dumps(STATE.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path in ("/", "/index.html"):
            with open(os.path.join(ASSETS, "index.html"), encoding="utf-8") as f:
                html = f.read()
            html = html.replace("</head>", SHIM + "\n</head>")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/dnipro-geo.js", "/data-dict.js", "/pipeline.js"):
            with open(os.path.join(ASSETS, path[1:]), "rb") as f:
                self._send(200, f.read(), "application/javascript; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")


def main():
    threading.Thread(target=poll_channels, daemon=True).start()
    threading.Thread(target=poll_alert, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("Карта загроз: http://127.0.0.1:%d" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
