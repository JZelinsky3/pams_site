/**
 * Shared nav component — The Milk Society
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
 *        data-chapter="PA MILK SOCIETY · VOL. 02"
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
        { key: 'hub',       label: 'The Hub',          path: 'index.html' },
        { key: 'standings', label: 'Standings',         path: 'standings.html' },
        { key: 'managers',  label: 'Managers',          path: 'managers/index.html' },
        { key: 'seasons',   label: 'Season Archives',   path: 'seasons/index.html' },
        { key: 'records',   label: 'Record Book',       path: 'records.html' },
        { key: 'pickems',   label: "Pick'ems",          path: 'pickems/index.html' },
        { key: 'powerrank', label: 'Power Rankings',    path: 'powerrank/index.html' },
        { key: 'draft', label: 'Draft History', path: 'draft/index.html' },
    ];

    // Determine how many levels deep the current page is relative to the site root.
    // On GitHub Pages the URL starts with /repo-name/ which is not part of the
    // site's own directory structure, so skip that first segment.
    function getRoot() {
        var parts = window.location.pathname.split('/').filter(function (p) { return p.length > 0; });
        var skip  = window.location.hostname.endsWith('.github.io') ? 1 : 0;
        var fileParts = parts.slice(skip);
        var depth = fileParts.length > 1 ? fileParts.length - 1 : 0;
        var prefix = '';
        for (var i = 0; i < depth; i++) prefix += '../';
        return prefix;
    }

    function buildNav() {
        var nav = document.getElementById('site-nav');
        if (!nav) return;

        var root        = getRoot();
        var currentPage = nav.dataset.page      || '';
        var chapter     = nav.dataset.chapter   || 'PA MILK SOCIETY';
        var backLabel   = nav.dataset.backLabel  || '';
        var backHref    = nav.dataset.backHref   ? root + nav.dataset.backHref  : '';
        var rightLabel  = nav.dataset.rightLabel || '';
        var rightHref   = nav.dataset.rightHref  ? root + nav.dataset.rightHref : '';
        var titleId     = nav.dataset.titleId    || 'nav-title';

        // Build dropdown links — skip the page you're already on
        var links = PAGES.filter(function (p) { return p.key !== currentPage; }).map(function (p) {
            return '<a href="' + root + p.path + '">' + p.label + '</a>';
        }).join('\n');

        var dropMenu = '<div class="nav-drop" id="nav-drop">'
            + '<button class="nav-drop-btn" onclick="toggleDrop()">Navigate <span class="drop-arrow">▾</span></button>'
            + '<div class="nav-drop-menu">'
            + '<span class="nav-drop-label">Go to</span>'
            + links
            + '</div></div>';

        var leftSlot  = backLabel
            ? '<a href="' + backHref + '" class="nav-back">' + backLabel + '</a>'
            : dropMenu;

        var rightSlot = backLabel
            ? dropMenu
            : (rightLabel ? '<a href="' + rightHref + '" class="nav-link">' + rightLabel + '</a>' : '<span></span>');

        nav.className = 'nav';
        nav.innerHTML = leftSlot
            + '<div class="nav-center">'
            + '<div class="nav-kicker">' + chapter + '</div>'
            + '<div class="nav-title" id="' + titleId + '">The Milk <em>Society.</em></div>'
            + '</div>'
            + rightSlot;

        // Wire up toggle (global so onclick="" can find it)
        window.toggleDrop = function () {
            var drop = document.getElementById('nav-drop');
            if (drop) drop.classList.toggle('open');
        };
        document.addEventListener('click', function (e) {
            var drop = document.getElementById('nav-drop');
            if (drop && !drop.contains(e.target)) drop.classList.remove('open');
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', buildNav);
    } else {
        buildNav();
    }
})();
