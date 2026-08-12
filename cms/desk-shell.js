(function () {
  "use strict";

  var mount = document.getElementById("desk-shell");
  if (!mount) return;

  var current = String(mount.dataset.current || "home");
  var labels = {
    home: "Live Desk",
    data: "Data Explorer",
    review: "Signal Review",
    editorial: "Editorial Desk"
  };
  if (!labels[current]) current = "home";

  var links = [
    ["home", "/", "Live Desk"],
    ["data", "/data.html", "Explore"],
    ["review", "/review.html", "Review"],
    ["editorial", "/index.html", "Write"]
  ];

  mount.innerHTML =
    '<a class="dw-skip" href="#main-content">Skip to workspace</a>' +
    '<header class="dw-shell">' +
      '<div class="dw-shell__top">' +
        '<a class="dw-brand" href="/" aria-label="Florida Signal Data Wire — Live Desk home">' +
          '<img src="/mark-full-color.png" alt="" width="35" height="35">' +
          '<span class="dw-brand__words"><span class="dw-brand__name">FLORIDA SIGNAL</span>' +
          '<span class="dw-brand__desk">Data Wire · ' + labels[current] + '</span></span>' +
        '</a>' +
        '<nav class="dw-nav" aria-label="Data Wire workspace">' + links.map(function (link) {
          var active = current === link[0] ? ' aria-current="page"' : '';
          return '<a href="' + link[1] + '"' + active + '>' + link[2] + '</a>';
        }).join("") + '</nav>' +
        '<span class="dw-connection">Private desk connected</span>' +
      '</div>' +
    '</header>' +
    '<section class="dw-pipeline" aria-label="Upcoming production pipeline"><div class="dw-pipeline__inner">' +
      '<span class="dw-pipeline__title">Next in pipeline</span>' +
      '<div class="dw-pipeline__jobs" data-pipeline-jobs><span class="dw-pipeline__loading">Checking the production schedule…</span></div>' +
      '<a href="/data.html#source-health">Source health</a>' +
    '</div></section>';

  function clock(value) {
    var date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Time unknown" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  async function loadPipeline() {
    var target = mount.querySelector("[data-pipeline-jobs]");
    try {
      var session = await fetch("/api/local-session");
      if (!session.ok) throw new Error("No local session");
      var token = (await session.json()).token || "";
      var response = await fetch("/api/admin/pipeline-schedule", { headers: { "Authorization": "Bearer " + token } });
      var body = await response.json();
      if (!response.ok || !Array.isArray(body.jobs)) throw new Error(body.error || "Schedule unavailable");
      var now = Date.now();
      var jobs = body.jobs.filter(function (job) { return new Date(job.next_at).getTime() >= now - 60000; }).slice(0, 5);
      target.innerHTML = jobs.length ? jobs.map(function (job, index) {
        return '<span class="dw-pipeline__job' + (index === 0 ? ' is-next' : '') + '"><b>' + clock(job.next_at) + '</b> ' + job.label + '</span>';
      }).join("") : '<span class="dw-pipeline__loading">No upcoming production timers reported.</span>';
      target.title = body.contract || "Scheduled time is not proof of source completeness.";
    } catch (error) {
      target.innerHTML = '<span class="dw-pipeline__loading">Schedule unavailable — no run is being inferred.</span>';
    }
  }

  loadPipeline();
  window.setInterval(loadPipeline, 60000);
})();
