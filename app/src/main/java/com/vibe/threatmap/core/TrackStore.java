package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class TrackStore {

    private static final long TRACK_TTL_MS = 45L * 60L * 1000L;
    private static final int FEED_LIMIT = 60;

    private static final java.util.Set<String> ACTIVE_STATUSES = new java.util.HashSet<>(java.util.Arrays.asList(
            "detected", "tracked", "transit", "approach", "overhead", "loiter", "unknown"
    ));

    private static final java.util.Set<String> SAFE_STATUSES = new java.util.HashSet<>(java.util.Arrays.asList(
            "no_threat", "left", "all_clear"
    ));

    public static class Track {
        public String id;
        public String channel;
        public String type = "ціль";
        public String status = "unknown";
        public Integer count;
        public Integer altitudeM;
        public String heading;
        public boolean pattern;
        public String lastText = "";
        public long lastUpdate;
        public final List<long[]> locations = new ArrayList<>();
        public final List<String> locationNames = new ArrayList<>();
    }

    private final Map<String, Track> tracks = new LinkedHashMap<>();
    private final List<String[]> feed = new ArrayList<>();
    private String alertState = null;
    private long alertUpdated = 0;
    private long updated = 0;
    private int seq = 0;

    public synchronized void apply(ParsedReport r) {
        updated = System.currentTimeMillis() / 1000L;
        feed.add(new String[]{r.channel, r.raw, String.valueOf(r.time), r.kind});
        if (feed.size() > FEED_LIMIT) {
            feed.remove(0);
        }
        if (ParsedReport.KIND_NOISE.equals(r.kind)) {
            return;
        }
        if (ParsedReport.KIND_ALERT_ECHO.equals(r.kind)) {
            alertState = r.alertOn ? "on" : "off";
            alertUpdated = r.time;
            return;
        }
        if ("all_clear".equals(r.status)) {
            for (Track t : tracks.values()) {
                if (t.channel.equals(r.channel)) {
                    t.status = "left";
                    t.lastUpdate = r.time;
                }
            }
            return;
        }
        List<Track> channelTracks = byChannel(r.channel);
        Track target = pickTarget(channelTracks, r);
        if (target == null) {
            if (r.placeNames.isEmpty() && r.type == null) {
                return;
            }
            target = new Track();
            target.id = "t-" + (++seq);
            target.channel = r.channel;
            target.type = r.type != null ? r.type : "ціль";
            target.status = r.status != null ? r.status : (!r.placeNames.isEmpty() ? "detected" : "unknown");
            target.lastUpdate = r.time;
            tracks.put(target.id, target);
        }
        if (r.status != null) {
            target.status = r.status;
        }
        if (r.type != null) {
            target.type = r.type;
        }
        if (r.count != null && (target.count == null || r.count > target.count)) {
            target.count = r.count;
        }
        if (r.altitudeM != null) {
            target.altitudeM = r.altitudeM;
        }
        if (r.direction != null) {
            target.heading = r.direction;
        }
        if ("loiter".equals(r.status)) {
            target.pattern = true;
        }
        target.lastText = r.raw;
        target.lastUpdate = r.time;
        if (!r.placeNames.isEmpty() && !SAFE_STATUSES.contains(target.status)) {
            for (int i = 0; i < r.placeNames.size(); i++) {
                String name = r.placeNames.get(i);
                if (target.locationNames.isEmpty() || !target.locationNames.get(target.locationNames.size() - 1).equals(name)) {
                    double[] c = r.placeCoords.get(i);
                    target.locationNames.add(name);
                    target.locations.add(new long[]{Math.round(c[0] * 1e6), Math.round(c[1] * 1e6), r.time});
                }
            }
        }
        prune(r.time);
    }

    private List<Track> byChannel(String channel) {
        List<Track> out = new ArrayList<>();
        for (Track t : tracks.values()) {
            if (t.channel.equals(channel)) {
                out.add(t);
            }
        }
        return out;
    }

    private Track pickTarget(List<Track> channelTracks, ParsedReport r) {
        if (r.sameHint) {
            Track active = lastActive(channelTracks);
            if (active != null) {
                return active;
            }
            if (!channelTracks.isEmpty()) {
                return channelTracks.get(channelTracks.size() - 1);
            }
            return null;
        }
        if (r.newHint) {
            return null;
        }
        return lastActive(channelTracks);
    }

    private Track lastActive(List<Track> channelTracks) {
        Track found = null;
        for (Track t : channelTracks) {
            if (ACTIVE_STATUSES.contains(t.status) || "lost".equals(t.status) || "redetected".equals(t.status)) {
                found = t;
            }
        }
        return found;
    }

    private void prune(long nowSec) {
        List<String> dead = new ArrayList<>();
        for (Map.Entry<String, Track> e : tracks.entrySet()) {
            Track t = e.getValue();
            long ageMs = (nowSec - t.lastUpdate) * 1000L;
            boolean stale = SAFE_STATUSES.contains(t.status) ? ageMs > TRACK_TTL_MS : ageMs > TRACK_TTL_MS * 3;
            if (stale) {
                dead.add(e.getKey());
            }
        }
        for (String id : dead) {
            tracks.remove(id);
        }
    }

    public synchronized void setAlert(String state, long epochSec) {
        this.alertState = state;
        this.alertUpdated = epochSec;
    }

    public synchronized String toJson() {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"updated\":").append(updated);
        sb.append(",\"alerts\":{\"state\":");
        sb.append(alertState == null ? "null" : "\"" + alertState + "\"");
        sb.append(",\"updated\":").append(alertUpdated).append('}');
        sb.append(",\"tracks\":[");
        boolean first = true;
        for (Track t : tracks.values()) {
            if (!first) {
                sb.append(',');
            }
            first = false;
            appendTrack(sb, t);
        }
        sb.append("],\"feed\":[");
        for (int i = 0; i < feed.size(); i++) {
            String[] f = feed.get(i);
            if (i > 0) {
                sb.append(',');
            }
            sb.append("{\"channel\":\"").append(JsonKit.escape(f[0]))
                    .append("\",\"text\":\"").append(JsonKit.escape(f[1]))
                    .append("\",\"time\":\"").append(f[2])
                    .append("\",\"kind\":\"").append(f[3]).append("\"}");
        }
        sb.append("]}");
        return sb.toString();
    }

    private void appendTrack(StringBuilder sb, Track t) {
        sb.append("{\"id\":\"").append(JsonKit.escape(t.id))
                .append("\",\"channel\":\"").append(JsonKit.escape(t.channel))
                .append("\",\"type\":\"").append(JsonKit.escape(t.type))
                .append("\",\"status\":\"").append(t.status)
                .append("\",\"count\":").append(t.count == null ? "null" : t.count)
                .append(",\"altitude_m\":").append(t.altitudeM == null ? "null" : t.altitudeM)
                .append(",\"heading\":").append(t.heading == null ? "null" : "\"" + t.heading + "\"")
                .append(",\"pattern\":").append(t.pattern)
                .append(",\"last_text\":\"").append(JsonKit.escape(t.lastText))
                .append("\",\"last_update\":").append(t.lastUpdate)
                .append(",\"locations\":[");
        for (int i = 0; i < t.locations.size(); i++) {
            long[] loc = t.locations.get(i);
            if (i > 0) {
                sb.append(',');
            }
            sb.append("{\"lat\":").append(loc[0] / 1e6)
                    .append(",\"lon\":").append(loc[1] / 1e6)
                    .append(",\"t\":").append(loc[2])
                    .append(",\"name\":\"").append(JsonKit.escape(t.locationNames.get(i))).append("\"}");
        }
        sb.append("]}");
    }
}
