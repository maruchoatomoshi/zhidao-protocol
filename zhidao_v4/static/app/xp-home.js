/* Opt-in style review. No persistent setting, identity access or API calls. */
(function () {
  "use strict";
  if (new URLSearchParams(window.location.search).get("design") === "xp") {
    document.documentElement.dataset.design = "xp";
  }
}());
