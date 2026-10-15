        /* ---------- component states ----------
           The stylesheet keys loading and invalid off ARIA, so the state a
           screen reader hears is the state the eye sees. These are the two
           entry points; nothing else should touch those attributes. */
        function setBusy(ctrl, on) {
            ctrl.disabled = !!on;
            if (on) ctrl.setAttribute('aria-busy', 'true'); else ctrl.removeAttribute('aria-busy');
        }
        function markInvalid(field, on) {
            if (on) field.setAttribute('aria-invalid', 'true'); else field.removeAttribute('aria-invalid');
        }

