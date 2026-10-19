        /* ---------- the field parts ----------
           Switches and fields (docs/DESIGN.md, Switches, Fields and Names):
           - switchBtn() (with the structured-response parts) builds a switch in
             the script; the Settings switches are real switches in the markup.
             setSwitch() turns a switch's look and its spoken state together,
             so nothing has to stamp a state on afterwards;
           - formField() builds a captioned field: the house label above its
             control, and a help line under it if it has one. */
        function setSwitch(sw, on) {
            sw.classList.toggle('on', !!on);
            sw.setAttribute('aria-checked', on ? 'true' : 'false');
        }
        function formField(caption, control, opts) {
            const o = opts || {};
            const f = el('label', 'pfield' + (o.cls ? ' ' + o.cls : ''));
            f.append(el('span', null, caption));
            if (control) f.append(control);
            if (o.help) f.append(el('p', 'field-help', o.help));
            return f;
        }
        /* ---------- the field parts end ---------- */
