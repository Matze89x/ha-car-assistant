// "More" on a wide screen (where the list stands next to the page, the same 1000 px as in pc-core.css) opens the first page (the vehicle passport) at once;
// on a phone and on a narrower tablet it shows the list - the page alone would have no way back to it.
(function () {
  if (!window.matchMedia || !window.matchMedia("(min-width: 1000px)").matches) { return; }
  var a = document.querySelector(".more-main .cur-txt");
  if (a && a.getAttribute("href")) { location.replace(a.getAttribute("href")); }
})();
