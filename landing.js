(function () {
  "use strict";
  var forms = document.querySelectorAll("[data-launch-signup]");
  var year = document.querySelector("[data-launch-year]");
  if (year) year.textContent = String(new Date().getFullYear());
  if (!forms.length) return;
  var apiBase = /(^|\.)thefloridasignal\.com$/i.test(window.location.hostname) ? "https://api.thefloridasignal.com" : "";
  forms.forEach(function (form) {
    var message = form.querySelector("[data-launch-message]");
    var button = form.querySelector("button[type='submit']");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var email = form.elements.email.value.trim();
      var zip = form.elements.zip ? form.elements.zip.value.trim() : "";
      message.classList.remove("is-error");
      message.textContent = "Saving your place…";
      button.disabled = true;
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
        form.reset();
      } catch (error) {
        message.classList.add("is-error");
        message.textContent = error.message || "Signup is unavailable. Email desk@thefloridasignal.com.";
      } finally {
        button.disabled = false;
      }
    });
  });
}());
