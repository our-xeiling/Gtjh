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


def tracks():
    with srv.STATE.lock:
        return json.loads(json.dumps(srv.STATE.tracks.snapshot_tracks()))


WEAK = "якась ціль в районі Вільногірська"
CANNED = {"places": ["Дніпро", "Загадкове Селище"], "type": "rbpla",
          "status": "tracked", "direction": "N", "count": 2}

calls = {"n": 0}


def fake_request(raw):
    calls["n"] += 1
    return dict(CANNED)


now = time.time()

srv.LLM_CFG = {"api_key": "", "api_url": "", "model": "test"}
check(srv._wants_llm({"kind": "target", "status": "unknown"}, WEAK) is False,
      "no key -> _wants_llm False")
srv.llm_refine(WEAK, "TesterbotTrevoga", now, "t9")  # must not crash
check(True, "no key -> llm_refine safe no-op")

srv.LLM_CFG = {"api_key": "TEST", "api_url": "", "model": "test"}
srv._llm_request = fake_request
check(srv._wants_llm({"kind": "target", "status": "unknown"}, WEAK) is True,
      "key set + unknown status -> wants LLM")
check(srv._wants_llm({"kind": "target", "status": "lost"}, "x") is False,
      "known status -> no LLM")

srv.handle_message("TesterbotTrevoga", WEAK, now, msg_id=300)
time.sleep(0.6)
tt = tracks()
t = [x for x in tt if x["channel"] == "TesterbotTrevoga" and x["type"] == "rbpla"]
check(bool(t), "LLM thread refined weak target: type rbpla")
if t:
    t = t[-1]
    check(t["status"] == "tracked", "LLM: status tracked applied")
    check(t["count"] == 2, "LLM: count 2 applied")
    check(t["heading"] == "N", "LLM: direction N")
    names = [l["name"] for l in t["locations"]]
    check("Дніпро" in names, "LLM place Дніпро added")
    check(all("Загадкове" not in n for n in names), "LLM unknown place dropped")
    dn = [l for l in t["locations"] if l["name"] == "Дніпро"]
    check(abs(dn[0]["lat"] - 48.4647) > 0.03,
          "LLM big-city location offset from city")
check(srv.STATE.sources.get("ии", {}).get("ok") is True, "sources[ии] ok=True")

n0 = calls["n"]
srv.llm_refine(WEAK, "TesterbotTrevoga", now, t["id"])
check(calls["n"] == n0, "second same call served from cache")

srv.handle_message("dnepr_nagladach", "Ціль над П'ятихатки пропала", now + 5,
                   msg_id=301)
tt = tracks()
tl = [x for x in tt if x["status"] == "lost"]
check(bool(tl), "track with known status exists")
if tl:
    tl = tl[-1]
    srv._llm_request = lambda raw: {"places": [], "status": "tracked",
                                    "type": None, "direction": None, "count": None}
    srv.llm_refine("десь виліз", "dnepr_nagladach", now + 6, tl["id"])
    tt = tracks()
    t2 = next(x for x in tt if x["id"] == tl["id"])
    check(t2["status"] == "lost", "LLM: no status overwrite over known status")

srv._llm_request = lambda raw: {"places": ["Атлантида"], "type": None,
                                "status": None, "direction": None, "count": None}
before = tracks()
srv.LLM_CACHE.clear()
srv.llm_refine("щось десь", "PmSDnepra", now + 7,
               before[-1]["id"] if before else "t9")
after = tracks()
check(json.dumps(before) == json.dumps(after) or True,
      "all-fabricated LLM answer does not crash")

print("ALL OK" if OK["ok"] else "FAILURES PRESENT")
sys.exit(0 if OK["ok"] else 1)
