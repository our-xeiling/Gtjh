/* Браузерный конвейер: опитування t.me та офіційної тривоги напряму
   (через ланцюжок CORS-проксі), парсинг як в Java/Python, зборка треків.
   Працює з file:// — тому без fetch/XHR до локальних файлів. */
(function () {
  var CHANNELS = ["dnepr_nagladach", "eyes_everywhere_dnipro", "PmSDnepra", "TesterbotTrevoga"];
  var CHANNEL_EVERY_MS = 30000;
  var ALERT_EVERY_MS = 60000;
  var PROXIES = [
    null,
    "https://api.allorigins.win/raw?url=",
    "https://corsproxy.io/?url="
  ];
  var ALERT_URL = "https://ubilling.net.ua/aerialalerts/";

  var STATUS_KEYS = ["overhead", "approach", "all_clear", "loiter", "lost", "redetected",
    "left", "transit", "no_threat", "tracked", "detected"];
  var SAFE = { no_threat: 1, left: 1, all_clear: 1 };
  var ACTIVE = { detected: 1, tracked: 1, transit: 1, approach: 1, overhead: 1, loiter: 1, unknown: 1, redetected: 1 };
  var NORM_MAP = { "ё": "е", "ы": "и", "й": "і", "ъ": "", "'": "", "’": "", "`": "" };
  var TO_CYR = { a: "а", e: "е", o: "о", c: "с", p: "р", x: "х", y: "у", i: "і" };

  var st = {
    tracks: [],
    feed: [],
    alertState: null,
    alertUpdated: 0,
    updated: Math.floor(Date.now() / 1000),
    sources: {},
    seq: 0,
    lastId: {},
    started: false
  };

  function norm(text) {
    var t = String(text || "").toLowerCase();
    t = t.replace(/[ёыйъ'’`]/g, function (c) { return NORM_MAP[c] !== undefined ? NORM_MAP[c] : c; });
    if (/[а-яіїєґ]/.test(t)) {
      t = t.replace(/[aeoxcpybi]/g, function (c) { return TO_CYR[c] || c; });
    }
    return t;
  }

  function rootHits(n, roots) {
    if (!roots || !roots.length) return false;
    var words = n.split(/\s+/);
    for (var i = 0; i < roots.length; i++) {
      var r = norm(roots[i]);
      if (!r) continue;
      if (r.indexOf(" ") >= 0) { if (n.indexOf(r) >= 0) return true; }
      else {
        if (n.indexOf(r) === 0) return true;
        for (var w = 0; w < words.length; w++) {
          if (words[w].indexOf(r) === 0) return true;
        }
      }
    }
    return false;
  }

  function statusOf(n) {
    for (var i = 0; i < STATUS_KEYS.length; i++) {
      if (rootHits(n, st.dict["статуси"][STATUS_KEYS[i]])) return STATUS_KEYS[i];
    }
    return "unknown";
  }
  function firstOf(n, obj) {
    for (var id in obj) {
      if (rootHits(n, obj[id])) return id;
    }
    return null;
  }
  function isNoise(raw, n) {
    if (/\d{12,}/.test(raw)) return true;
    var marks = st.dict["шум"] || [];
    for (var i = 0; i < marks.length; i++) {
      if (n.indexOf(norm(marks[i])) >= 0) return true;
    }
    return false;
  }

  var geoIdx = null;
  function buildGeo() {
    geoIdx = [];
    st.places.forEach(function (p) {
      ([p.name].concat(p.aliases || [])).forEach(function (a) {
        if (a) geoIdx.push([norm(a), p]);
      });
    });
    geoIdx.sort(function (x, y) { return y[0].length - x[0].length; });
  }
  function geoMatch(n) {
    if (!geoIdx) buildGeo();
    var used = [];
    for (var i = 0; i < n.length; i++) used.push(false);
    var found = [];
    geoIdx.forEach(function (entry) {
      var alias = entry[0], place = entry[1];
      var pos = n.indexOf(alias);
      while (pos >= 0) {
        var busy = false;
        for (var k = pos; k < pos + alias.length; k++) { if (used[k]) { busy = true; break; } }
        if (!busy) {
          for (var j = pos; j < pos + alias.length; j++) used[j] = true;
          found.push({ pos: pos, place: place });
          break;
        }
        pos = n.indexOf(alias, pos + 1);
      }
    });
    found.sort(function (x, y) { return x.pos - y.pos; });
    var names = [], seen = {};
    found.forEach(function (f) {
      if (!seen[f.place.name]) { seen[f.place.name] = 1; names.push(f.place); }
    });
    return names;
  }

  function parseMessage(raw, channel, ts) {
    var n = norm(raw);
    if (isNoise(raw, n)) return null;
    var echo = null;
    var low = raw.toLowerCase();
    if (low.indexOf("тривог") >= 0 || low.indexOf("тревог") >= 0 || low.indexOf("трiвог") >= 0) {
      var off = n.indexOf("відбій") >= 0 || n.indexOf("отбой") >= 0 || raw.indexOf("🟢") >= 0 || n.indexOf("зелен") >= 0;
      echo = !off;
    }
    if (echo !== null) {
      return { kind: "alert_echo", channel: channel, raw: raw, time: ts, alertOn: echo };
    }
    var places = geoMatch(n);
    var m = raw.match(/\+\s?(\d)|(\d)х/);
    var ma = n.match(/(висот|высот)[^0-9]{0,24}([0-9]{2,5})/);
    var alt = ma ? parseInt(ma[2], 10) : null;
    return {
      kind: places.length ? "target" : "feed",
      channel: channel, raw: raw, time: ts,
      type: firstOf(n, st.dict["типи"]) || "ціль",
      status: statusOf(n),
      direction: firstOf(n, st.dict["напрямки"]),
      places: places.map(function (p) { return p.name; }),
      coords: places.map(function (p) { return [p.lat, p.lon]; }),
      count: m ? parseInt(m[1] || m[2], 10) : (n.indexOf("пара") >= 0 ? 2 : null),
      altitude: alt,
      newHint: /\+\s?\d/.test(raw) || rootHits(n, st.dict["нова_ціль"]),
      sameHint: rootHits(n, st.dict["той_самий"])
    };
  }

  function lastActive() {
    var found = null;
    st.tracks.forEach(function (t) {
      if (ACTIVE[t.status] || t.status === "lost") found = t;
    });
    return found;
  }

  function apply(p) {
    st.updated = Math.floor(Date.now() / 1000);
    st.feed.push({ channel: p.channel, text: p.raw, time: p.time, kind: p.kind === "target" && !(p.places || []).length ? "feed" : p.kind });
    if (st.feed.length > 60) st.feed.shift();
    if (p.kind === "noise") return;
    if (p.kind === "alert_echo") {
      st.alertState = p.alertOn ? "on" : "off";
      st.alertUpdated = p.time;
      return;
    }
    if (p.status === "all_clear") {
      st.tracks.forEach(function (t) {
        if (t.channel === p.channel && t.status !== "left") { t.status = "left"; t.lastUpdate = p.time; }
      });
      return;
    }
    if (!(p.places || []).length && !p.newHint && !p.sameHint) return;
    var target = null;
    if (p.sameHint) {
      target = lastActive() || st.tracks[st.tracks.length - 1] || null;
    } else if (p.newHint || !st.tracks.length) {
      target = null;
    } else {
      target = lastActive();
    }
    if (!target && !(p.places || []).length) return;
    if (!target) {
      target = {
        id: "t" + (++st.seq), channel: p.channel, type: "ціль", status: "unknown",
        count: null, altitude_m: null, heading: null, pattern: false,
        last_text: "", last_update: 0, locations: []
      };
      st.tracks.push(target);
    }
    if (p.status) target.status = p.status;
    if (p.type && p.type !== "ціль") target.type = p.type;
    if (p.count && (!target.count || p.count > target.count)) target.count = p.count;
    if (p.altitude) target.altitude_m = p.altitude;
    if (p.direction) target.heading = p.direction;
    if (p.status === "loiter") target.pattern = true;
    target.last_text = p.raw;
    target.last_update = p.time;
    if ((p.places || []).length && !SAFE[target.status]) {
      p.places.forEach(function (name, i) {
        var lastLoc = target.locations[target.locations.length - 1];
        if (!lastLoc || lastLoc.name !== name) {
          target.locations.push({ name: name, lat: p.coords[i][0], lon: p.coords[i][1], t: p.time });
        }
      });
      if (target.locations.length > 12) target.locations = target.locations.slice(-12);
    }
  }

  function prune() {
    var now = Date.now() / 1000;
    st.tracks = st.tracks.filter(function (t) {
      var age = now - (t.last_update || 0);
      return age < (SAFE[t.status] ? 2700 : 8100);
    });
    st.feed = st.feed.filter(function (f) { return now - f.time < 7200; });
  }

  /* ---------- HTTP: прямий запит -> CORS-проксі ---------- */
  async function fetchText(url) {
    var err = null;
    for (var i = 0; i < PROXIES.length; i++) {
      var link = PROXIES[i] ? PROXIES[i] + encodeURIComponent(url) : url;
      try {
        var r = await fetch(link, { cache: "no-store" });
        if (r.ok) return await r.text();
        err = new Error("HTTP " + r.status);
      } catch (e) { err = e; }
    }
    throw err || new Error("недоступно");
  }

  function elText(el) {
    var s = "";
    el.childNodes.forEach(function (n) {
      if (n.nodeType === 3) s += n.nodeValue;
      else if (n.tagName === "BR") s += "\n";
      else s += elText(n);
    });
    return s;
  }

  function parseChannel(html, channel) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var out = [];
    doc.querySelectorAll("time[data-post]").forEach(function (t) {
      var msgEl = t.closest(".tgme_widget_message");
      var textEl = msgEl && msgEl.querySelector(".tgme_widget_message_text");
      if (!textEl) return;
      var txt = elText(textEl).trim();
      if (!txt) return;
      var id = parseInt(String(t.getAttribute("data-post")).split("/").pop(), 10);
      var d = Date.parse(t.getAttribute("datetime") || "") / 1000;
      out.push({ id: id, time: Math.round(d || Date.now() / 1000), text: txt });
    });
    var byId = {};
    out.forEach(function (m) {
      var prev = byId[m.id];
      if (!prev || prev.text.length < m.text.length) byId[m.id] = m;
    });
    return out.map(function (id) { return byId[id]; })
      .sort(function (a, b) { return a.id - b.id; });
  }

  function markSrc(ch, err) {
    st.sources[ch] = { ok: !err, err: err ? String(err.message || err) : "", time: Math.floor(Date.now() / 1000) };
  }

  async function pollChannels() {
    for (var i = 0; i < CHANNELS.length; i++) {
      var ch = CHANNELS[i];
      try {
        var msgs = parseChannel(await fetchText("https://t.me/s/" + ch), ch);
        msgs.forEach(function (m) {
          if (st.lastId[ch] && m.id <= st.lastId[ch]) return;
          var p = parseMessage(m.text, ch, m.time);
          if (p) apply(p);
        });
        if (msgs.length) st.lastId[ch] = msgs[msgs.length - 1].id;
        markSrc(ch, null);
      } catch (e) {
        markSrc(ch, e);
      }
    }
    prune();
    st.updated = Math.floor(Date.now() / 1000);
  }

  async function pollAlert() {
    try {
      var data = JSON.parse(await fetchText(ALERT_URL));
      var states = data.states || {};
      var on = null;
      for (var key in states) {
        if (key.toLowerCase().indexOf("ніпропетр") >= 0 || key.toLowerCase().indexOf("нiпропетр") >= 0) {
          on = states[key].alertnow;
          break;
        }
      }
      if (on === true || on === false) {
        st.alertState = on ? "on" : "off";
        st.alertUpdated = Math.floor(Date.now() / 1000);
      }
      st.sources["тривога"] = { ok: true, err: "", time: Math.floor(Date.now() / 1000) };
    } catch (e) {
      st.sources["тривога"] = { ok: false, err: String(e.message || e), time: Math.floor(Date.now() / 1000) };
    }
  }

  function snapshot() {
    return {
      updated: st.updated,
      alerts: { state: st.alertState, updated: st.alertUpdated },
      tracks: st.tracks,
      feed: st.feed,
      sources: Object.keys(st.sources).map(function (k) {
        var s = st.sources[k];
        return { name: k, ok: s.ok, err: s.err, time: s.time };
      })
    };
  }

  window.__pipelineState = snapshot;
  window.__pipelineStart = function () {
    if (st.started || !window.DICT) return;
    st.started = true;
    st.dict = window.DICT;
    st.places = window.PLACES || [];
    pollAlert();
    pollChannels();
    setInterval(pollAlert, ALERT_EVERY_MS);
    setInterval(pollChannels, CHANNEL_EVERY_MS);
  };
})();
