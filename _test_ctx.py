# -*- coding: utf-8 -*-
import importlib.util
import json
import sys
import time

spec = importlib.util.spec_from_file_location("srv", "server.py")
srv = importlib.util.module_from_spec(spec)
sys.modules["srv"] = srv
spec.loader.exec_module(srv)

OK = {"ok": True}


def check(cond, label):
    OK["ok"] = OK["ok"] and cond
    print(("OK  " if cond else "FAIL"), label)


now = time.time()
SEQ_A = [
    ("dnepr_nagladach", "Реактив на Кривий Ріг зі сходу", 100, None),
    ("dnepr_nagladach", "Покров наближення", 101, 100),
    ("dnepr_nagladach", "Без фіксації", 102, 101),
    ("dnepr_nagladach", "Вылез", 103, 102),
]
for ch, text, mid, rto in SEQ_A:
    srv.handle_message(ch, text, now, msg_id=mid, reply_to=rto)
with srv.STATE.lock:
    tracks = json.loads(json.dumps(srv.STATE.tracks.snapshot_tracks()))
    feed0 = len(srv.STATE.feed)
t1 = [t for t in tracks if t["id"] == "t1"]
check(bool(t1) and t1[0]["status"] == "redetected",
      "reply chain: идёт->покров->без фіксації->вилез = one track, redetected")
kr_loc = t1[0]["locations"][0] if t1 else None
check(abs(kr_loc["lon"] - 33.3918) > 0.1, "KR jet offset east of city, not on city")
check(t1[0]["heading"] == "E", "heading E captured")

srv.handle_message("PmSDnepra", "+1 рбпла на севере транзит", now, msg_id=200)
srv.handle_message("PmSDnepra", "Идет на Никополь р-н", now, msg_id=201, reply_to=200)
srv.handle_message("dnepr_nagladach", "Днепр пока курим, без угроз", now, msg_id=104)
srv.handle_message("dnepr_nagladach", "От ПТХ на Соленое пропал", now, msg_id=105)

with srv.STATE.lock:
    tracks = json.loads(json.dumps(srv.STATE.tracks.snapshot_tracks()))
    feed = len(srv.STATE.feed)
print("feed entries:", feed)
for t in tracks:
    print(t["id"], t["channel"], t["type"], t["status"], t["heading"],
          [(l["name"], round(l["lat"], 3), round(l["lon"], 3)) for l in t["locations"]],
          t.get("marker"), t.get("color"))

t_nik = [t for t in tracks if any(l["name"] == "Нікополь" for l in t["locations"])]
check(bool(t_nik) and (abs(t_nik[0]["locations"][0]["lat"] - 47.5716) > 0.05 or
                       abs(t_nik[0]["locations"][0]["lon"] - 34.4003) > 0.05),
      "Nikopol tracked -> offset, not on city")
t_dn = [t for t in tracks if any(l["name"] == "Дніпро" for l in t["locations"])]
check(bool(t_dn) and t_dn[0]["status"] == "no_threat" and t_dn[0]["color"] == "yellow",
      "Dnipro no_threat yellow")
t_lost = [t for t in tracks if t["status"] == "lost"]
check(any("Солоне" in [l["name"] for l in t["locations"]] for t in t_lost),
      "lost track exists (ПТХ->Солоне)")

for ch, text, mid, rto in SEQ_A:
    srv.handle_message(ch, text, now + 5, msg_id=mid, reply_to=rto)
with srv.STATE.lock:
    check(len(srv.STATE.feed) == feed, "dedupe: no duplicate feed entries on re-poll")

print("\nALL OK" if OK["ok"] else "\nFAILURES PRESENT")
sys.exit(0 if OK["ok"] else 1)
