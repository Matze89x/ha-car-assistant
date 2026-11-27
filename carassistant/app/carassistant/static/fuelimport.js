/* The import of fill-ups from a CSV file (fuelimport_web.py): the example under the choice of a column follows the choice. */
(function () {
  document.addEventListener('change', function (e) {
    var select = e.target;
    if (!select || !select.matches || !select.matches('select[data-sample-for]')) { return; }
    var out = document.getElementById(select.getAttribute('data-sample-for')), option = select.options[select.selectedIndex];
    if (out) { out.textContent = (option && option.getAttribute('data-sample')) || ''; }
  });
})();
