package com.vibe.threatmap;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TgPoller {

    private static final Pattern DATA_POST = Pattern.compile("data-post=\"([^\"]+)\"");
    private static final Pattern TIME = Pattern.compile("datetime=\"([^\"]+)\"");
    private static final Pattern TEXT = Pattern.compile(
            "<div class=\"tgme_widget_message_text[^\"]*\"[^>]*>(.*?)</div>",
            Pattern.DOTALL);

    private final Map<String, Long> lastIds = new HashMap<>();

    public static class Msg {
        public String channel;
        public long id;
        public long time;
        public String text;
    }

    public synchronized List<Msg> fetchNew(String channel) throws Exception {
        String html = httpGet("https://t.me/s/" + channel);
        List<Msg> messages = parseHtml(channel, html);
        Long last = lastIds.get(channel);
        List<Msg> fresh = new ArrayList<>();
        for (Msg m : messages) {
            if (last == null || m.id > last) {
                fresh.add(m);
            }
        }
        if (!messages.isEmpty()) {
            lastIds.put(channel, messages.get(messages.size() - 1).id);
        }
        return fresh;
    }

    static List<Msg> parseHtml(String channel, String html) {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss");
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        List<Msg> out = new ArrayList<>();
        Matcher post = DATA_POST.matcher(html);
        while (post.find()) {
            Msg m = new Msg();
            m.channel = channel;
            String postRef = post.group(1);
            int slash = postRef.lastIndexOf('/');
            try {
                m.id = Long.parseLong(postRef.substring(slash + 1));
            } catch (NumberFormatException e) {
                continue;
            }
            int blockEnd = html.length();
            Matcher next = DATA_POST.matcher(html);
            if (next.find(post.end())) {
                blockEnd = next.start();
            }
            String block = html.substring(post.start(), blockEnd);

            Matcher tm = TIME.matcher(block);
            if (tm.find()) {
                try {
                    Date d = fmt.parse(tm.group(1).substring(0, 19));
                    if (d != null) {
                        m.time = d.getTime() / 1000L;
                    }
                } catch (ParseException ignored) {
                    m.time = System.currentTimeMillis() / 1000L;
                }
            } else {
                m.time = System.currentTimeMillis() / 1000L;
            }

            Matcher tx = TEXT.matcher(block);
            if (tx.find()) {
                m.text = stripTags(tx.group(1)).trim();
            } else {
                continue;
            }
            if (m.text.isEmpty()) {
                continue;
            }
            out.add(m);
        }
        mergeDuplicates(out);
        return out;
    }

    private static void mergeDuplicates(List<Msg> list) {
        Map<Long, Msg> byId = new TreeMap<>();
        for (Msg m : list) {
            Msg prev = byId.get(m.id);
            if (prev == null || prev.text.length() > m.text.length()) {
                byId.put(m.id, m);
            }
        }
        list.clear();
        list.addAll(byId.values());
    }

    private static String stripTags(String html) {
        String s = html.replace("<br/>", "\n").replace("<br>", "\n").replace("<br />", "\n");
        s = s.replaceAll("<[^>]+>", "");
        s = s.replace("&quot;", "\"").replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&nbsp;", " ").replace("&rarr;", "->")
                .replace("&laquo;", "«").replace("&raquo;", "»");
        s = s.replaceAll("\n{2,}", "\n");
        return s;
    }

    private static String httpGet(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36");
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
