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

    // Sync the topbar moon/sun icons to the current theme.
    function syncThemeIcons() {
        var theme = html.getAttribute('data-theme') || 'light';
        // Moon (theme-icon-dark) shows when we're in LIGHT mode (click to go dark).
        // Sun  (theme-icon-light) shows when we're in DARK mode (click to go light).
        document.querySelectorAll('.theme-icon-dark').forEach(function (el) {
            el.classList.toggle('d-none', theme === 'dark');
        });
        document.querySelectorAll('.theme-icon-light').forEach(function (el) {
            el.classList.toggle('d-none', theme === 'light');
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        syncSettingsPanel();
        syncThemeIcons();

        // Wire each radio to apply+persist.
        Object.keys(defaults).forEach(function (k) {
            document.querySelectorAll('input[name="' + k + '"]').forEach(function (r) {
                r.addEventListener('change', function () {
                    if (r.checked) {
                        setAttr(k, r.value);
                        if (k === 'data-theme') syncThemeIcons();
                    }
                });
            });
        });

        // Re-sync the panel radios whenever the offcanvas opens (in case
        // something else updated the data-* attributes in the meantime).
        var offcanvas = document.getElementById('theme-settings-offcanvas');
        if (offcanvas) {
            offcanvas.addEventListener('show.bs.offcanvas', function () {
                syncSettingsPanel();
            });
        }

        // Light/dark quick toggle in topbar
        document.querySelectorAll('.light-dark-mode').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                var cur = html.getAttribute('data-theme') || 'light';
                var next = (cur === 'light') ? 'dark' : 'light';
                setAttr('data-theme', next);
                syncSettingsPanel();
                syncThemeIcons();
            });
        });

        // Sidebar toggle: mobile opens a drawer, desktop toggles default <-> small.
        var hamburger = document.getElementById('topnav-hamburger-icon');
        if (hamburger) {
            hamburger.addEventListener('click', function (e) {
                e.preventDefault();
                if (window.innerWidth < 992) {
                    document.body.classList.toggle('sidebar-enable');
                    return;
                }
                // Horizontal layout: ignore size cycling (no vertical sidebar).
                if (html.getAttribute('data-layout') === 'horizontal') return;
                var cur = html.getAttribute('data-sidebar-size') || 'default';
                var next = (cur === 'default') ? 'small' : 'default';
                setAttr('data-sidebar-size', next);
                syncSettingsPanel();
            });
        }

        // When sidebar is collapsed (small), clicking a menu item with a submenu
        // should expand the sidebar back to "default" and then open that submenu.
        document.querySelectorAll('.menu-link[data-bs-toggle="collapse"]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                if (html.getAttribute('data-sidebar-size') !== 'small') return;
                e.preventDefault();
                e.stopPropagation();
                setAttr('data-sidebar-size', 'default');
                syncSettingsPanel();
                var href = link.getAttribute('href');
                var target = href && document.querySelector(href);
                if (target && window.bootstrap && bootstrap.Collapse) {
                    setTimeout(function () {
                        bootstrap.Collapse.getOrCreateInstance(target, { toggle: false }).show();
                    }, 60);
                }
            });
        });

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
