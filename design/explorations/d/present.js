// Presentation helper for Design D pages. DEVELOPMENT ONLY.
// - Scales the 1440px desktop iframe to the available width.
// - Switches the typography pairing in every iframe (?type=newsreader|fraunces|sans).
(function () {
  "use strict";
  const frames = Array.from(document.querySelectorAll("iframe[data-src]"));

  function withType(src, type) {
    const url = new URL(src, location.href);
    url.searchParams.set("type", type);
    return url.href;
  }

  function setType(type) {
    for (const f of frames) f.src = withType(f.dataset.src, type);
    for (const b of document.querySelectorAll("[data-type-btn]")) b.setAttribute("aria-pressed", String(b.dataset.typeBtn === type));
    for (const a of document.querySelectorAll("[data-open]")) a.href = withType(a.dataset.open, type);
  }

  function scaleDesks() {
    for (const box of document.querySelectorAll(".d-desk")) {
      const f = box.querySelector("iframe");
      const h = Number(f.dataset.height || 1000);
      const scale = Math.min(1, box.clientWidth / 1440);
      f.style.height = h + "px";
      f.style.transform = `scale(${scale})`;
      box.style.height = Math.round(h * scale) + "px";
    }
  }

  for (const b of document.querySelectorAll("[data-type-btn]")) b.addEventListener("click", () => setType(b.dataset.typeBtn));
  window.addEventListener("resize", scaleDesks);
  setType("newsreader");
  scaleDesks();
})();
