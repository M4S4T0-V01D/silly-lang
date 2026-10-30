// Search over search.json, the mobile menu, and copy buttons on code blocks.
(function () {
  const root = document.body.dataset.root || "";
  const q = document.getElementById("q");
  const box = document.getElementById("results");
  let index = null;
  let picked = 0;

  function load() {
    if (index) return Promise.resolve(index);
    return fetch(root + "search.json").then(r => r.json()).then(d => (index = d));
  }

  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  }

  function score(e, terms) {
    const h = e.h.toLowerCase(), p = e.p.toLowerCase(), x = e.x.toLowerCase();
    let s = 0;
    for (const t of terms) {
      let hit = 0;
      if (h === t) hit += 30;
      else if (h.startsWith(t)) hit += 20;
      else if (h.includes(t)) hit += 12;
      if (p.includes(t)) hit += 4;
      if (x.includes(t)) hit += 2;
      if (!hit) return 0;
      s += hit;
    }
    return s - h.length / 100;
  }

  function snippet(x, terms) {
    const lx = x.toLowerCase();
    let at = -1;
    for (const t of terms) { at = lx.indexOf(t); if (at >= 0) break; }
    const start = Math.max(0, at - 40);
    let s = esc((start ? "…" : "") + x.slice(start, start + 140));
    for (const t of terms) {
      if (t.length < 2) continue;
      s = s.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    }
    return s;
  }

  function show() {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { box.hidden = true; return; }
    load().then(idx => {
      const hits = idx.map(e => [score(e, terms), e]).filter(h => h[0] > 0)
        .sort((a, b) => b[0] - a[0]).slice(0, 12);
      picked = 0;
      box.innerHTML = hits.length ? hits.map(([, e], i) =>
        `<a href="${root}${e.u}"${i === 0 ? ' class="picked"' : ""}>` +
        `<b>${esc(e.h)}</b><span class="where">${esc(e.p)}</span>` +
        `<span class="snip">${snippet(e.x, terms)}</span></a>`).join("")
        : '<p class="none">No results</p>';
      box.hidden = false;
    });
  }

  if (q) {
    q.addEventListener("input", show);
    q.addEventListener("focus", () => { load(); if (q.value) show(); });
    q.addEventListener("keydown", e => {
      const links = box.querySelectorAll("a");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!links.length) return;
        links[picked].classList.remove("picked");
        picked = (picked + (e.key === "ArrowDown" ? 1 : links.length - 1)) % links.length;
        links[picked].classList.add("picked");
        links[picked].scrollIntoView({block: "nearest"});
      } else if (e.key === "Enter" && links.length) {
        location.href = links[picked].href;
      } else if (e.key === "Escape") {
        q.value = ""; box.hidden = true; q.blur();
      }
    });
    document.addEventListener("keydown", e => {
      if (e.key === "/" && document.activeElement !== q) { e.preventDefault(); q.focus(); }
    });
    document.addEventListener("click", e => {
      if (!e.target.closest(".search")) box.hidden = true;
    });
  }

  const menu = document.getElementById("menu");
  const side = document.getElementById("sidebar");
  if (menu && side) menu.addEventListener("click", () => side.classList.toggle("open"));
  const active = side && side.querySelector("a.active");
  if (active) side.scrollTop = active.offsetTop - side.clientHeight / 2;

  for (const pre of document.querySelectorAll(".hl pre")) {
    const b = document.createElement("button");
    b.className = "copy";
    b.textContent = "Copy";
    b.addEventListener("click", () => {
      navigator.clipboard.writeText(pre.innerText).then(() => {
        b.textContent = "Copied";
        setTimeout(() => (b.textContent = "Copy"), 1200);
      });
    });
    pre.parentElement.appendChild(b);
  }
})();
