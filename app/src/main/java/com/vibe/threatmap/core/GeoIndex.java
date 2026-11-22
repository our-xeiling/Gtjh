package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class GeoIndex {

    private static final Set<String> STOP_WORDS = new HashSet<>(Arrays.asList(
            "с", "сел", "село", "села", "смт", "м", "місто", "міста", "р", "н", "р-н", "напрям",
            "ку", "до", "на", "біля", "от", "из", "в", "з", "зі", "и", "і", "та", "через"
    ));

    private final List<GeoPlace> places = new ArrayList<>();

    public GeoIndex() {
    }

    public void add(GeoPlace place) {
        places.add(place);
    }

    public GeoPlace match(String normalizedText) {
        List<GeoPlace> all = matchAll(normalizedText);
        return all.isEmpty() ? null : all.get(all.size() - 1);
    }

    public List<GeoPlace> matchAll(String normalizedText) {
        List<GeoPlace> found = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        List<String> tokens = tokenize(normalizedText);
        int j = 0;
        while (j < tokens.size()) {
            GeoPlace hit = null;
            int used = 0;
            for (int k = Math.min(tokens.size(), j + 3); k > j; k--) {
                StringBuilder sb = new StringBuilder();
                for (int m = j; m < k; m++) {
                    if (m > j) {
                        sb.append(' ');
                    }
                    sb.append(tokens.get(m));
                }
                String gram = sb.toString();
                if (gram.length() < 3) {
                    continue;
                }
                GeoPlace place = lookup(gram);
                if (place != null) {
                    hit = place;
                    used = k - j;
                    break;
                }
            }
            if (hit != null) {
                if (seen.add(hit.name)) {
                    found.add(hit);
                }
                j += used;
            } else {
                j++;
            }
        }
        return found;
    }

    private GeoPlace lookup(String gram) {
        for (GeoPlace place : places) {
            for (String aliasDirty : place.aliases) {
                String alias = normalize(aliasDirty);
                if (alias.isEmpty()) {
                    continue;
                }
                if (alias.equals(gram)) {
                    return place;
                }
                if (alias.length() >= 5 && gram.length() >= 5) {
                    if (Fuzzy.close(alias, gram, 1)) {
                        return place;
                    }
                    if (gram.startsWith(alias) || alias.startsWith(gram)) {
                        return place;
                    }
                }
            }
        }
        return null;
    }

    private List<String> tokenize(String text) {
        List<String> tokens = new ArrayList<>();
        for (String raw : text.toLowerCase(new Locale("uk")).split("[^0-9\\p{L}\\-]+")) {
            if (raw.isEmpty() || STOP_WORDS.contains(raw)) {
                continue;
            }
            tokens.add(raw);
        }
        return tokens;
    }

    private String normalize(String s) {
        return s.toLowerCase(new Locale("uk"))
                .replace("ё", "е")
                .replace("ы", "и")
                .replace("'", "")
                .replace("’", "")
                .trim();
    }
}
