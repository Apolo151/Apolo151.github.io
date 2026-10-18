(function () {
  var root = document.documentElement;
  function stored() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
  function initial() {
    var t = stored();
    if (t === "dark" || t === "light") return t;
    try {
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
    } catch (e) {}
    return "dark";
  }
  function apply(t) {
    root.setAttribute("data-theme", t);
    var b = document.getElementById("theme-toggle");
    if (b) b.setAttribute("aria-pressed", t === "light" ? "true" : "false");
  }
  apply(initial());
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("#theme-toggle");
    if (!b) return;
    var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    apply(next);
    try { localStorage.setItem("theme", next); } catch (err) {}
  });
  document.addEventListener("DOMContentLoaded", function () { apply(root.getAttribute("data-theme")); });
})();
