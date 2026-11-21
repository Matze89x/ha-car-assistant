// "More" on a tablet or a wide screen opens the first page (the vehicle passport) at once; the phone shows the list.
(function () {
  if (!window.matchMedia || !window.matchMedia("(min-width: 760px)").matches) { return; }
  var a = document.querySelector(".more-main .cur-txt");
  if (a && a.getAttribute("href")) { location.replace(a.getAttribute("href")); }
})();
