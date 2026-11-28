/*
  Shared behaviour for every page (Polish v2, docs/POLISH_V2.md). Progressive enhancement only:
  links, forms, selects and permissions all work on the server without this file. Stored
  preferences are wrapped in try/catch (private browsing). Under prefers-reduced-motion nothing
  moves: count-ups show the final number and states change instantly.

  Contents: helpers · theme · sidebar · search · popovers (<details class="sa-pop">) · dropdown
  (select enhancement) · segmented controls · list/cards toggle · meetings view · dialogs ·
  toasts · bell · count-up and fill · "not ready" buttons · sticky side panel.
*/
(function () {
  "use strict";

  var PHONE = window.matchMedia("(max-width: 767.98px)");
  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)");
  var root = document.documentElement;

  function read(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function write(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* not stored */ }
  }
  function each(selector, callback, scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll(selector), callback);
  }
  function csrf(form) {
    var input = form && form.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  // --- Theme: sun / moon, remembered; the first visit follows the device -----------------------
  function applyTheme(theme) {
    root.dataset.theme = theme;
    each("[data-theme-choice]", function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-theme-choice") === theme));
    });
    each("[data-theme-toggle]", function (group) { if (group._seg) group._seg(); });
  }
  each("[data-theme-choice]", function (button) {
    button.addEventListener("click", function () {
      var theme = button.getAttribute("data-theme-choice");
      write("sa-theme", theme);
      applyTheme(theme);
    });
  });
  applyTheme(root.dataset.theme === "dark" ? "dark" : "light");

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

  // --- Quick search: "/" or Ctrl+K focuses, Esc closes; a full-width sheet on phones -----------
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
  each("[data-search-close]", function (button) { button.addEventListener("click", closeSearch); });
  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && search) {
      event.preventDefault();
      openSearch();
    } else if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey && search) {
      event.preventDefault();
      openSearch();
    } else if (event.key === "Escape" && target === searchInput) {
      closeSearch();
    }
  });

  // --- Popovers: <details class="sa-pop"> -------------------------------------------------------
  // They open without JS; here: one open at a time, Esc closes and returns focus, arrow keys move
  // between menu items, and a short closing animation.
  function closePop(details, restoreFocus) {
    if (!details.open) return;
    var summary = details.querySelector("summary");
    if (REDUCED.matches) {
      details.open = false;
    } else {
      details.classList.add("is-closing");
      window.setTimeout(function () { details.open = false; details.classList.remove("is-closing"); }, 110);
    }
    if (restoreFocus && summary) summary.focus();
  }
  function popItems(details) {
    return Array.prototype.filter.call(
      details.querySelectorAll(".sa-pop-panel a[href], .sa-pop-panel button:not([disabled])"),
      function (el) { return el.offsetParent !== null; }
    );
  }
  each("details.sa-pop", function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;
      each("details.sa-pop[open]", function (other) { if (other !== details) other.open = false; });
      details.dispatchEvent(new CustomEvent("sa:open", { bubbles: true }));
    });
    details.addEventListener("keydown", function (event) {
      if (!details.open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closePop(details, true);
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        var items = popItems(details);
        if (!items.length) return;
        event.preventDefault();
        var index = items.indexOf(document.activeElement);
        index = event.key === "ArrowDown" ? (index + 1) % items.length : (index <= 0 ? items.length - 1 : index - 1);
        items[index].focus();
      }
    });
  });
  document.addEventListener("click", function (event) {
    each("details.sa-pop[open]", function (details) {
      if (!details.contains(event.target)) closePop(details, false);
    });
  });

  // --- Dropdown: one for the whole platform, over a real <select> ------------------------------
  // Every select.form-select (and select[data-dropdown]) becomes a pill trigger and a menu with
  // tinted items and ✓ on the selected one. The select stays in the form and keeps the value; a
  // change is mirrored with real "change" events, so other scripts (complaints.js) keep working.
  var ddCount = 0;
  function optionText(option) {
    return option.getAttribute("data-short") || option.textContent.trim();
  }
  function enhanceSelect(select) {
    if (select._dd || select.multiple || select.size > 1 || select.hasAttribute("data-native")) return;
    var id = "sa-dd-" + (++ddCount);
    var isFilter = select.hasAttribute("data-filter") || !!select.closest("[data-filter-form], .sa-controls, .sa-rep-filters");
    var wrap = document.createElement("div");
    wrap.className = "sa-dd" + (isFilter ? "" : " sa-dd--field") + (select.classList.contains("is-invalid") ? " is-invalid" : "");
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("sa-dd-native");
    select.setAttribute("tabindex", "-1");
    select.setAttribute("aria-hidden", "true");

    var label = select.id ? document.querySelector("label[for='" + select.id + "']") : null;
    var labelText = select.getAttribute("data-label") || (isFilter && label ? label.textContent.trim() : "");
    if (label && select.id) {
      label.setAttribute("for", id);
      label.id = label.id || id + "-label";
    }

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.id = id;
    trigger.className = "sa-dd-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", id + "-menu");
    if (label) trigger.setAttribute("aria-labelledby", label.id + " " + id);
    var describedBy = select.getAttribute("aria-describedby");
    if (describedBy) trigger.setAttribute("aria-describedby", describedBy);
    if (select.getAttribute("aria-invalid") === "true") trigger.setAttribute("aria-invalid", "true");
    trigger.innerHTML = (labelText ? '<span class="sa-dd-label"></span>' : "") +
      '<span class="sa-dd-value"></span><svg class="sa-i sa-dd-caret" aria-hidden="true" focusable="false"><use href="#i-chevron"/></svg>';
    if (labelText) trigger.querySelector(".sa-dd-label").textContent = labelText + ":";
    wrap.appendChild(trigger);

    var menu = document.createElement("ul");
    menu.className = "sa-pop-panel sa-dd-menu";
    menu.id = id + "-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;
    if (label) menu.setAttribute("aria-labelledby", label.id);
    wrap.appendChild(menu);

    var focused = -1;
    function options() { return Array.prototype.slice.call(select.options); }
    function build() {
      menu.innerHTML = "";
      var lastGroup = null;
      options().forEach(function (option, index) {
        // A required field's empty placeholder ("Choose a category") is shown on the trigger, not offered as a choice.
        if (!isFilter && select.required && option.value === "") return;
        var group = option.parentNode.tagName === "OPTGROUP" ? option.parentNode : null;
        if (group && group !== lastGroup) {
          var head = document.createElement("li");
          head.className = "sa-dd-group";
          head.setAttribute("role", "presentation");
          head.textContent = group.label;
          menu.appendChild(head);
        }
        lastGroup = group;
        var item = document.createElement("li");
        item.className = "sa-dd-item";
        item.id = id + "-o" + index;
        item.setAttribute("role", "option");
        item.dataset.index = String(index);
        if (option.disabled) item.setAttribute("aria-disabled", "true");
        item.innerHTML = '<span></span><svg class="sa-i sa-dd-check" aria-hidden="true" focusable="false"><use href="#i-check"/></svg>';
        item.firstChild.textContent = option.textContent.trim();
        menu.appendChild(item);
      });
      sync();
    }
    function sync() {
      var selected = select.options[select.selectedIndex];
      var value = trigger.querySelector(".sa-dd-value");
      value.textContent = selected ? optionText(selected) : "";
      var empty = !selected || selected.value === "";
      trigger.classList.toggle("is-placeholder", empty && !isFilter);
      trigger.classList.toggle("is-active", isFilter && !empty);
      trigger.disabled = select.disabled;
      each(".sa-dd-item", function (item) {
        var on = Number(item.dataset.index) === select.selectedIndex;
        item.classList.toggle("is-selected", on);
        item.setAttribute("aria-selected", String(on));
      }, menu);
    }
    function items() { return Array.prototype.slice.call(menu.querySelectorAll(".sa-dd-item:not([aria-disabled='true'])")); }
    function focusItem(index) {
      var list = items();
      if (!list.length) return;
      focused = Math.max(0, Math.min(index, list.length - 1));
      list.forEach(function (item, i) { item.classList.toggle("is-focused", i === focused); });
      trigger.setAttribute("aria-activedescendant", list[focused].id);
      list[focused].scrollIntoView({ block: "nearest" });
    }
    function open() {
      if (select.disabled) return;
      each(".sa-dd.is-open", function (other) { if (other !== wrap && other._close) other._close(); });
      each("details.sa-pop[open]", function (details) { details.open = false; });
      menu.hidden = false;
      wrap.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      var list = items();
      var current = list.findIndex(function (item) { return Number(item.dataset.index) === select.selectedIndex; });
      focusItem(current < 0 ? 0 : current);
    }
    function close(restore) {
      menu.hidden = true;
      wrap.classList.remove("is-open");
      trigger.setAttribute("aria-expanded", "false");
      trigger.removeAttribute("aria-activedescendant");
      if (restore) trigger.focus();
    }
    wrap._close = function () { close(false); };
    function choose(item) {
      if (!item || item.getAttribute("aria-disabled") === "true") return;
      var index = Number(item.dataset.index);
      var changed = index !== select.selectedIndex;
      select.selectedIndex = index;
      sync();
      close(true);
      if (changed) {
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
        if (select.hasAttribute("data-autosubmit") && select.form) {
          if (select.form.requestSubmit) select.form.requestSubmit(); else select.form.submit();
        }
      }
    }
    var typed = "", typedAt = 0;
    trigger.addEventListener("click", function () { if (menu.hidden) open(); else close(true); });
    trigger.addEventListener("keydown", function (event) {
      var list = items();
      if (menu.hidden) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
        return;
      }
      if (event.key === "ArrowDown") { event.preventDefault(); focusItem(focused + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); focusItem(focused - 1); }
      else if (event.key === "Home") { event.preventDefault(); focusItem(0); }
      else if (event.key === "End") { event.preventDefault(); focusItem(list.length - 1); }
      else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(list[focused]); }
      else if (event.key === "Escape") { event.preventDefault(); close(true); }
      else if (event.key === "Tab") { close(false); }
      else if (event.key.length === 1 && /\S/.test(event.key)) {
        var now = Date.now();
        typed = now - typedAt > 700 ? event.key.toLowerCase() : typed + event.key.toLowerCase();
        typedAt = now;
        var match = list.findIndex(function (item) { return item.textContent.trim().toLowerCase().indexOf(typed) === 0; });
        if (match >= 0) focusItem(match);
      }
    });
    menu.addEventListener("mousedown", function (event) { event.preventDefault(); }); // keep focus on the trigger
    menu.addEventListener("click", function (event) { choose(event.target.closest(".sa-dd-item")); });
    document.addEventListener("click", function (event) { if (!wrap.contains(event.target) && !menu.hidden) close(false); });
    select.addEventListener("change", sync);
    // Options added or removed by another script (for example the subcategory list) rebuild the menu.
    new MutationObserver(build).observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    select._dd = { sync: sync, build: build };
    build();
  }
  each("select.form-select, select[data-dropdown]", enhanceSelect);
  // A select inside an auto-submitting filter form submits on change (works with the dropdown too).
  each("[data-filter-form] select", function (select) { select.setAttribute("data-autosubmit", ""); });

  // --- Segmented controls: the highlight slides to the chosen option ---------------------------
  function initSeg(group) {
    if (group._seg) { group._seg(); return; }
    var thumb = document.createElement("span");
    thumb.className = "sa-seg-thumb";
    thumb.setAttribute("aria-hidden", "true");
    group.appendChild(thumb);
    group.classList.add("has-thumb", "is-init");
    function active() {
      var input = group.querySelector("input:checked");
      if (input) return input.closest("label");
      return group.querySelector("[aria-pressed='true'], [aria-current]");
    }
    function place() {
      var item = active();
      if (!item || !item.offsetWidth) { thumb.style.opacity = "0"; return; }
      thumb.style.opacity = "1";
      thumb.style.setProperty("--x", item.offsetLeft + "px");
      thumb.style.setProperty("--w", item.offsetWidth + "px");
    }
    group._seg = place;
    place();
    window.requestAnimationFrame(function () { group.classList.remove("is-init"); });
    group.addEventListener("change", function () {
      place();
      if (group.hasAttribute("data-autosubmit")) {
        var form = group.closest("form");
        if (form) { if (form.requestSubmit) form.requestSubmit(); else form.submit(); }
      }
    });
    group.addEventListener("click", function () { window.requestAnimationFrame(place); });
    if (window.ResizeObserver) new ResizeObserver(place).observe(group);
  }
  each("[data-seg]", initSeg);

  // --- List / Cards toggle, remembered per page ------------------------------------------------
  each("[data-view-toggle]", function (group) {
    var key = group.getAttribute("data-view-toggle");
    var collections = document.querySelectorAll('[data-view-key="' + key + '"]');
    if (!collections.length) return;
    function apply(view, animate) {
      Array.prototype.forEach.call(collections, function (collection) {
        collection.setAttribute("data-view", view);
        if (animate && !REDUCED.matches) {
          collection.classList.remove("is-switching");
          void collection.offsetWidth; // restart the crossfade
          collection.classList.add("is-switching");
        }
      });
      Array.prototype.forEach.call(group.querySelectorAll("[data-view-choice]"), function (button) {
        button.setAttribute("aria-pressed", String(button.getAttribute("data-view-choice") === view));
      });
      if (group._seg) group._seg();
      // "3 | 4 per row" only matters for cards.
      var perRow = document.querySelector('[data-per-row-toggle="' + key + '"]');
      if (perRow) {
        perRow.hidden = view !== "cards";
        if (perRow._seg) perRow._seg();
      }
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

  // --- Cards per row (3 | 4), remembered per page ----------------------------------------------
  each("[data-per-row-toggle]", function (group) {
    var key = group.getAttribute("data-per-row-toggle");
    var collections = document.querySelectorAll('[data-view-key="' + key + '"]');
    function apply(count) {
      Array.prototype.forEach.call(collections, function (collection) { collection.setAttribute("data-per-row", count); });
      Array.prototype.forEach.call(group.querySelectorAll("[data-per-row-choice]"), function (button) {
        button.setAttribute("aria-pressed", String(button.getAttribute("data-per-row-choice") === count));
      });
      if (group._seg) group._seg();
    }
    var saved = read("sa-perrow-" + key);
    if (saved === "3" || saved === "4") apply(saved);
    group.addEventListener("click", function (event) {
      var button = event.target.closest("[data-per-row-choice]");
      if (!button) return;
      var count = button.getAttribute("data-per-row-choice");
      write("sa-perrow-" + key, count);
      apply(count);
    });
  });

  // --- Copy a reference ([data-copy]): the button's tooltip says "Copied" for a moment ----------
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button || !navigator.clipboard) return;
    navigator.clipboard.writeText(button.getAttribute("data-copy")).then(function () {
      var tip = button.getAttribute("data-tip");
      button.setAttribute("data-tip", "Copied");
      window.setTimeout(function () { button.setAttribute("data-tip", tip || "Copy"); }, 1600);
    });
  });

  // --- Meetings: List | Month | Week, remembered -----------------------------------------------
  var switcher = document.querySelector("[data-meeting-views]");
  if (switcher) {
    var activeView = switcher.getAttribute("data-meeting-views");
    var explicit = /[?&]view=list\b/.test(window.location.search);
    var savedView = read("sa-meetings-view");
    if (activeView === "list" && !explicit && !window.location.search && (savedView === "month" || savedView === "week")) {
      var target = switcher.querySelector('[data-view-name="' + savedView + '"]');
      if (target) window.location.replace(target.href);
    } else {
      write("sa-meetings-view", activeView);
    }
  }

  // --- Dialogs: native <dialog>; Esc and the backdrop close; focus moves in and back -----------
  var dialogOpener = null;
  function openDialog(dialog, opener) {
    if (!dialog || !dialog.showModal) return;
    dialogOpener = opener || document.activeElement;
    dialog.showModal();
    var first = dialog.querySelector("[autofocus], input:not([type='hidden']):not([disabled]), select, textarea, button:not([data-dialog-close])");
    if (first) first.focus();
  }
  each("[data-dialog-open]", function (button) {
    button.addEventListener("click", function () {
      openDialog(document.getElementById(button.getAttribute("data-dialog-open")), button);
    });
  });
  each("dialog.sa-dialog", function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog || event.target.closest("[data-dialog-close]")) dialog.close();
    });
    dialog.addEventListener("close", function () {
      if (dialogOpener && document.contains(dialogOpener)) dialogOpener.focus();
      dialogOpener = null;
    });
    // showModal() makes the rest of the page inert; Tab also wraps inside the dialog.
    dialog.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var focusable = Array.prototype.filter.call(
        dialog.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]):not([type='hidden']), select:not([disabled]):not(.sa-dd-native), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"),
        function (el) { return el.offsetParent !== null; }
      );
      if (!focusable.length) return;
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    // A form returned with errors reopens its dialog.
    if (dialog.hasAttribute("data-open-on-load")) openDialog(dialog, null);
  });

  // --- Toasts: about 4s, paused on hover or focus, × closes ------------------------------------
  each("[data-toast]", function (toast, index) {
    var remaining = 4000 + index * 600, started = 0, timer = null;
    function leave() {
      window.clearTimeout(timer);
      if (REDUCED.matches) { toast.remove(); return; }
      toast.classList.add("is-leaving");
      window.setTimeout(function () { toast.remove(); }, 200);
    }
    function run() { started = Date.now(); timer = window.setTimeout(leave, remaining); }
    function pause() { window.clearTimeout(timer); remaining -= Date.now() - started; }
    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("mouseleave", run);
    toast.addEventListener("focusin", pause);
    toast.addEventListener("focusout", run);
    var close = toast.querySelector("[data-toast-close]");
    if (close) close.addEventListener("click", leave);
    run();
  });

  // --- Bell: the badge pops when the count changes; "Mark all read" without leaving the page ---
  var bell = document.querySelector("[data-bell]");
  if (bell) {
    var unread = bell.getAttribute("data-unread");
    var badge = bell.querySelector("[data-bell-badge]");
    var seen = null;
    try { seen = window.sessionStorage.getItem("sa-unread"); } catch (error) { /* not stored */ }
    if (badge && seen !== null && seen !== unread && !REDUCED.matches) badge.classList.add("is-pop");
    try { window.sessionStorage.setItem("sa-unread", unread); } catch (error) { /* not stored */ }
    var markAll = bell.querySelector("[data-mark-all]");
    if (markAll && window.fetch) {
      markAll.addEventListener("submit", function (event) {
        event.preventDefault();
        window.fetch(markAll.action, {
          method: "POST",
          headers: { "Accept": "application/json", "X-CSRFToken": csrf(markAll) },
          body: new FormData(markAll),
          credentials: "same-origin"
        }).then(function (response) {
          if (!response.ok) throw new Error(response.status);
          each(".is-unread", function (item) { item.classList.remove("is-unread"); }, bell);
          each(".visually-hidden", function (el) { if (el.textContent === "Unread: ") el.remove(); }, bell);
          if (badge) badge.remove();
          markAll.remove();
          bell.querySelector("summary").setAttribute("aria-label", "Notifications, none unread");
          try { window.sessionStorage.setItem("sa-unread", "0"); } catch (error) { /* not stored */ }
        }).catch(function () { markAll.submit(); });
      });
    }
  }

  // --- Count-up and fill -----------------------------------------------------------------------
  var numberFormat = window.Intl ? new Intl.NumberFormat() : null;
  function format(value) { return numberFormat ? numberFormat.format(value) : String(value); }
  each("[data-countup]", function (el) {
    var end = parseInt(el.getAttribute("data-countup"), 10);
    if (isNaN(end) || String(end) !== el.textContent.trim().replace(/[,\s]/g, "")) return; // only plain integers
    el.textContent = format(end);
    if (REDUCED.matches || end === 0) return;
    var start = null, duration = 600;
    el.textContent = format(0);
    function step(now) {
      if (start === null) start = now;
      var t = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = format(Math.round(end * eased));
      if (t < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  });
  each("[data-fill]", function (el) {
    var value = parseFloat(el.getAttribute("data-fill"));
    if (!isNaN(value) && !el.style.getPropertyValue("--fill")) el.style.setProperty("--fill", String(Math.max(0, Math.min(1, value))));
  });

  // --- "Not ready" primary buttons: grey until the form is valid -------------------------------
  each("[data-requires-valid]", function (button) {
    var form = button.form || button.closest("form");
    if (!form) return;
    function check() { button.classList.toggle("is-not-ready", !form.checkValidity()); }
    form.addEventListener("input", check);
    form.addEventListener("change", check);
    check();
  });

  // --- Sticky side panel taller than the window: it sticks by its bottom edge ------------------
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
