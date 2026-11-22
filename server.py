#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карта загроз — Дніпропетровщина. Весь проєкт: Python + HTML.

Логика полностью в Python: опрос Telegram (Telethon с твоим api_id/api_hash,
фолбэк — web-превью t.me/s/<канал>), парсинг постов, треки, тревога с ubilling.
HTML только рисует векторную карту.

Запуск:  python server.py            (сначала впиши api_id/api_hash в config.json)
Карта:   http://127.0.0.1:8080
"""
import json
import math
import os
import re
import sys
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
STATIC = os.path.join(BASE, "static")

DEFAULT_CHANNELS = ["dnepr_nagladach", "eyes_everywhere_dnipro", "PmSDnepra", "TesterbotTrevoga"]
ALERT_URL = "https://ubilling.net.ua/aerialalerts/"
POLL_CHANNELS = 15
POLL_ALERT = 60
VISIBLE_SEC = 300
HOST = "127.0.0.1"
PORT = 8080

LATIN_TO_CYR = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "y": "у", "i": "і"}

STATUS_KEYS = ["overhead", "approach", "all_clear", "loiter", "lost", "redetected",
               "left", "transit", "no_threat", "tracked", "detected"]
SAFE_STATUSES = {"no_threat", "left", "all_clear"}
ACTIVE_STATUSES = {"detected", "tracked", "transit", "approach", "overhead", "loiter",
                   "unknown", "redetected"}
BIG_CITIES = [
    ("Дніпро", 48.4647, 35.0462),
    ("Кривий Ріг", 47.9105, 33.3918),
    ("Нікополь", 47.5716, 34.4003),
    ("Кам'янське", 48.5136, 34.6006),
    ("Павлоград", 48.5334, 35.8676),
]
THREAT_RADIUS_KM = 45
MARK_TTL_ACTIVE = 7200
MARK_TTL_SAFE = 2700


def normalize(text):
    t = (text or "").lower()
    t = t.replace("ё", "е").replace("э", "е").replace("ы", "і").replace("и", "і").replace("й", "і").replace("ґ", "г")
    t = t.replace("ъ", "").replace("'", "").replace("’", "").replace("`", "")
    if re.search(r"[а-яіїєґ]", t):
        t = "".join(LATIN_TO_CYR.get(c, c) for c in t)
    return t.strip()


def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


try:
    DICT = load_json("dictionaries.json")
    PLACES = load_json("settlements.json")
except Exception as e:
    print("Нет словарей в data/: %s" % e, file=sys.stderr)
    sys.exit(1)


def root_hits(norm, roots):
    words = norm.split()
    for root in roots or []:
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


def dict_first(norm, obj):
    for did, roots in (obj or {}).items():
        if root_hits(norm, roots):
            return did
    return None


def is_noise(raw, norm):
    if re.search(r"\d{12,}", raw):
        return True
    for m in DICT.get("шум", []):
        if normalize(m) in norm:
            return True
    return False


GEO_IDX = []
STOP_GEO = {"с", "з", "і", "и", "в", "у", "к", "на", "до", "от", "из", "за", "по",
            "пгт", "смт", "село", "селище", "раион", "область", "обл", "город", "города", "городу",
            "трасса", "траса", "км", "год"}


def _cp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _dl_le1(a, b):
    if a == b:
        return True
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diff) == 1:
            return True
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if abs(len(a) - len(b)) != 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def _hit(tok, w):
    if tok == w:
        return True
    if len(w) >= 4 and tok.startswith(w) and len(tok) - len(w) <= 4:
        return True
    if len(tok) >= 4 and w.startswith(tok) and len(w) - len(tok) <= 4:
        return True
    if len(w) >= 5 and _cp(tok, w) >= len(w) - 2 and abs(len(tok) - len(w)) <= 2:
        return True
    return False


def _occ_hit(tok, w):
    return tok == w or (len(w) >= 3 and tok.startswith(w) and len(tok) - len(w) <= 2)


def _occ_phrase(tokens, i, words):
    if i + len(words) > len(tokens):
        return False
    return all(tokens[i + k] == words[k] or _hit(tokens[i + k], words[k]) for k in range(len(words)))


def _tokens(norm):
    return re.findall(r"[а-щьюяіїєґa-z0-9\-]+", norm)


def occupied_spans(tokens):
    occ = set()
    for key in ("напрямки", "статуси", "типи"):
        for roots in (DICT.get(key) or {}).values():
            for root in roots or []:
                words = normalize(root).split()
                if not words:
                    continue
                if len(words) == 1:
                    w = words[0]
                    if key != "напрямки" and len(w) < 4:
                        continue
                    for i, tok in enumerate(tokens):
                        if _occ_hit(tok, w):
                            occ.add(i)
                else:
                    n = len(words)
                    for i in range(len(tokens) - n + 1):
                        if _occ_phrase(tokens, i, words):
                            for k in range(n):
                                occ.add(i + k)
    return occ


def build_geo():
    for p in PLACES:
        for a in [p.get("name", "")] + p.get("aliases", []):
            na = normalize(a)
            if na:
                GEO_IDX.append((tuple(na.split()), p))
    GEO_IDX.sort(key=lambda x: (-len(x[0]), -max(len(w) for w in x[0])))


build_geo()


def geo_match(tokens, occupied=None):
    occupied = occupied or set()
    ok = [i for i, t in enumerate(tokens)
          if t not in STOP_GEO and i not in occupied]
    found = []
    for words, place in GEO_IDX:
        n = len(words)
        for i in ok:
            if i + n > len(tokens) or any((i + k) in occupied for k in range(n)):
                continue
            if all(_hit(tokens[i + k], words[k]) for k in range(n)):
                found.append((i, n, place))
                break
    if not found:
        for i in ok:
            tok = tokens[i]
            if len(tok) < 6:
                continue
            for words, place in GEO_IDX:
                if len(words) == 1 and len(words[0]) >= 6 and _dl_le1(tok, words[0]):
                    found.append((i, 1, place))
                    break
    found.sort(key=lambda x: (x[0], -x[1]))
    out, seen = [], set()
    for _, _, p in found:
        if p.get("name") not in seen:
            seen.add(p.get("name"))
            out.append(p)
    return out[:6]
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for _, p in found:
        if p.get("name") not in seen:
            seen.add(p.get("name"))
            out.append(p)
    return out


def dist_km(la1, lo1, la2, lo2):
    R, rad = 6371.0, math.pi / 180
    dla, dlo = (la2 - la1) * rad, (lo2 - lo1) * rad
    a = math.sin(dla / 2) ** 2 + math.cos(la1 * rad) * math.cos(la2 * rad) * math.sin(dlo / 2) ** 2
    return 2 * R * math.atan2(a ** 0.5, (1 - a) ** 0.5)


def parse_message(raw, channel, ts):
    n = normalize(raw)
    if is_noise(raw, n):
        return None
    toks = _tokens(n)
    occ = occupied_spans(toks)
    if "трівог" in n or "тревог" in n:
        rl = (raw or "").lower()
        off = ("відбій" in rl or "отбой" in rl or "\U0001F7E2" in raw or "зелен" in n)
        echo = {"kind": "alert_echo", "channel": channel, "raw": raw, "time": ts,
                "text": raw, "alert_on": not off}
        ep = geo_match(toks, occ)
        echo["places"] = [p.get("name") for p in ep]
        echo["coords"] = [(p["lat"], p["lon"]) for p in ep]
        return echo
    places = geo_match(toks, occ)
    if any(not pl.get("rajon") for pl in places):
        places = [pl for pl in places if not pl.get("rajon")]
    m = re.search(r"\+\s?(\d{1,2})|(\d{1,2})\s?[хx](?=$|[\s,.;])", raw)
    ma = re.search(r"(висот|высот)[^0-9]{0,24}(\d{2,5})", n)
    return {
        "kind": "target" if places else "feed",
        "channel": channel, "raw": raw, "text": raw, "time": ts,
        "type": dict_first(n, DICT.get("типи")) or "ціль",
        "status": status_of(n),
        "direction": dict_first(n, DICT.get("напрямки")),
        "places": [p.get("name") for p in places],
        "coords": [(p["lat"], p["lon"]) for p in places],
        "count": int(m.group(1) or m.group(2)) if m else (2 if "пара" in n else None),
        "altitude": int(ma.group(2)) if ma else None,
        "new_hint": bool(re.search(r"\+\s?\d", raw)) or root_hits(n, DICT.get("нова_ціль", [])),
        "same_hint": root_hits(n, DICT.get("той_самий", [])),
    }


class TrackStore:
    def __init__(self):
        self.tracks = []
        self.seq = 0

    @staticmethod
    def marker_of(t):
        if t["status"] == "unknown" and t["type"] == "ціль":
            return "?"
        return "+"

    @staticmethod
    def color_of(t):
        if t["status"] == "lost":
            return "gray"
        if t["status"] == "unknown" and t["type"] == "ціль":
            return "red"
        if t["status"] in ("approach", "overhead"):
            return "red"
        if t["status"] in SAFE_STATUSES:
            return "yellow"
        for loc in t["locations"]:
            for _, la, lo in BIG_CITIES:
                if dist_km(loc["lat"], loc["lon"], la, lo) < THREAT_RADIUS_KM:
                    return "red"
        return "yellow"

    def apply(self, p):
        if not p["coords"]:
            return
        target = None
        if p["same_hint"]:
            target = self._last_active() or (self.tracks[-1] if self.tracks else None)
        elif p["new_hint"] or not self.tracks:
            target = None
        else:
            target = self._last_active()
        if target is None:
            self.seq += 1
            target = {"id": "t%d" % self.seq, "channel": p["channel"], "type": "ціль",
                      "status": "unknown", "count": None, "altitude_m": None,
                      "heading": None, "pattern": False, "last_text": "",
                      "last_update": 0, "locations": []}
            self.tracks.append(target)
        if p["status"]:
            target["status"] = p["status"]
        if p["type"] != "ціль":
            target["type"] = p["type"]
        if p["count"] and (not target["count"] or p["count"] > target["count"]):
            target["count"] = p["count"]
        if p["altitude"]:
            target["altitude_m"] = p["altitude"]
        if p["direction"]:
            target["heading"] = p["direction"]
        if p["status"] == "loiter":
            target["pattern"] = True
        target["last_text"] = p["raw"]
        target["last_update"] = p["time"]
        target["channel"] = p["channel"]
        for name, (lat, lon) in zip(p["places"], p["coords"]):
            locs = target["locations"]
            if not locs or locs[-1]["name"] != name:
                locs.append({"name": name, "lat": lat, "lon": lon, "t": p["time"]})
            target["locations"] = locs[-12:]

    def _last_active(self):
        found = None
        for t in self.tracks:
            if ACTIVE_STATUSES & {t["status"]} or t["status"] in ("lost", "redetected"):
                found = t
        return found

    def prune(self):
        now = time.time()
        keep = []
        for t in self.tracks:
            age = now - (t["last_update"] or 0)
            limit = MARK_TTL_SAFE if t["status"] in SAFE_STATUSES else MARK_TTL_ACTIVE
            if age < limit:
                keep.append(t)
        self.tracks = keep

    def snapshot_tracks(self):
        now = time.time()
        out = []
        for t in list(self.tracks):
            age = now - (t["last_update"] or 0)
            if age > VISIBLE_SEC:
                continue
            view = dict(t)
            view["color"] = self.color_of(t)
            view["marker"] = self.marker_of(t)
            out.append(view)
        return out


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
                "tracks": self.tracks.snapshot_tracks(),
                "feed": list(self.feed)[-40:],
                "sources": [{"name": k, "ok": v["ok"], "err": v["err"], "time": v["time"]}
                            for k, v in list(self.sources.items())],
            }


STATE = State()


class TelethonPoller:
    def __init__(self, api_id, api_hash, phone, channels):
        self.channels = channels
        self.min_id = {ch: 0 for ch in channels}
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            from telethon import TelegramClient
        except ImportError:
            print("Telethon не установлен: pip install telethon", file=sys.stderr)
            with STATE.lock:
                STATE.sources["telegram"] = {"ok": False, "err": "нет telethon", "time": int(time.time())}
            return
        import asyncio

        async def main():
            client = TelegramClient(os.path.join(BASE, "tg_session"), self.api_id, self.api_hash)
            if self.phone and "X" not in self.phone:
                await client.start(phone=self.phone)
            else:
                await client.start()
            me = await client.get_me()
            print("Telegram: авторизован как %s" % (me.first_name or me.username))
            while True:
                for ch in self.channels:
                    try:
                        entity = await client.get_entity(ch)
                        msgs = []
                        async for mm in client.iter_messages(entity, limit=20, min_id=self.min_id[ch]):
                            if not mm.message:
                                continue
                            msgs.append((mm.id, int(mm.date.timestamp()), mm.message))
                        for mid, ts, text in sorted(msgs):
                            handle_message(ch, text, ts)
                        if msgs:
                            self.min_id[ch] = max(self.min_id[ch], max(m[0] for m in msgs))
                        STATE.sources[ch] = {"ok": True, "err": "", "time": int(time.time())}
                    except Exception as e:
                        STATE.sources[ch] = {"ok": False, "err": str(e)[:120], "time": int(time.time())}
                STATE.tracks.prune()
                with STATE.lock:
                    STATE.updated = int(time.time())
                    STATE.feed = STATE.feed[-40:]
                await asyncio.sleep(POLL_CHANNELS)

        try:
            asyncio.run(main())
        except Exception as e:
            print("Telethon: %s" % e, file=sys.stderr)
            with STATE.lock:
                STATE.sources["telegram"] = {"ok": False, "err": str(e)[:120], "time": int(time.time())}


def tg_fetch(channel):
    url = "https://t.me/s/%s" % channel
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "replace")
    msgs = []
    for m in re.finditer(r'data-post="[^"]*?(\d+)".*?class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                         html, re.S):
        mid = m.group(1)
        text = re.sub(r"<[^>]+>", "", m.group(2))
        text = (text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&nbsp;", " ")).strip()
        if not text:
            continue
        tm = re.search(r'datetime="([^"]+)"', html[max(0, m.start() - 2000):m.start()])
        ts = int(time.time())
        if tm:
            try:
                import calendar
                ts = calendar.timegm(time.strptime(tm.group(1)[:16], "%Y-%m-%dT%H:%M"))
            except Exception:
                pass
        msgs.append({"id": mid, "time": ts, "text": text})
    return msgs


def poll_channels_fallback():
    seen = {}
    while True:
        for ch in DEFAULT_CHANNELS:
            try:
                for msg in tg_fetch(ch):
                    handle_message(ch, msg["text"], msg["time"])
                STATE.tracks.prune()
                STATE.sources[ch] = {"ok": True, "err": "", "time": int(time.time())}
            except Exception as e:
                print("poll %s: %s" % (ch, e), file=sys.stderr)
                STATE.sources[ch] = {"ok": False, "err": str(e)[:120], "time": int(time.time())}
        with STATE.lock:
            STATE.updated = int(time.time())
            STATE.feed = STATE.feed[-40:]
        time.sleep(POLL_CHANNELS)


def handle_message(channel, text, ts):
    parsed = parse_message(text, channel, ts)
    if not parsed:
        return
    with STATE.lock:
        STATE.feed.append({"channel": channel, "time": ts, "kind": parsed["kind"], "text": text})
        if "alert_on" in parsed:
            STATE.alert_state = "on" if parsed["alert_on"] else STATE.alert_state
        elif parsed["status"] == "all_clear" and parsed["kind"] != "alert_echo":
            STATE.alert_state = "off"
        if parsed["kind"] == "target":
            prev = STATE.tracks.tracks[-1]["status"] if STATE.tracks.tracks else ""
            STATE.tracks.apply(parsed)
            cur = STATE.tracks.tracks[-1]["status"] if STATE.tracks.tracks else ""
            if cur != prev and cur in ("approach", "overhead"):
                notify(cur)


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
                if "ніпропетр" in key.lower():
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
            self._send(200, self._static("index.html"), "text/html; charset=utf-8")
            return
        for fname in ("dnipro-geo.js", "rivers.js"):
            if path == "/" + fname:
                self._send(200, self._static(fname), "application/javascript; charset=utf-8")
                return
        self._send(404, b"not found", "text/plain")

    @staticmethod
    def _static(fname):
        with open(os.path.join(STATIC, fname), "rb") as f:
            return f.read()


def write_config_if_missing():
    cfg = os.path.join(BASE, "config.json")
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({
                "api_id": 0,
                "api_hash": "ВСТАВЬ_СЮДА_СВОЙ_API_HASH",
                "phone": "+380XXXXXXXXX",
                "channels": DEFAULT_CHANNELS
            }, f, ensure_ascii=False, indent=2)
        return False
    return True


def main():
    if not write_config_if_missing():
        print("\nСоздал config.json — впиши туда api_id и api_hash (получить: https://my.telegram.org),")
        print("затем запусти снова: python server.py\n")
        sys.exit(0)
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    channels = cfg.get("channels") or DEFAULT_CHANNELS
    api_id = int(cfg.get("api_id") or 0)
    api_hash = cfg.get("api_hash") or ""

    try:
        import telethon  # noqa
        telethon_ok = True
    except ImportError:
        telethon_ok = False

    if api_id > 0 and api_hash and "ВСТАВЬ" not in api_hash:
        if telethon_ok:
            print("Режим: Telegram API (Telethon)")
            TelethonPoller(api_id, api_hash, cfg.get("phone", ""), channels).start()
        else:
            print("Telethon не установлен (pip install telethon) — включён фолбэк web-скрейпа")
            threading.Thread(target=poll_channels_fallback, daemon=True).start()
    else:
        print("config.json без api_id/api_hash — включён фолбэк web-скрейпа t.me")
        threading.Thread(target=poll_channels_fallback, daemon=True).start()

    threading.Thread(target=poll_alert, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Карта загроз: http://%s:%d" % (HOST, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
