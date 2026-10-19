        /* ---------- icons (constant SVG; safe to inject) ---------- */
        // Feather Icons (https://feathericons.com), inlined so there are no extra requests.
        /* aria-hidden on the factory, so it holds for every icon in the app
           rather than at hundreds of call sites. These are all decorative: the
           control around them carries the name, and an icon that announced
           itself would just read the name twice. focusable="false" keeps them
           out of the tab order, which some engines still put them in. */
        const SV = (inner) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + inner + '</svg>';
        const I = {
            mail: SV('<rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"></path>'),
            clip: SV('<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>'),
            hardDrive: SV('<line x1="22" y1="12" x2="2" y2="12"></line><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"></path><line x1="6" y1="16" x2="6.01" y2="16"></line><line x1="10" y1="16" x2="10.01" y2="16"></line>'),
            copy: SV('<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'),
            phone: SV('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>'),
            cal: SV('<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>'),
            clock: SV('<circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline>'),
            flag: SV('<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>'),
            coffee: SV('<path d="M18 8h1a4 4 0 0 1 0 8h-1"></path><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"></path>'),
            spark: SV('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>'),
            grid: SV('<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>'),
            chat: SV('<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>'),
            plus: SV('<path d="M5 12h14"/><path d="M12 5v14"/>'),
            menu: SV('<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>'),
            panelLeft: SV('<rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M9 3v18"></path>'),
            moreH: SV('<circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle>'),
            loader: SV('<path d="M21 12a9 9 0 1 1-6.219-8.56"></path>'),
            refresh: SV('<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'),
            send: SV('<line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>'),
            history: SV('<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>'),
            archive: SV('<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>'),
            archiveRestore: SV('<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/>'),
            trash: SV('<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line>'),
            chev: SV('<path d="m9 18 6-6-6-6"/>'),
            inbox: SV('<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'),
            sort: SV('<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>'),
            checkCircle: SV('<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
            /* A menu opens downward, so its trigger points down. The right
               chevron is the app's "next", and it read as navigation. */
            chevDown: SV('<path d="m6 9 6 6 6-6"/>'),
            up: SV('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline>'),
            arrowDown: SV('<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>'),
            down: SV('<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"></polyline><polyline points="17 18 23 18 23 12"></polyline>'),
            check: SV('<path d="M20 6 9 17l-5-5"/>'),
            gripVertical: SV('<circle cx="9" cy="12" r="1"></circle><circle cx="9" cy="5" r="1"></circle><circle cx="9" cy="19" r="1"></circle><circle cx="15" cy="12" r="1"></circle><circle cx="15" cy="5" r="1"></circle><circle cx="15" cy="19" r="1"></circle>'),
            eyeOff: SV('<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"></path><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"></path><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"></path><path d="m2 2 20 20"></path>'),
            win: SV('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'),
            warning: SV('<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>'),
            opportunity: SV('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline>'),
            insight: SV('<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>'),
            search: SV('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
            bookmark: SV('<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>'),
            book: SV('<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>'),
            tag: SV('<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5"/>'),
            globe: SV('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
            users: SV('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
            rotate: SV('<polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>'),
            box: SV('<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"/><path d="m7.5 4.27 9 5.15"/>'),
            /* One glyph per section, from the same lucide set: two sections
               shared a tick, two a box, Forecast wore an 'info' circle, and
               Xero sync the chat's Send arrow. */
            scale: SV('<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="M7 21h10"></path><path d="M12 3v18"></path><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"></path>'),
            trendUp: SV('<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>'),
            arrowsLR: SV('<path d="M8 3 4 7l4 4"></path><path d="M4 7h16"></path><path d="m16 21 4-4-4-4"></path><path d="M20 17H4"></path>'),
            ruler: SV('<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"></path><path d="m14.5 12.5 2-2"></path><path d="m11.5 9.5 2-2"></path><path d="m8.5 6.5 2-2"></path><path d="m17.5 15.5 2-2"></path>'),
            projector: SV('<path d="M5 7 3 5"></path><path d="M9 6V3"></path><path d="m13 7 2-2"></path><circle cx="9" cy="13" r="3"></circle><path d="M11.83 12H20a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h2.17"></path><path d="M16 16h2"></path>'),
            sliders: SV('<line x1="21" x2="14" y1="4" y2="4"></line><line x1="10" x2="3" y1="4" y2="4"></line><line x1="21" x2="12" y1="12" y2="12"></line><line x1="8" x2="3" y1="12" y2="12"></line><line x1="21" x2="16" y1="20" y2="20"></line><line x1="12" x2="3" y1="20" y2="20"></line><line x1="14" x2="14" y1="2" y2="6"></line><line x1="8" x2="8" y1="10" y2="14"></line><line x1="16" x2="16" y1="18" y2="22"></line>'),
            truck: SV('<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>'),
            chevLeft: SV('<polyline points="15 18 9 12 15 6"></polyline>'),
            chevFirst: SV('<polyline points="11 17 6 12 11 7"></polyline><polyline points="18 17 13 12 18 7"></polyline>'),
            chevLast: SV('<polyline points="13 17 18 12 13 7"></polyline><polyline points="6 17 11 12 6 7"></polyline>'),
            settings: SV('<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>'),
            x: SV('<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>'),
            arrowUpRight: SV('<path d="M7 17 17 7"/><path d="M7 7h10v10"/>'),
            maximize: SV('<polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line>'),
            edit: SV('<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/>'),
            download: SV('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'),
            eye: SV('<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>'),
            printer: SV('<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>'),
            folder: SV('<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'),
            folderPlus: SV('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line>'),
            upload: SV('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>'),
            fileDoc: SV('<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline>'),
            briefcase: SV('<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>'),
            userCheck: SV('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/>'),
            helpCircle: SV('<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>'),
            info: SV('<circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path>'),
            arrowRight: SV('<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>'),
            arrowDownRight: SV('<path d="m7 7 10 10"></path><path d="M17 7v10H7"></path>'),
            wallet: SV('<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"></path><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"></path>'),
            compass: SV('<circle cx="12" cy="12" r="10"></circle><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"></path>'),
            target: SV('<circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle>'),
            shield: SV('<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path><path d="m9 12 2 2 4-4"></path>'),
            table: SV('<path d="M12 3v18"></path><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M3 9h18"></path><path d="M3 15h18"></path>'),
            cash: SV('<rect width="20" height="12" x="2" y="6" rx="2"></rect><circle cx="12" cy="12" r="2"></circle><path d="M6 12h.01M18 12h.01"></path>'),
            columns: SV('<rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M9 3v18"></path><path d="M15 3v18"></path>'),
            compare: SV('<circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><path d="M11 18H8a2 2 0 0 1-2-2V9"></path>'),
            card: SV('<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>'),
            logOut: SV('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line>'),
            logIn: SV('<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line>'),
            lock: SV('<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path>'),
            user: SV('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle>'),
            atSign: SV('<circle cx="12" cy="12" r="4"></circle><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"></path>'),
            key: SV('<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path>'),
            fileImg: SV('<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline>'),
            fileZip: SV('<polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line>'),
            /* A PDF is the commonest file in this store and it was falling
               through to the generic page, so a proof and a note looked alike. */
            filePdf: SV('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M9 19v-7h2a2 2 0 0 1 0 4H9"></path>'),
            fileSheet: SV('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>'),
            penTool: SV('<path d="M12 19l7-7 3 3-7 7-3-3z"></path><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path><circle cx="11" cy="11" r="2"></circle>'),
            moveTo: SV('<polyline points="15 14 20 9 15 4"></polyline><path d="M4 20v-7a4 4 0 0 1 4-4h12"></path>'),
        };
        const el = (t, c, txt) => { const e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; };
        const loader = () => { const s = el('span', 'spinner'); s.innerHTML = I.loader; s.setAttribute('aria-hidden', 'true'); return s; };
        /* The .ic class is the whole fix for icons floating above button text:
           a bare span leaves the svg sitting ON the text baseline inside the
           button's 20px line box, ~3px above the text's optical middle. */
        /* ico() is the one helper that puts a string into innerHTML on purpose,
           so it checks that the string is one of OUR icons rather than trusting
           its caller. Every caller passes an I.* constant today; this is what
           keeps that true when somebody writes ico(item.icon) from server JSON. */
        const ICON_MARKUP = new Set(Object.values(I).filter(v => typeof v === 'string'));
        const ico = (svg) => {
            const s = el('span', 'ic');
            if (ICON_MARKUP.has(svg)) s.innerHTML = svg;
            return s;
        };
        /* An anchor with an onclick and no href is a button wearing a link's
           clothes: the pointer stays an arrow and the tab order walks straight
           past it, so the word looks like a door to a mouse and does not exist
           to a keyboard. These are real in-page actions, so they say so - and
           they keep the underline, which is what tells a reader it is a door
           in the first place. Anything with a real href stays a real link. */
        const actionLink = (cls, txt) => {
            const a = el('a', cls, txt);
            a.setAttribute('role', 'button'); a.tabIndex = 0;
            a.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); a.click(); }
            });
            return a;
        };
        const $ = (id) => document.getElementById(id);
        /* A time of day as the clock on the wall showed it. The stamps are UTC,
           and slicing the hour out of one put every clock-in an hour early from
           March to October. */
        function londonHM(iso) {
            const d = new Date(iso);
            if (isNaN(d)) return String(iso || '').slice(11, 16);
            return d.toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' });
        }
        /* One way to write a date, in British order, with the same month
           abbreviations the chart axes use: '23 Sep', or '23 Sep 2025' in
           another year. It followed the browser's locale, so an American
           browser wrote 'Sep 23' beside axes reading '5 Sep', and a British
           one wrote 'Sept'. A bare ISO day ('2026-09-20') is read as that
           calendar day, not as midnight UTC shifted into the viewer's zone. */
        function fmtDate(iso) {
            const s = String(iso || '');
            const d = /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(s + 'T12:00:00') : new Date(iso);
            if (isNaN(d)) return s.slice(0, 10);
            const out = d.getDate() + ' ' + MONTH_ABBR[d.getMonth()];
            return d.getFullYear() !== new Date().getFullYear() ? out + ' ' + d.getFullYear() : out;
        }
        function freshLabel(at) {
            const m = Math.max(0, Math.round((Date.now() - (at || 0)) / 60000));
            if (m < 1) return 'Updated just now';
            if (m < 60) return 'Updated ' + m + 'm ago';
            const h = Math.round(m / 60);
            if (h < 24) return 'Updated ' + h + 'h ago';
            const d = Math.round(h / 24);
            return 'Updated ' + d + (d === 1 ? ' day ago' : ' days ago');
        }

        /* The right side of a page header, as the reference lays it out: the
           "last updated" line and the page's own buttons in one row, which
           drops under the title on a phone. Refresh lives here, beside the
           stamp it renews, rather than in the app's header. */
        function heroAct(updated, ...buttons) {
            const act = el('div', 'ov-hero-act');
            if (updated) act.append(el('div', 'ov-updated', updated));
            buttons.filter(Boolean).forEach(b => act.append(b));
            return act;
        }
        function refreshBtn(onClick, label) {
            const b = el('button', 'btn btn-sm btn-icon');
            b.type = 'button'; b.append(ico(I.refresh));
            b.title = label || 'Refresh'; b.setAttribute('aria-label', label || 'Refresh');
            b.onclick = () => { setBusy(b, true); Promise.resolve().then(onClick).finally(() => setBusy(b, false)); };
            return b;
        }
        /* The page header (the mix, spec 5): a Bricolage title, Beta beside it
           on the pages BETA_TABS names, at most one short line under it or a
           status line, and the page's actions on the right.
           o: { view, title, info: an infoButton, line, status: [words, ...], live: a time in ms,
           onRefresh, refreshLabel, actions: [nodes] }. The names .ov-hero and
           .ov-hero-act stay: the widget grid puts Customise in the rail by
           them, and a printed report hides the rail by them. */
        function pageHead(o) {
            const hero = el('div', 'ov-hero');
            const text = el('div', 'ph-text');
            const h = el('h2', null, o.title);
            if (o.view && BETA_TABS.indexOf(o.view) >= 0) h.append(el('span', 'beta-tag', 'Beta'));
            /* The info button sits beside the heading, not in it, so the heading's name stays its title. */
            if (o.info) { const row = el('div', 'ph-title'); row.append(h, o.info); text.append(row); } else text.append(h);
            if (o.live != null) {
                const sub = el('div', 'ph-sub');
                const dot = el('span', 'live-dot'); dot.setAttribute('aria-hidden', 'true');
                sub.append(dot, el('span', 'ov-updated', freshLabel(o.live)));
                if (o.onRefresh) { const r = refreshBtn(o.onRefresh, o.refreshLabel); r.className = 'info'; sub.append(r); }
                text.append(sub);
            } else if (o.status && o.status.length) {
                const sub = el('div', 'ph-sub');
                o.status.forEach((t, i) => {
                    if (i) { const s = el('span', 'dot-sep'); s.setAttribute('aria-hidden', 'true'); sub.append(s); }
                    sub.append(el('span', null, t));
                });
                text.append(sub);
            } else if (o.line) text.append(el('p', null, o.line));
            hero.append(text, heroAct('', ...(o.actions || [])));
            return hero;
        }
        /* An explanation on request (the mix, spec 6 and 7): a 24 info glyph
           beside a heading or a figure label, opening a popover with the words
           that used to sit under the title, moved word for word, and a link to
           the Guide. A tap and the keyboard open it as well as a click, which
           the old title text on hover never did. o: { title, body: a string or
           [strings and nodes], guide: [section id, search] } */
        function infoButton(label, o) {
            const b = el('button', 'info');
            b.type = 'button'; b.title = label;
            b.setAttribute('aria-label', label);
            b.setAttribute('aria-haspopup', 'dialog');
            b.setAttribute('aria-expanded', 'false');
            b.append(ico(I.info));
            b.onclick = (e) => {
                e.stopPropagation();
                dropPanel(b, (box) => {
                    box.classList.add('ipop');
                    if (o.title) box.append(el('h3', null, o.title));
                    [].concat(o.body || []).filter(Boolean).forEach(t => box.append(typeof t === 'string' ? el('p', null, t) : t));
                    if (o.guide) {
                        const a = textLink('More in the Guide', { size: 'go', icon: I.arrowRight });
                        a.type = 'button';
                        a.onclick = () => { closeDMenu(); openGuideAt(o.guide[0], o.guide[1] || ''); };
                        box.append(a);
                    }
                });
            };
            return b;
        }
        /* A heading with its info button: the button sits beside the heading in a row (as the page
           header's does), never inside it, so the heading's name is its words and the button is its
           own control, named About <title>. A heading already in its head is replaced by the row in
           place; one not yet placed comes back as the row to append. */
        function titleInfo(h, info) {
            const row = el('div', 'title-row'), at = h.parentNode;
            if (at) at.insertBefore(row, h);
            row.append(h, info);
            return row;
        }
        /* How it works (the mix, spec 6): one header button holding a screen's
           method pages as a menu, the Guide's link last after a rule. items:
           [{ icon, label, n, onClick }]; guide: { label, at: [section id, search] }. */
        function howItWorks(items, guide) {
            const b = el('button', 'btn');
            b.type = 'button';
            b.append(ico(I.helpCircle), document.createTextNode('How it works'));
            b.setAttribute('aria-haspopup', 'menu'); b.setAttribute('aria-expanded', 'false');
            b.onclick = () => dropMenu(b, items.concat(guide ? ['-', { label: guide.label, link: true,
                onClick: () => openGuideAt(guide.at[0], guide.at[1] || '') }] : []));
            return b;
        }
        // static icon wiring
        $('nav-overview').append(ico(I.grid), document.createTextNode('Overview'));
        $('nav-seo').append(ico(I.globe), document.createTextNode('SEO'));
        $('nav-keywords').append(ico(I.tag), document.createTextNode('Keywords'));
        $('nav-products').append(ico(I.box), document.createTextNode('Products'));
        $('nav-customers').append(ico(I.users), document.createTextNode('Customers'));
        $('nav-liability').append(ico(I.card), document.createTextNode('Liability'));
        $('nav-recon').append(ico(I.scale), document.createTextNode('Reconciliation'),
            el('span', 'beta-tag', 'Beta'));
        $('nav-forecast').append(ico(I.trendUp), document.createTextNode('Forecast'),
            el('span', 'beta-tag', 'Beta'));
        $('nav-connector').append(ico(I.arrowsLR), document.createTextNode('Xero sync'),
            el('span', 'beta-tag', 'Beta'));
        $('nav-sizes').append(ico(I.ruler), document.createTextNode('Size list'));
        $('nav-crm').append(ico(I.briefcase), document.createTextNode('CRM'),
            el('span', 'beta-tag', 'Beta'));
        $('nav-loans').append(ico(I.projector), document.createTextNode('Loan units'));
        $('nav-mail').append(ico(I.inbox), document.createTextNode('Inbox'));
        $('nav-files').append(ico(I.folder), document.createTextNode('Files'));
        $('nav-team').append(ico(I.userCheck), document.createTextNode('Team'));
        $('nav-labels').append(ico(I.printer), document.createTextNode('Production Manager'));
        $('nav-memory').append(ico(I.bookmark), document.createTextNode('Memory'));
        $('nav-skills').append(ico(I.book), document.createTextNode('Skills'));
        $('nav-chat').append(ico(I.chat), document.createTextNode('Chat'));
        $('nav-guide').append(ico(I.helpCircle), document.createTextNode('Guide'));
        $('brand-home').onclick = () => setView('overview');
        $('new-convo').innerHTML = I.plus;
        /* The top bar's button: the panel glyph beside a sidebar that can hide, the menu glyph while the sidebar is a drawer (900 and under). */
        $('menu-btn').innerHTML = I.panelLeft + I.menu;
        { const mb = $('menu-btn').querySelectorAll('svg'); mb[0].classList.add('mb-panel'); mb[1].classList.add('mb-menu'); }
        $('side-hide').innerHTML = I.panelLeft;
        $('crumb-chev').innerHTML = I.chev;
        $('side-user-more').innerHTML = I.moreH;
        $('side-user').onclick = userMenu;
        $('topbar-search').append(ico(I.search), el('span', 'ts-label', 'Search'),
            el('kbd', null, /Mac|iPhone|iPad/.test(navigator.platform || '') ? '\u2318J' : 'Ctrl J'));
        $('topbar-search').onclick = openSearch;
        $('send').innerHTML = I.send;
        $('settings-btn').innerHTML = I.settings;
        $('logout-btn').innerHTML = I.logOut;
        $('logout-btn').onclick = () => authLogout();
