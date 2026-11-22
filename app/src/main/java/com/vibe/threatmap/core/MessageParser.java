package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MessageParser {

    private static final String[] STATUS_PRIORITY = {
            "overhead", "approach", "all_clear", "loiter", "lost", "redetected",
            "left", "transit", "no_threat", "tracked", "detected"
    };

    private static final Pattern COUNT_X = Pattern.compile("([0-9])\\s*х(\\b|$)");
    private static final Pattern COUNT_PLUS = Pattern.compile("\\+\\s*([0-9])");
    private static final Pattern ALTITUDE = Pattern.compile("(висот|высот)[^0-9]{0,24}([0-9]{2,5})");

    private static final String[][] LATIN_TO_CYR = {
            {"a", "а"}, {"e", "е"}, {"o", "о"}, {"c", "с"}, {"p", "р"},
            {"x", "х"}, {"y", "у"}, {"i", "і"}
    };

    private final Lexicon lexicon;
    private final GeoIndex geo;

    public MessageParser(Lexicon lexicon, GeoIndex geo) {
        this.lexicon = lexicon;
        this.geo = geo;
    }

    public ParsedReport parse(String channel, String rawText, long epochSec) {
        ParsedReport r = new ParsedReport();
        r.channel = channel;
        r.raw = rawText == null ? "" : rawText.trim();
        r.time = epochSec;

        String lower = r.raw.toLowerCase(new Locale("uk"));
        if (isNoise(lower)) {
            r.kind = ParsedReport.KIND_NOISE;
            return r;
        }
        if (isAlertEcho(lower)) {
            r.kind = ParsedReport.KIND_ALERT_ECHO;
            r.alertOn = !(lower.contains("відбій") || lower.contains("отбой")
                    || lower.contains("🟢") || lower.contains("зелен"));
            return r;
        }

        String norm = normalize(r.raw);
        List<String> tokens = tokenize(norm);

        r.type = matchGroup(lexicon.types, tokens);
        r.status = matchStatus(tokens, norm);
        r.direction = matchGroup(lexicon.directions, tokens);
        r.altitudeM = parseAltitude(norm);
        r.count = parseCount(norm, r.raw.toLowerCase(new Locale("uk")));
        if (norm.contains("+1") || r.raw.contains("+") || containsAny(norm, lexicon.newTargetMarkers)) {
            r.newHint = true;
        }
        if (containsAny(norm, lexicon.sameTargetMarkers) || lower.contains("турист")
                || lower.contains("той сам") || lower.contains("того же") || lower.contains("того ж")
                || lower.contains("этот") || lower.contains("цей")) {
            r.sameHint = true;
        }

        for (GeoPlace place : geo.matchAll(norm)) {
            r.placeNames.add(place.name);
            r.placeCoords.add(new double[]{place.lat, place.lon});
        }

        if (r.status == null && r.type == null && r.direction == null
                && r.altitudeM == null && r.count == null && r.placeNames.isEmpty()) {
            r.kind = ParsedReport.KIND_NOISE;
            return r;
        }
        if (r.status == null && !r.placeNames.isEmpty()) {
            r.status = "detected";
        }
        r.kind = ParsedReport.KIND_TARGET;
        return r;
    }

    private boolean isNoise(String lower) {
        Matcher m = Pattern.compile("[0-9]{12,}").matcher(lower);
        if (m.find()) {
            return true;
        }
        return containsAny(lower, lexicon.noiseMarkers);
    }

    private boolean isAlertEcho(String lower) {
        return (lower.contains("тривог") || lower.contains("тревог"))
                && (lower.contains("🔴") || lower.contains("🟢")
                || lower.contains("червон") || lower.contains("зелен")
                || lower.contains("відбій") || lower.contains("отбой"));
    }

    private String matchStatus(List<String> tokens, String norm) {
        Map<String, List<String>> statuses = lexicon.statuses;
        for (String key : STATUS_PRIORITY) {
            List<String> roots = statuses.get(key);
            if (roots == null) {
                continue;
            }
            if (matchRoots(roots, tokens) || rootPhrase(norm, roots)) {
                return key;
            }
        }
        return null;
    }

    private boolean rootPhrase(String norm, List<String> roots) {
        for (String root : roots) {
            if (root.contains(" ") && norm.contains(root)) {
                return true;
            }
        }
        return false;
    }

    private String matchGroup(Map<String, List<String>> groups, List<String> tokens) {
        for (Map.Entry<String, List<String>> entry : groups.entrySet()) {
            if (matchRoots(entry.getValue(), tokens)) {
                return entry.getKey();
            }
        }
        return null;
    }

    private boolean matchRoots(List<String> roots, List<String> tokens) {
        for (String token : tokens) {
            for (String root : roots) {
                String nRoot = normalize(root);
                if (nRoot.length() < 3) {
                    continue;
                }
                if (token.startsWith(nRoot)) {
                    return true;
                }
                if (nRoot.length() >= 5 && token.length() >= 4 && Fuzzy.close(token, nRoot, 1)) {
                    return true;
                }
            }
        }
        return false;
    }

    private Integer parseCount(String norm, String rawLower) {
        Matcher m = COUNT_PLUS.matcher(rawLower);
        if (m.find()) {
            return Integer.parseInt(m.group(1));
        }
        m = COUNT_X.matcher(norm);
        if (m.find()) {
            return Integer.parseInt(m.group(1));
        }
        if (norm.contains(" пара ")) {
            return 2;
        }
        return null;
    }

    private Integer parseAltitude(String norm) {
        Matcher m = ALTITUDE.matcher(norm);
        if (m.find()) {
            try {
                return Integer.parseInt(m.group(2));
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private boolean containsAny(String text, List<String> markers) {
        if (markers == null) {
            return false;
        }
        for (String marker : markers) {
            if (!marker.isEmpty() && text.contains(normalize(marker))) {
                return true;
            }
        }
        return false;
    }

    static String normalize(String text) {
        StringBuilder out = new StringBuilder();
        for (String token : text.split("[^0-9a-zA-Zа-яА-ЯіїєґІЇЄҐ\\-]+")) {
            if (token.isEmpty()) {
                continue;
            }
            String t = token.toLowerCase(new Locale("uk"))
                    .replace("ё", "е")
                    .replace("ы", "и")
                    .replace("ъ", "")
                    .replace("'", "")
                    .replace("’", "");
            boolean hasCyr = false;
            for (char ch : t.toCharArray()) {
                if (ch >= 'а' && ch <= 'я' || ch == 'і' || ch == 'ї' || ch == 'є' || ch == 'ґ') {
                    hasCyr = true;
                    break;
                }
            }
            if (hasCyr) {
                for (String[] pair : LATIN_TO_CYR) {
                    t = t.replace(pair[0], pair[1]);
                }
            }
            out.append(t).append(' ');
        }
        return out.toString();
    }

    static List<String> tokenize(String normalized) {
        List<String> tokens = new ArrayList<>();
        for (String token : normalized.trim().split(" +")) {
            if (!token.isEmpty()) {
                tokens.add(token);
            }
        }
        return tokens;
    }
}
