(function () {
  "use strict";
  var forms = document.querySelectorAll("[data-launch-signup]");
  var year = document.querySelector("[data-launch-year]");
  if (year) year.textContent = String(new Date().getFullYear());
  var apiBase = /(^|\.)thefloridasignal\.com$/i.test(window.location.hostname) ? "https://api.thefloridasignal.com" : "";

  function analyticsSessionId() {
    try {
      var sessionId = window.sessionStorage.getItem("florida-signal-analytics-session");
      if (!sessionId) {
        sessionId = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : "fs-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
        window.sessionStorage.setItem("florida-signal-analytics-session", sessionId);
      }
      return sessionId;
    } catch (error) {
      return "";
    }
  }

  function trackEvent(name, properties) {
    var cleanProperties = properties || {};
    var payload = JSON.stringify({
      event: name,
      page: window.location.pathname,
      session_id: analyticsSessionId(),
      properties: Object.assign({ device: window.matchMedia("(max-width: 620px)").matches ? "mobile" : "desktop" }, cleanProperties)
    });
    if (window.dataLayer && Array.isArray(window.dataLayer)) window.dataLayer.push(Object.assign({ event: name }, cleanProperties));
    try {
      fetch(apiBase + "/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
        credentials: "omit"
      }).catch(function () { /* Analytics are best-effort and never block signup. */ });
    } catch (error) { /* Analytics must never block the product. */ }
  }

  window.floridaSignalTrack = trackEvent;
  trackEvent("page_view", { page_name: "newsletter_landing" });
  if (!forms.length) return;

  forms.forEach(function (form) {
    var message = form.querySelector("[data-launch-message]");
    var button = form.querySelector("button[type='submit']");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var email = form.elements.email.value.trim();
      var zip = form.elements.zip ? form.elements.zip.value.trim() : "";
      var placement = form.classList.contains("launch-signup--final") ? "final-cta" : "hero";
      message.classList.remove("is-error");
      message.textContent = "Saving your place…";
      button.disabled = true;
      trackEvent("newsletter_submit", { placement: placement });
      try {
        var response = await fetch(apiBase + "/api/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: email,
            zip: zip,
            cities: ["fort-lauderdale"],
            interests: ["development", "neighborhoods", "meetings", "property", "liens", "storm"],
            source: "florida-signal-brief-launch"
          })
        });
        var data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not save your signup.");
        message.textContent = data.existing ? "You’re already on the list." : "You’re in. Watch for the next brief.";
        trackEvent("newsletter_conversion", { placement: placement, status: data.existing ? "existing" : "created" });
        form.reset();
      } catch (error) {
        message.classList.add("is-error");
        message.textContent = error.message || "Signup is unavailable. Email desk@thefloridasignal.com.";
        trackEvent("newsletter_error", { placement: placement, status: "api_error" });
      } finally {
        button.disabled = false;
      }
    });
  });
}());
