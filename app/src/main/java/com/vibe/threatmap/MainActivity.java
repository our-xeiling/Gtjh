package com.vibe.threatmap;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import com.vibe.threatmap.core.GeoIndex;
import com.vibe.threatmap.core.GeoPlace;
import com.vibe.threatmap.core.Lexicon;
import com.vibe.threatmap.core.MessageParser;
import com.vibe.threatmap.core.ParsedReport;
import com.vibe.threatmap.core.TrackStore;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final String[] CHANNELS = {
            "dnepr_nagladach",
            "eyes_everywhere_dnipro",
            "PmSDnepra",
            "TesterbotTrevoga"
    };

    private static final long CHANNEL_INTERVAL_MS = 20_000;
    private static final long ALERT_INTERVAL_MS = 60_000;

    private WebView web;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService exec = Executors.newSingleThreadExecutor();

    private MessageParser parser;
    private final TrackStore store = new TrackStore();
    private TgPoller tgPoller;
    private AlertPoller alertPoller;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        try {
            Lexicon lexicon = LexiconLoader.loadLexicon(getAssets().open("dictionaries.json"));
            GeoIndex geoIndex = new GeoIndex();
            for (GeoPlace place : LexiconLoader.loadPlaces(getAssets().open("settlements.json"))) {
                geoIndex.add(place);
            }
            parser = new MessageParser(lexicon, geoIndex);
        } catch (Exception e) {
            throw new IllegalStateException("dictionaries not loadable", e);
        }

        tgPoller = new TgPoller();
        alertPoller = new AlertPoller();

        web = findViewById(R.id.webview);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.addJavascriptInterface(new Bridge(), "Android");
        web.loadUrl("file:///android_asset/index.html");

        ui.post(this::pollChannel);
        ui.post(this::pollAlert);
    }

    private void pollChannel() {
        exec.execute(() -> {
            for (String channel : CHANNELS) {
                try {
                    for (TgPoller.Msg msg : tgPoller.fetchNew(channel)) {
                        ParsedReport report = parser.parse(channel, msg.text, msg.time);
                        store.apply(report);
                    }
                } catch (Exception ignored) {
                }
            }
        });
        ui.postDelayed(this::pollChannel, CHANNEL_INTERVAL_MS);
    }

    private void pollAlert() {
        exec.execute(() -> {
            try {
                boolean alert = alertPoller.dniproAlert();
                store.setAlert(alert ? "on" : "off", System.currentTimeMillis() / 1000L);
            } catch (Exception ignored) {
            }
        });
        ui.postDelayed(this::pollAlert, ALERT_INTERVAL_MS);
    }

    private class Bridge {
        @JavascriptInterface
        public String getState() {
            return store.toJson();
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        exec.shutdownNow();
    }
}
