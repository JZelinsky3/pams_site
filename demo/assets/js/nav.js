/**
 * Shared nav component — The Lakeside League
 * Usage on each page:
 *   <nav id="site-nav"
 *        data-page="standings"
 *        data-chapter="CH. I · STANDINGS"
 *        data-back-label="← The Hub"
 *        data-back-href="index.html"></nav>
 *   <script src="../assets/js/nav.js"></script>
 *
 * For the hub (no back link, custom right link):
 *   <nav id="site-nav"
 *        data-page="hub"
 *        data-chapter="THE LAKESIDE LEAGUE · VOL. II"
 *        data-right-label="Seasons →"
 *        data-right-href="seasons/index.html"></nav>
 *   <script src="assets/js/nav.js"></script>
 *
 * To add a new page to every nav dropdown, add one entry to PAGES below.
 */
(function () {
    'use strict';

    // ── Page registry — add new pages here ──────────────────────────────────
    var PAGES = [
        { key: 'hub',       label: 'Hub',        path: 'index.html' },
        { key: 'standings', label: 'Standings',       path: 'standings.html' },
        {
            isGroup: true, label: 'Season Odds',
            items: [
                { key: 'pickems',   label: "Pick'ems",       path: 'pickems/index.html' },
                { key: 'powerrank', label: 'Power Rankings', path: 'powerrank/index.html' },
            ]
        },
        {
            isGroup: true, label: 'The Society',
            items: [
                { key: 'managers',  label: 'Managers',  path: 'managers/index.html' },
                { key: 'rivalries', label: 'Rivalries', path: 'rivalries/index.html' },
            ]
        },
        {
            isGroup: true, label: 'League History',
            items: [
                { key: 'seasons', label: 'Season Archives', path: 'seasons/index.html' },
                { key: 'records', label: 'Record Book',     path: 'records.html' },
                { key: 'draft',   label: 'Draft History',   path: 'draft/index.html' },
            ]
        },
    ];

    // Determine how many levels deep the current page is relative to the site root.
    // Build an ABSOLUTE site-root prefix (e.g. '/demo/' or '/jzff/demo/').
    // We return an absolute path instead of relative '../../' because relative
    // resolution breaks when URLs lose their trailing slash (e.g. /demo vs
    // /demo/), which turns out to happen in the wild.
    //   - On GitHub Pages: prepend '/<repo-name>/'
    //   - Inside a /demo/ subfolder: append 'demo/' too
    function getRoot() {
        var parts = window.location.pathname.split('/').filter(function (p) { return p.length > 0; });
        // Drop a trailing filename like 'standings.html' so we never reason
        // about a file as if it were a directory
        if (parts.length && /\.[a-z0-9]+$/i.test(parts[parts.length - 1])) {
            parts = parts.slice(0, -1);
        }
        var prefix;
        if (window.location.hostname.endsWith('.github.io')) {
            prefix = '/' + parts[0] + '/';
            parts = parts.slice(1);
        } else {
            prefix = '/';
        }
        if (parts[0] === 'demo') prefix += 'demo/';
        return prefix;
    }

    function buildNav() {
        var nav = document.getElementById('site-nav');
        if (!nav) return;

        var root        = getRoot();
        var currentPage = nav.dataset.page      || '';
        var chapter     = nav.dataset.chapter   || 'THE LAKESIDE LEAGUE';
        var backLabel   = nav.dataset.backLabel  || '';
        var rightLabel  = nav.dataset.rightLabel || '';
        var rightHref   = nav.dataset.rightHref  ? root + nav.dataset.rightHref : '';
        var titleId     = nav.dataset.titleId    || 'nav-title';
        var titleHref   = nav.dataset.titleHref  ? root + nav.dataset.titleHref : root + 'index.html';

        // Build dropdown links — groups expand on hover; skip current page
        var links = PAGES.map(function (p) {
            if (p.isGroup) {
                var visible = p.items.filter(function (i) { return i.key !== currentPage; });
                if (visible.length === 0) return '';
                var sub = visible.map(function (i) {
                    return '<a href="' + root + i.path + '">' + i.label + '</a>';
                }).join('');
                return '<div class="nav-drop-group">'
                    + '<span class="nav-drop-group-lbl">' + p.label
                    + ' <span class="nav-group-arr">›</span></span>'
                    + '<div class="nav-drop-sub">' + sub + '</div>'
                    + '</div>';
            }
            if (p.key === currentPage) return '';
            return '<a href="' + root + p.path + '">' + p.label + '</a>';
        }).join('');

        var dropMenu = '<div class="nav-drop" id="nav-drop">'
            + '<button class="nav-drop-btn" onclick="toggleDrop()" aria-label="Navigate"><svg class="nav-icon" viewBox="0 0 20 14" width="20" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><line x1="0" y1="1" x2="20" y2="1"/><line x1="0" y1="7" x2="20" y2="7"/><line x1="0" y1="13" x2="20" y2="13"/></svg></button>'
            + '<div class="nav-drop-menu">'
            + '<span class="nav-drop-label">Go to</span>'
            + links
            + '</div></div>';

        var leftSlot  = backLabel
            ? '<button class="nav-back" onclick="history.back()" aria-label="Go back"><svg viewBox="0 0 8 14" width="9" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="7 1 1 7 7 13"/></svg></button>'
            : dropMenu;

        var rightSlot = backLabel
            ? dropMenu
            : (rightLabel ? '<a href="' + rightHref + '" class="nav-link">' + rightLabel + '</a>' : '<span></span>');

        nav.className = 'nav';
        nav.innerHTML = leftSlot
            + '<div class="nav-center">'
            + '<div class="nav-kicker">' + chapter + '</div>'
            + (currentPage === 'hub'
                ? '<div class="nav-title" id="' + titleId + '">The Lakeside <em>League.</em></div>'
                : '<a class="nav-title" id="' + titleId + '" href="' + titleHref + '">The Lakeside <em>League.</em></a>')
            + '</div>'
            + rightSlot;

        // Wire up toggle (global so onclick="" can find it)
        function closeAllGroups(drop) {
            if (!drop) return;
            drop.querySelectorAll('.nav-drop-group.open').forEach(function (g) {
                g.classList.remove('open');
            });
        }
        window.toggleDrop = function () {
            var drop = document.getElementById('nav-drop');
            if (!drop) return;
            drop.classList.toggle('open');
            if (!drop.classList.contains('open')) closeAllGroups(drop);
        };
        document.addEventListener('click', function (e) {
            var drop = document.getElementById('nav-drop');
            if (drop && !drop.contains(e.target)) {
                drop.classList.remove('open');
                closeAllGroups(drop);
            }
        });

        // Tap-to-toggle groups (touch only — desktop keeps its hover behavior).
        // Tapping an open group closes it; tapping a different group closes the
        // previous and opens the new one.
        nav.querySelectorAll('.nav-drop-group-lbl').forEach(function (lbl) {
            lbl.addEventListener('click', function (e) {
                if (!window.matchMedia('(hover: none)').matches) return;
                e.stopPropagation();
                var group = lbl.parentElement;
                var wasOpen = group.classList.contains('open');
                closeAllGroups(document.getElementById('nav-drop'));
                if (!wasOpen) group.classList.add('open');
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', buildNav);
    } else {
        buildNav();
    }
})();
