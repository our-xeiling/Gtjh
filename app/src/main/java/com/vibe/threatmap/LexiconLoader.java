package com.vibe.threatmap;

import com.vibe.threatmap.core.GeoPlace;
import com.vibe.threatmap.core.Lexicon;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.util.ArrayList;

final class LexiconLoader {

    private LexiconLoader() {
    }

    static Lexicon loadLexicon(InputStream in) throws Exception {
        byte[] buf = new byte[8192];
        StringBuilder sb = new StringBuilder();
        int n;
        while ((n = in.read(buf)) > 0) {
            sb.append(new String(buf, 0, n, "UTF-8"));
        }
        in.close();
        JSONObject root = new JSONObject(sb.toString());

        Lexicon lexicon = new Lexicon();
        JSONObject statuses = root.getJSONObject("статуси");
        for (String key : keyList(statuses)) {
            lexicon.addStatus(key, stringList(statuses.getJSONArray(key)));
        }
        JSONObject types = root.getJSONObject("типи");
        for (String key : keyList(types)) {
            lexicon.addType(key, stringList(types.getJSONArray(key)));
        }
        JSONObject directions = root.getJSONObject("напрямки");
        for (String key : keyList(directions)) {
            lexicon.addDirection(key, stringList(directions.getJSONArray(key)));
        }
        lexicon.noiseMarkers.addAll(stringList(root.getJSONArray("шум")));
        lexicon.sameTargetMarkers.addAll(stringList(root.getJSONArray("той_самий")));
        lexicon.newTargetMarkers.addAll(stringList(root.getJSONArray("нова_ціль")));
        return lexicon;
    }

    static ArrayList<GeoPlace> loadPlaces(InputStream in) throws Exception {
        byte[] buf = new byte[8192];
        StringBuilder sb = new StringBuilder();
        int n;
        while ((n = in.read(buf)) > 0) {
            sb.append(new String(buf, 0, n, "UTF-8"));
        }
        in.close();
        JSONArray arr = new JSONArray(sb.toString());
        ArrayList<GeoPlace> places = new ArrayList<>();
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.getJSONObject(i);
            places.add(new GeoPlace(
                    o.getString("name"),
                    o.getDouble("lat"),
                    o.getDouble("lon"),
                    stringList(o.optJSONArray("aliases"))
            ));
        }
        return places;
    }

    private static ArrayList<String> keyList(JSONObject o) {
        ArrayList<String> keys = new ArrayList<>();
        java.util.Iterator<String> it = o.keys();
        while (it.hasNext()) {
            keys.add(it.next());
        }
        return keys;
    }

    private static ArrayList<String> stringList(JSONArray arr) {
        ArrayList<String> out = new ArrayList<>();
        if (arr == null) {
            return out;
        }
        for (int i = 0; i < arr.length(); i++) {
            out.add(arr.getString(i));
        }
        return out;
    }
}
