(function () {
  "use strict";

  var mount = document.getElementById("desk-shell");
  if (!mount) return;

  var current = String(mount.dataset.current || "home");
  var labels = {
    home: "Live Desk",
    agenda: "Agenda Watch",
    editorial: "Brief",
    data: "Data Explorer",
    review: "Triage"
  };
  if (!labels[current]) current = "home";

  var links = [
    ["home", "/", "Live Desk", "Today"],
    ["agenda", "/agenda.html", "Agenda Watch", "Early"],
    ["editorial", "/index.html", "Brief", "Draft"],
    ["data", "/data.html", "Data Explorer", "Search"],
    ["review", "/review.html", "Triage", "Decide"]
  ];

  function navLinks(className) {
    return '<nav class="' + className + '" aria-label="Florida Signal Newsroom">' + links.map(function (link) {
      var active = current === link[0] ? ' aria-current="page"' : '';
      return '<a href="' + link[1] + '"' + active + '><span>' + link[2] + '</span>' +
        (className === "dw-side-nav" ? '<small>' + link[3] + '</small>' : '') + '</a>';
    }).join("") + '</nav>';
  }

  mount.innerHTML =
    '<a class="dw-skip" href="#main-content">Skip to workspace</a>' +
    '<header class="dw-shell">' +
      '<div class="dw-shell__top">' +
        '<a class="dw-brand" href="/" aria-label="Florida Signal Newsroom — Live Desk home">' +
          '<img src="/mark-full-color.png" alt="" width="44" height="44">' +
          '<span class="dw-brand__words"><span class="dw-brand__name">FLORIDA SIGNAL</span>' +
          '<span class="dw-brand__desk">Newsroom</span></span>' +
        '</a>' +
        '<button class="dw-search-toggle" type="button" aria-expanded="false" aria-controls="dw-global-search">Search</button>' +
        '<form class="dw-global-search" id="dw-global-search" action="/data.html">' +
          '<label hidden for="dw-global-search-input">Search newsroom records</label>' +
          '<input id="dw-global-search-input" name="search" type="search" placeholder="Search permits, folios, instruments or addresses" autocomplete="off">' +
          '<button type="submit">Go</button>' +
        '</form>' +
        '<button class="dw-status-button" type="button" data-status-open aria-haspopup="dialog"><span class="dw-status-dot"></span><span data-status-label>Checking source clocks</span></button>' +
        '<span class="dw-private-chip">Private newsroom</span>' +
        navLinks("dw-mobile-tabs") +
      '</div>' +
    '</header>' +
    '<aside class="dw-sidebar" aria-label="Newsroom sections">' +
      '<p class="dw-nav-label">Workspace</p>' + navLinks("dw-side-nav") +
      '<div class="dw-sidebar__rule"></div>' +
      '<p class="dw-sidebar__note"><b>Record → Candidate → Signal → Story</b><br>Nothing becomes public without a human editor and source proof.</p>' +
      '<a class="dw-sidebar__public" href="https://thefloridasignal.com" target="_blank" rel="noopener"><span>PUBLIC FLORIDA SIGNAL</span><span>↗</span></a>' +
    '</aside>' +
    '<section class="dw-pipeline" aria-label="Upcoming newsroom pipeline"><div class="dw-pipeline__inner">' +
      '<span class="dw-pipeline__title">Next in pipeline</span>' +
      '<div class="dw-pipeline__jobs" data-pipeline-jobs><span class="dw-pipeline__loading">Checking production schedule…</span></div>' +
    '</div></section>' +
    '<dialog class="dw-status-dialog" data-status-dialog aria-labelledby="dw-status-title">' +
      '<div class="dw-status-head"><div><p>Source receipts and independent clocks</p><h2 id="dw-status-title">Newsroom source status</h2></div><button class="dw-status-close" type="button" data-status-close aria-label="Close source status">×</button></div>' +
      '<div class="dw-status-body" data-status-body><p>Checking each monitored source lane. No freshness state will be inferred from a timer alone.</p></div>' +
    '</dialog>';

  document.body.classList.add("dw-newsroom-ready");

  var token = "";
  var tokenPromise = null;
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }
  function clock(value) {
    if (value == null || value === "" || value === 0 || value === "0") return "not exposed";
    var date = new Date(value);
    return Number.isNaN(date.getTime()) || date.getFullYear() < 2000 ? "not exposed" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  function dateTime(value) {
    if (value == null || value === "" || value === 0 || value === "0") return "not exposed";
    var date = new Date(value);
    return Number.isNaN(date.getTime()) || date.getFullYear() < 2000 ? "not exposed" : date.toLocaleString();
  }
  async function getToken() {
    if (token) return token;
    if (tokenPromise) return tokenPromise;
    tokenPromise = (async function () {
      try {
        var response = await fetch("/api/local-session");
        if (response.ok) token = (await response.json()).token || "";
      } catch (error) {}
      if (!token) token = window.prompt("Private newsroom token") || "";
      tokenPromise = null;
      return token;
    })();
    return tokenPromise;
  }
  async function admin(path, options) {
    var opts = options || {};
    var headers = Object.assign({}, opts.headers || {}, { Authorization: "Bearer " + await getToken() });
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    var response = await fetch(path, Object.assign({}, opts, { headers: headers }));
    var body = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(body.error || "Request unavailable");
    return body;
  }

  async function loadPipeline() {
    var target = mount.querySelector("[data-pipeline-jobs]");
    try {
      var body = await admin("/api/admin/pipeline-schedule");
      var now = Date.now();
      var jobs = (Array.isArray(body.jobs) ? body.jobs : []).filter(function (job) {
        return new Date(job.next_at).getTime() >= now - 60000;
      }).slice(0, 5);
      target.innerHTML = jobs.length ? jobs.map(function (job, index) {
        return '<span class="dw-pipeline__job' + (index === 0 ? ' is-next' : '') + '"><b>' + esc(clock(job.next_at)) + '</b> ' + esc(job.label) + '</span>';
      }).join("") : '<span class="dw-pipeline__loading">No upcoming production timer was reported.</span>';
      target.title = body.contract || "A timer proves scheduling only; source clocks prove usable data.";
    } catch (error) {
      target.innerHTML = '<span class="dw-pipeline__loading">Schedule unavailable — no run inferred.</span>';
    }
  }

  async function loadStatus() {
    var label = mount.querySelector("[data-status-label]");
    var target = mount.querySelector("[data-status-body]");
    try {
      var responses = await Promise.all([
        admin("/api/admin/early-intel"),
        admin("/api/admin/signal-machine").catch(function () { return null; })
      ]);
      var body = responses[0];
      var machine = responses[1];
      var lanes = Array.isArray(body.lanes) ? body.lanes : [];
      var scored = machine && Array.isArray(machine.lanes) ? machine.lanes.filter(function (lane) { return lane.coverage === "shadow_ranked"; }).length : null;
      label.textContent = lanes.length + " lane" + (lanes.length === 1 ? "" : "s") + " ingesting · " + (scored == null ? "scoring status unavailable" : scored + " shadow-scored");
      target.innerHTML = lanes.length ? lanes.map(function (lane) {
        return '<article class="dw-source-row"><span class="dw-source-stage">' + esc(lane.phase || "—") + '</span><div><b>' + esc(lane.label || "Unnamed source") + '</b><p>' + esc(lane.headline || lane.note || "No source note exposed.") + '</p></div><span class="dw-source-clock">Event ' + esc(lane.event_through || "not exposed") + '<br>System ' + esc(dateTime(lane.system_time)) + '</span></article>';
      }).join("") : '<p>No monitored lane responded. No source state was inferred.</p>';
    } catch (error) {
      label.textContent = "Source status unavailable";
      target.innerHTML = '<p>Source status could not be opened. No freshness state was inferred.</p>';
    }
  }

  var searchToggle = mount.querySelector(".dw-search-toggle");
  var search = mount.querySelector(".dw-global-search");
  searchToggle.addEventListener("click", function () {
    var open = !search.classList.contains("is-open");
    search.classList.toggle("is-open", open);
    searchToggle.setAttribute("aria-expanded", String(open));
    if (open) search.querySelector("input").focus();
  });

  var dialog = mount.querySelector("[data-status-dialog]");
  mount.querySelector("[data-status-open]").addEventListener("click", function () { dialog.showModal(); });
  mount.querySelector("[data-status-close]").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("click", function (event) { if (event.target === dialog) dialog.close(); });

  window.FloridaSignalNewsroom = { getToken: getToken, admin: admin, refreshStatus: loadStatus };
  loadPipeline();
  loadStatus();
  window.setInterval(loadPipeline, 60000);
})();
