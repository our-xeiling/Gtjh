package com.vibe.threatmap.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Before;
import org.junit.Test;

public class ParserTest {

    private MessageParser parser;
    private TrackStore store;

    @Before
    public void setUp() {
        Lexicon lexicon = buildLexicon();
        GeoIndex geo = buildGeo();
        parser = new MessageParser(lexicon, geo);
        store = new TrackStore();
    }

    @Test
    public void jetToKryvyiRih() {
        ParsedReport r = parser.parse("ch", "Реактив на Кривий Ріг зі сходу", 1000);
        assertEquals(ParsedReport.KIND_TARGET, r.kind);
        assertEquals("jet", r.type);
        assertEquals("Кривий Ріг", r.lastPlaceName());
        assertNull(r.status);
    }

    @Test
    public void transitVakulove() {
        ParsedReport r = parser.parse("ch", "Проходить с.Вакулове", 1000);
        assertEquals("transit", r.status);
        assertEquals("Вакулове", r.lastPlaceName());
    }

    @Test
    public void countRbpla() {
        ParsedReport r = parser.parse("ch", "1х РБпЛА Соленое", 1000);
        assertEquals("rbpla", r.type);
        assertEquals(Integer.valueOf(1), r.count);
        assertEquals("Солоне", r.lastPlaceName());
        assertEquals("detected", r.status);
    }

    @Test
    public void lostNoFixation() {
        ParsedReport r = parser.parse("ch", "Без фіксації", 1000);
        assertEquals("lost", r.status);
        assertNull(r.placeName);
    }

    @Test
    public void sameTargetReference() {
        ParsedReport r = parser.parse("ch", "Мда, тот же от ПТХ на Соленое", 1000);
        assertTrue(r.sameHint);
        assertEquals("Солоне", r.lastPlaceName());
    }

    @Test
    public void plusOneTransitNorth() {
        ParsedReport r = parser.parse("ch", "+1 рбпла на севере транзит", 1000);
        assertTrue(r.newHint);
        assertEquals("rbpla", r.type);
        assertEquals("N", r.direction);
        assertEquals("transit", r.status);
    }

    @Test
    public void altitude() {
        ParsedReport r = parser.parse("ch", "Курсом на Петропавлівку. Висота 4500м", 1000);
        assertEquals(Integer.valueOf(4500), r.altitudeM);
    }

    @Test
    public void donationIsNoise() {
        ParsedReport r = parser.parse("ch", "За оперативність хто хоче по 1-2 грн на каву 5375411223232682", 1000);
        assertEquals(ParsedReport.KIND_NOISE, r.kind);
    }

    @Test
    public void friendlyTalkIsNoise() {
        ParsedReport r = parser.parse("ch", "Тихой ночи", 1000);
        assertEquals(ParsedReport.KIND_NOISE, r.kind);
    }

    @Test
    public void alertEchoOn() {
        ParsedReport r = parser.parse("ch", "🔴 Дніпровський район — повітряна тривога, червоний рівень", 1000);
        assertEquals(ParsedReport.KIND_ALERT_ECHO, r.kind);
        assertTrue(r.alertOn);
    }

    @Test
    public void alertEchoOff() {
        ParsedReport r = parser.parse("ch", "🟢 Дніпровський район — відбій повітряної тривоги", 1000);
        assertEquals(ParsedReport.KIND_ALERT_ECHO, r.kind);
        assertFalse(r.alertOn);
    }

    @Test
    public void latinAbbreviationInMixedText() {
        ParsedReport r = parser.parse("ch", "FPV над Войсковое", 1000);
        assertEquals("fpv", r.type);
        assertEquals("Військове", r.lastPlaceName());
    }

    @Test
    public void trackSequenceBuildsHistoryAndResurrests() {
        store.apply(parser.parse("ch", "1х РБпЛА Соленое", 1000));
        store.apply(parser.parse("ch", "Взяли курс запад от города, Днепр пока курим", 1100));
        store.apply(parser.parse("ch", "Пропал на пересечении областей, доразведка", 1200));
        store.apply(parser.parse("ch", "Вылез. На того же туриста, без угроз", 1300));

        String json = store.toJson();
        assertTrue(json.contains("\"tracks\":["));
        assertTrue(json.contains("\"status\":\"redetected\""));
        assertTrue(json.contains("\"heading\":\"W\""));
        assertTrue(json.contains("Солоне"));
        assertTrue(json.contains("\"type\":\"rbpla\""));
    }

    @Test
    public void allClearLeftsChannelTracks() {
        store.apply(parser.parse("ch", "1х РБпЛА Соленое", 1000));
        store.apply(parser.parse("ch", "Відбій", 1100));
        assertTrue(store.toJson().contains("\"status\":\"left\""));
    }

    private Lexicon buildLexicon() {
        Lexicon lexicon = new Lexicon();
        lexicon.addStatus("overhead", java.util.Arrays.asList("покров над", "над вами"));
        lexicon.addStatus("approach", java.util.Arrays.asList("покров наближ", "наближає"));
        lexicon.addStatus("all_clear", java.util.Arrays.asList("відбій", "отбой"));
        lexicon.addStatus("loiter", java.util.Arrays.asList("круж", "наматыва", "круги"));
        lexicon.addStatus("lost", java.util.Arrays.asList("пропа", "зник", "без фікс", "дорозвід"));
        lexicon.addStatus("redetected", java.util.Arrays.asList("виліз", "вилез"));
        lexicon.addStatus("left", java.util.Arrays.asList("улет", "пішов", "пролет"));
        lexicon.addStatus("transit", java.util.Arrays.asList("проход", "транзит", "повз", "вздовж"));
        lexicon.addStatus("no_threat", java.util.Arrays.asList("без загроз", "без угроз", "курим"));
        lexicon.addStatus("tracked", java.util.Arrays.asList("курс", "повернув", "иде на"));
        lexicon.addStatus("detected", java.util.Arrays.asList("вході", "входе", "зафіксов", "фіксац"));
        lexicon.addType("fpv", java.util.Arrays.asList("fpv", "фпв"));
        lexicon.addType("rbpla", java.util.Arrays.asList("рбпла", "рб-пла"));
        lexicon.addType("jet", java.util.Arrays.asList("реактив"));
        lexicon.addType("br", java.util.Arrays.asList("балістичн", "ісд"));
        lexicon.addType("kr", java.util.Arrays.asList("крилат", "крылат"));
        lexicon.addType("aviation", java.util.Arrays.asList("міг", "авиація"));
        lexicon.addType("drone", java.util.Arrays.asList("бпла", "дрон", "шахед"));
        lexicon.addDirection("N", java.util.Arrays.asList("північ", "север"));
        lexicon.addDirection("S", java.util.Arrays.asList("півд", "юг"));
        lexicon.addDirection("E", java.util.Arrays.asList("схід", "восток"));
        lexicon.addDirection("W", java.util.Arrays.asList("захід", "запад"));
        lexicon.noiseMatchers.addAll(java.util.Arrays.asList("каву", "картк", "донат", "тихой ноч", "зв'язку"));
        lexicon.sameTargetMarkers.addAll(java.util.Arrays.asList("той сам", "того же", "того ж", "турист"));
        lexicon.newTargetMarkers.addAll(java.util.Arrays.asList("новий", "нові", "ще один"));
        return lexicon;
    }

    private GeoIndex buildGeo() {
        GeoIndex geo = new GeoIndex();
        geo.add(new GeoPlace("Дніпро", 48.4647, 35.0462, java.util.Arrays.asList("днепр", "центр")));
        geo.add(new GeoPlace("Кривий Ріг", 47.9105, 33.3918, java.util.Arrays.asList("кривой рог")));
        geo.add(new GeoPlace("Нікополь", 47.5716, 34.4003, java.util.Arrays.asList("никополь")));
        geo.add(new GeoPlace("Солоне", 48.3546, 35.3064, java.util.Arrays.asList("соленое")));
        geo.add(new GeoPlace("Військове", 48.4287, 35.5478, java.util.Arrays.asList("войсковое")));
        geo.add(new GeoPlace("Вакулове", 47.9866, 33.7716, java.util.Arrays.asList("вакулово")));
        geo.add(new GeoPlace("Підгороднє", 48.5636, 35.1353, java.util.Arrays.asList("подгородное", "подгар", "птх")));
        return geo;
    }
}
