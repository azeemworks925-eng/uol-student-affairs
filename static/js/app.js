/*
  Shared behaviour for the signed-in shell. Progressive enhancement: links, forms and permissions
  all work on the server. Stored preferences are wrapped in try/catch (private browsing).
*/
(function () {
  "use strict";

  var PHONE = window.matchMedia("(max-width: 767.98px)");
  var root = document.documentElement;

  function read(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function write(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* not stored */ }
  }
  function each(selector, callback) {
    Array.prototype.forEach.call(document.querySelectorAll(selector), callback);
  }

  // --- Sidebar: collapsible on laptops, a drawer on phones -------------------------------------
  var toggle = document.querySelector("[data-sidebar-toggle]");
  function syncToggle() {
    if (!toggle) return;
    toggle.setAttribute("aria-expanded", String(!PHONE.matches && root.dataset.sidebar !== "collapsed"));
  }
  if (toggle) {
    toggle.addEventListener("click", function () {
      if (PHONE.matches) {
        var drawer = document.getElementById("sa-drawer");
        if (drawer && window.bootstrap) window.bootstrap.Offcanvas.getOrCreateInstance(drawer).toggle();
        return;
      }
      var collapsed = root.dataset.sidebar === "collapsed";
      if (collapsed) delete root.dataset.sidebar; else root.dataset.sidebar = "collapsed";
      write("sa-sidebar", collapsed ? "open" : "collapsed");
      syncToggle();
    });
    syncToggle();
  }
  // Transitions start after the first paint, so a remembered state never animates on load.
  window.requestAnimationFrame(function () {
    window.requestAnimationFrame(function () { root.classList.add("sa-ready"); });
  });

  // --- Quick search: "/" or Ctrl+K focuses, Esc closes ------------------------------------------
  var search = document.querySelector("[data-quick-search]");
  var searchInput = search ? search.querySelector("input[type='search']") : null;
  function openSearch() {
    if (!search) return;
    search.classList.add("is-open");
    searchInput.focus();
    searchInput.select();
  }
  function closeSearch() {
    if (!search) return;
    search.classList.remove("is-open");
    searchInput.blur();
  }
  each("[data-search-open]", function (button) { button.addEventListener("click", openSearch); });
  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
    } else if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      openSearch();
    } else if (event.key === "Escape" && target === searchInput) {
      closeSearch();
    }
  });

  // --- List / Cards toggle, remembered per page --------------------------------------------------
  each("[data-view-toggle]", function (group) {
    var key = group.getAttribute("data-view-toggle");
    var collections = document.querySelectorAll('[data-view-key="' + key + '"]');
    if (!collections.length) return;
    function apply(view, animate) {
      Array.prototype.forEach.call(collections, function (collection) {
        collection.setAttribute("data-view", view);
        if (animate) {
          collection.classList.remove("is-switching");
          void collection.offsetWidth; // restart the crossfade
          collection.classList.add("is-switching");
        }
      });
      Array.prototype.forEach.call(group.querySelectorAll("[data-view-choice]"), function (button) {
        button.setAttribute("aria-pressed", String(button.getAttribute("data-view-choice") === view));
      });
    }
    var saved = read("sa-view-" + key);
    if (saved === "list" || saved === "cards") apply(saved, false);
    group.addEventListener("click", function (event) {
      var button = event.target.closest("[data-view-choice]");
      if (!button) return;
      var view = button.getAttribute("data-view-choice");
      write("sa-view-" + key, view);
      apply(view, true);
    });
  });

  // --- Meetings: List | Month | Week, remembered ---------------------------------------------------
  var switcher = document.querySelector("[data-meeting-views]");
  if (switcher) {
    var active = switcher.getAttribute("data-meeting-views");
    var explicit = /[?&]view=list\b/.test(window.location.search);
    var savedView = read("sa-meetings-view");
    if (active === "list" && !explicit && !window.location.search && (savedView === "month" || savedView === "week")) {
      var target = switcher.querySelector('[data-view-name="' + savedView + '"]');
      if (target) window.location.replace(target.href);
    } else {
      write("sa-meetings-view", active);
    }
  }

  // --- Dialogs -----------------------------------------------------------------------------------
  each("[data-dialog-open]", function (button) {
    button.addEventListener("click", function () {
      var dialog = document.getElementById(button.getAttribute("data-dialog-open"));
      if (dialog && dialog.showModal) dialog.showModal();
    });
  });
  each("dialog.sa-dialog", function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog || event.target.closest("[data-dialog-close]")) dialog.close();
    });
    // A form returned with errors reopens its dialog.
    if (dialog.hasAttribute("data-open-on-load") && dialog.showModal) dialog.showModal();
  });

  // --- Sticky side panel taller than the window: it sticks by its bottom edge --------------------
  var panel = document.querySelector("[data-sticky-panel]");
  function placePanel() {
    if (!panel) return;
    var top = parseInt(window.getComputedStyle(root).getPropertyValue("--sa-topbar-h"), 10) + 16;
    var room = window.innerHeight - panel.offsetHeight - 16;
    panel.style.setProperty("--sa-panel-top", Math.min(top, room) + "px");
  }
  if (panel) {
    placePanel();
    window.addEventListener("resize", placePanel);
    window.addEventListener("load", placePanel);
  }
})();
