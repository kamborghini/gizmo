    (function () {
        /* ---------- design tokens, read from the stylesheet ----------
           Colour lives in :root and nowhere else. A script that needs a
           value (an SVG stop, a swatch, an email body) asks for it here
           rather than carrying a copy. The stylesheet has loaded before
           this runs, and a custom property's computed value already has
           its var() chain substituted, so what comes back is the hex. */
        function tokenValue(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
        /* The same door for a LENGTH. Geometry the script has to compute with
           (a plot's padding, a dot's radius) still belongs in :root, so it is
           read from there rather than written twice in JavaScript. */
        function tokenNum(name) { return parseFloat(tokenValue(name)) || 0; }
        /* Read once at boot: these do not change without a reload, and a
           getComputedStyle per chart redraw is a layout read in a hot path. */
        const CHART = {
            padL: tokenNum('--chart-pad-l'), padR: tokenNum('--chart-pad-r'),
            padT: tokenNum('--chart-pad-t'), padB: tokenNum('--chart-pad-b'),
            h: tokenNum('--chart-h'), hTall: tokenNum('--chart-h-tall'),
            dotR: tokenNum('--chart-dot-r'), ptR: tokenNum('--chart-pt-r'),
        };

