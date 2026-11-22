package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.List;

public class ParsedReport {

    public static final String KIND_TARGET = "target";
    public static final String KIND_ALERT_ECHO = "alert_echo";
    public static final String KIND_NOISE = "noise";

    public String kind;
    public String channel;
    public String raw;
    public long time;

    public String type;
    public String status;
    public String direction;
    public Integer count;
    public Integer altitudeM;
    public final List<String> placeNames = new ArrayList<>();
    public final List<double[]> placeCoords = new ArrayList<>();

    public String lastPlaceName() {
        return placeNames.isEmpty() ? null : placeNames.get(placeNames.size() - 1);
    }

    public boolean newHint;
    public boolean sameHint;
    public boolean alertOn;
}
