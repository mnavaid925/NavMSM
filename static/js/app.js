/* NavMSM — layout & theme switcher (vanilla JS, persists to localStorage) */
(function () {
    'use strict';

    var html = document.documentElement;
    var STORAGE_KEY = 'navmsm.ui';

    var defaults = {
        'data-layout': 'vertical',
        'data-theme': 'light',
        'data-topbar': 'light',
        'data-sidebar': 'light',
        'data-sidebar-size': 'default',
        'data-layout-width': 'fluid',
        'data-layout-position': 'fixed',
        'dir': 'ltr',
    };

    function readStore() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function writeStore(obj) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(obj)); } catch (e) {}
    }

    function applyAll(state) {
        Object.keys(defaults).forEach(function (k) {
            var v = state[k] || defaults[k];
            if (k === 'dir') html.setAttribute('dir', v);
            else html.setAttribute(k, v);
        });
    }
    function setAttr(key, value) {
        if (key === 'dir') html.setAttribute('dir', value);
        else html.setAttribute(key, value);
        var state = readStore();
        state[key] = value;
        writeStore(state);
    }

    // Init from localStorage (overrides server-provided attributes).
    var stored = readStore();
    if (Object.keys(stored).length) applyAll(stored);

    // Sync the settings panel radios to the current state.
    function syncSettingsPanel() {
        Object.keys(defaults).forEach(function (k) {
            var cur = html.getAttribute(k) || defaults[k];
            var radios = document.querySelectorAll('input[name="' + k + '"]');
            radios.forEach(function (r) { r.checked = (r.value === cur); });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        syncSettingsPanel();

        // Wire each radio to apply+persist.
        Object.keys(defaults).forEach(function (k) {
            document.querySelectorAll('input[name="' + k + '"]').forEach(function (r) {
                r.addEventListener('change', function () {
                    if (r.checked) setAttr(k, r.value);
                });
            });
        });

        // Light/dark quick toggle in topbar
        document.querySelectorAll('.light-dark-mode').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var cur = html.getAttribute('data-theme') || 'light';
                var next = (cur === 'light') ? 'dark' : 'light';
                setAttr('data-theme', next);
                syncSettingsPanel();
                document.querySelectorAll('.theme-icon-light').forEach(function (el) {
                    el.classList.toggle('d-none', next === 'light');
                });
                document.querySelectorAll('.theme-icon-dark').forEach(function (el) {
                    el.classList.toggle('d-none', next === 'dark');
                });
            });
        });

        // Sidebar toggle (mobile + desktop)
        var hamburger = document.getElementById('topnav-hamburger-icon');
        if (hamburger) {
            hamburger.addEventListener('click', function () {
                if (window.innerWidth < 992) {
                    document.body.classList.toggle('sidebar-enable');
                } else {
                    var cur = html.getAttribute('data-sidebar-size') || 'default';
                    var next = (cur === 'default') ? 'small' : 'default';
                    setAttr('data-sidebar-size', next);
                    syncSettingsPanel();
                }
            });
        }

        // Tap overlay to close mobile sidebar
        document.querySelectorAll('.vertical-overlay').forEach(function (o) {
            o.addEventListener('click', function () { document.body.classList.remove('sidebar-enable'); });
        });

        // Auto-expand parent of active nav link.
        var links = document.querySelectorAll('.navbar-nav .nav-sm .nav-link');
        links.forEach(function (a) {
            if (a.href && a.href === window.location.href) {
                a.classList.add('active');
                var dropdown = a.closest('.menu-dropdown');
                if (dropdown) {
                    dropdown.classList.add('show');
                    var toggler = document.querySelector('[href="#' + dropdown.id + '"]');
                    if (toggler) toggler.setAttribute('aria-expanded', 'true');
                }
            }
        });
        document.querySelectorAll('.navbar-nav .menu-link').forEach(function (a) {
            if (a.href && a.href === window.location.href) a.classList.add('active');
        });

        // Reset button.
        var resetBtn = document.getElementById('reset-layout');
        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                writeStore({});
                applyAll(defaults);
                syncSettingsPanel();
            });
        }
    });
})();
