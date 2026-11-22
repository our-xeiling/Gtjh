package com.vibe.threatmap.core;

public final class Fuzzy {

    private Fuzzy() {
    }

    public static int distance(String a, String b) {
        int la = a.length();
        int lb = b.length();
        int[][] d = new int[la + 1][lb + 1];
        for (int i = 0; i <= la; i++) {
            d[i][0] = i;
        }
        for (int j = 0; j <= lb; j++) {
            d[0][j] = j;
        }
        for (int j = 1; j <= lb; j++) {
            for (int i = 1; i <= la; i++) {
                int cost = a.charAt(i - 1) == b.charAt(j - 1) ? 0 : 1;
                int best = Math.min(d[i - 1][j] + 1, Math.min(d[i][j - 1] + 1, d[i - 1][j - 1] + cost));
                if (i > 1 && j > 1 && a.charAt(i - 1) == b.charAt(j - 2) && a.charAt(i - 2) == b.charAt(j - 1)) {
                    best = Math.min(best, d[i - 2][j - 2] + 1);
                }
                d[i][j] = best;
            }
        }
        return d[la][lb];
    }

    public static boolean close(String a, String b, int maxDist) {
        if (a.equals(b)) {
            return true;
        }
        int tolerance = Math.max(1, maxDist);
        if (Math.abs(a.length() - b.length()) > tolerance) {
            return false;
        }
        return distance(a, b) <= tolerance;
    }
}
