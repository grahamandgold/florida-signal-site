(function () {
  "use strict";
  var forms = document.querySelectorAll("[data-launch-signup]");
  var year = document.querySelector("[data-launch-year]");
  if (year) year.textContent = String(new Date().getFullYear());
  var apiBase = /(^|\.)thefloridasignal\.com$/i.test(window.location.hostname) ? "https://api.thefloridasignal.com" : "";
  var UTM_STORAGE_KEY = "florida-signal-utm";
  var UTM_TTL_MS = 30 * 24 * 60 * 60 * 1000;
  // Official first-touch scheme. Clickable links only — never About text.
  // Company page is already tagged — do not change it.
  // Profile featured: ?utm_source=linkedin&utm_medium=profile&utm_campaign=featured
  // LinkedIn post:    ?utm_source=linkedin&utm_medium=post&utm_campaign=20260825-galleria
  // LinkedIn DM:      ?utm_source=linkedin&utm_medium=dm&utm_campaign=warm102
  // Email forward:    ?utm_source=email&utm_medium=forward&utm_campaign=referral
  // Do not use utm_campaign=about — About is not clickable on LinkedIn.
  var FORWARD_URL = "https://thefloridasignal.com/?utm_source=email&utm_medium=forward&utm_campaign=referral";

  function readQueryUtms() {
    var params = new URLSearchParams(window.location.search);
    var utm = {
      utm_source: (params.get("utm_source") || "").trim(),
      utm_medium: (params.get("utm_medium") || "").trim(),
      utm_campaign: (params.get("utm_campaign") || "").trim()
    };
    if (!utm.utm_source && !utm.utm_medium && !utm.utm_campaign) return null;
    return utm;
  }

  function firstTouchUtms() {
    var incoming = readQueryUtms();
    var now = Date.now();
    try {
      var stored = window.localStorage.getItem(UTM_STORAGE_KEY);
      if (stored) {
        var parsed = JSON.parse(stored);
        var age = now - (parsed && parsed.saved_at ? parsed.saved_at : 0);
        if (parsed && age >= 0 && age < UTM_TTL_MS) {
          return {
            utm_source: parsed.utm_source || "",
            utm_medium: parsed.utm_medium || "",
            utm_campaign: parsed.utm_campaign || ""
          };
        }
        window.localStorage.removeItem(UTM_STORAGE_KEY);
      }
      if (incoming) {
        window.localStorage.setItem(UTM_STORAGE_KEY, JSON.stringify({
          utm_source: incoming.utm_source,
          utm_medium: incoming.utm_medium,
          utm_campaign: incoming.utm_campaign,
          saved_at: now
        }));
        return incoming;
      }
    } catch (error) {
      return incoming;
    }
    return incoming;
  }

  var attribution = firstTouchUtms() || {};

  function fillUtmFields() {
    forms.forEach(function (form) {
      ["utm_source", "utm_medium", "utm_campaign"].forEach(function (name) {
        var field = form.elements[name];
        if (field && attribution[name]) field.value = attribution[name];
      });
    });
  }

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
    var url = apiBase + "/api/events";
    try {
      if (navigator.sendBeacon) {
        var sent = navigator.sendBeacon(url, new Blob([payload], { type: "application/json" }));
        if (sent) return;
      }
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
        credentials: "omit"
      }).catch(function () { /* Analytics are best-effort and never block signup. */ });
    } catch (error) { /* Analytics must never block the product. */ }
  }

  window.floridaSignalTrack = trackEvent;
  fillUtmFields();
  trackEvent("page_view", Object.assign({ page_name: "newsletter_landing" }, attribution));

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
            source: "florida-signal-brief-launch",
            utm_source: (form.elements.utm_source && form.elements.utm_source.value) || attribution.utm_source || "",
            utm_medium: (form.elements.utm_medium && form.elements.utm_medium.value) || attribution.utm_medium || "",
            utm_campaign: (form.elements.utm_campaign && form.elements.utm_campaign.value) || attribution.utm_campaign || ""
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

  var shareUrl = FORWARD_URL;
  var shareTitle = "Florida Signal Brief";
  var shareText = "Know what’s changing across Broward before the headline. Get the Florida Signal Brief.";
  var nativeShare = document.querySelector("[data-native-share]");
  var shareMessage = document.querySelector("[data-share-message]");

  var deskEmail = "desk@thefloridasignal.com";
  var deskMailto = "mailto:desk@thefloridasignal.com?subject=" + encodeURIComponent("Florida Signal");
  var deskGmail = "https://mail.google.com/mail/?view=cm&fs=1&to=" + encodeURIComponent(deskEmail) + "&su=" + encodeURIComponent("Florida Signal");

  function showDeskEmail() {
    if (!shareMessage) return;
    shareMessage.innerHTML = deskEmail + ' · <a href="' + deskGmail + '" target="_blank" rel="noopener noreferrer">Open Gmail</a>';
  }

  document.querySelectorAll("[data-share-method]").forEach(function (control) {
    if (control === nativeShare) return;
    control.addEventListener("click", function (event) {
      var method = control.getAttribute("data-share-method") || "unknown";
      trackEvent("share_click", { method: method });
      if (method !== "email") return;
      event.preventDefault();
      showDeskEmail();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(deskEmail).catch(function () { /* visible address is the fallback */ });
      }
      var prefersNativeMail = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || "");
      if (prefersNativeMail) {
        window.location.href = deskMailto;
        return;
      }
      window.open(deskGmail, "_blank", "noopener,noreferrer");
    });
  });

  if (nativeShare) {
    if (navigator.share) {
      nativeShare.textContent = "Share";
      nativeShare.setAttribute("data-share-method", "native");
      nativeShare.setAttribute("aria-label", "Share Florida Signal");
    }
    nativeShare.addEventListener("click", async function () {
      var method = nativeShare.getAttribute("data-share-method") || "copy";
      if (navigator.share) {
        try {
          await navigator.share({ title: shareTitle, text: shareText, url: shareUrl });
          trackEvent("share_click", { method: "native", status: "shared" });
          return;
        } catch (error) {
          if (error && error.name === "AbortError") return;
        }
      }
      try {
        await navigator.clipboard.writeText(shareUrl);
        shareMessage.textContent = "Link copied.";
        trackEvent("share_click", { method: method === "native" ? "copy_fallback" : "copy", status: "copied" });
      } catch (error) {
        shareMessage.textContent = "Copy this link: " + shareUrl;
        trackEvent("share_click", { method: "copy", status: "manual" });
      }
    });
  }
}());
