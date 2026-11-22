package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Lexicon {

    public final Map<String, List<String>> statuses = new LinkedHashMap<>();
    public final Map<String, List<String>> types = new LinkedHashMap<>();
    public final Map<String, List<String>> directions = new LinkedHashMap<>();
    public final List<String> noiseMarkers = new ArrayList<>();
    public final List<String> sameTargetMarkers = new ArrayList<>();
    public final List<String> newTargetMarkers = new ArrayList<>();

    public void addStatus(String key, List<String> roots) {
        statuses.put(key, new ArrayList<>(roots));
    }

    public void addType(String key, List<String> roots) {
        types.put(key, new ArrayList<>(roots));
    }

    public void addDirection(String key, List<String> roots) {
        directions.put(key, new ArrayList<>(roots));
    }

    public List<String> statusKeys() {
        List<String> keys = new ArrayList<>(statuses.keySet());
        Collections.reverse(keys);
        return keys;
    }
}
