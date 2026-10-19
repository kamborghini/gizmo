        /* ---------- the field parts ----------
           Switches and fields (docs/DESIGN.md, Switches, Fields and Names):
           - switchBtn() (with the structured-response parts) builds a switch in
             the script; the Settings switches are real switches in the markup.
             setSwitch() turns a switch's look and its spoken state together,
             so nothing has to stamp a state on afterwards;
           - field() builds a captioned field: the house label above its
             control, and a help line under it if it has one. */
        function setSwitch(sw, on) {
            sw.classList.toggle('on', !!on);
            sw.setAttribute('aria-checked', on ? 'true' : 'false');
        }
        /* ---------- the field parts end ---------- */
