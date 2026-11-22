package com.vibe.threatmap;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;

public class AlertPoller {

    public static final String OBLAST_KEY_HINT = "ніпропетр";

    public boolean dniproAlert() throws Exception {
        String body = httpGet("https://ubilling.net.ua/aerialalerts/");
        JSONObject root = new JSONObject(body);
        JSONObject states = root.getJSONObject("states");
        Iterator<String> keys = states.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            String lower = key.toLowerCase();
            if (lower.contains(OBLAST_KEY_HINT) || lower.contains("днепропетр")) {
                return states.getJSONObject(key).getBoolean("alertnow");
            }
        }
        throw new Exception("oblast not found in alert feed");
    }

    private static String httpGet(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13)");
        c.setConnectTimeout(10000);
        c.setReadTimeout(15000);
        try {
            int code = c.getResponseCode();
            if (code != 200) {
                throw new Exception("HTTP " + code + " for " + url);
            }
            BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[8192];
            int n;
            while ((n = r.read(buf)) > 0) {
                sb.append(buf, 0, n);
            }
            r.close();
            return sb.toString();
        } finally {
            c.disconnect();
        }
    }
}
