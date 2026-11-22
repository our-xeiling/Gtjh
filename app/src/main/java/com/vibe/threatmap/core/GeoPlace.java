package com.vibe.threatmap.core;

import java.util.ArrayList;
import java.util.List;

public class GeoPlace {

    public final String name;
    public final double lat;
    public final double lon;
    public final List<String> aliases;

    public GeoPlace(String name, double lat, double lon, List<String> aliases) {
        this.name = name;
        this.lat = lat;
        this.lon = lon;
        this.aliases = new ArrayList<>();
        this.aliases.add(name);
        if (aliases != null) {
            this.aliases.addAll(aliases);
        }
    }
}
