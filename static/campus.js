const selection = document.getElementById('selection');
if (selection) {
  const refresh = document.getElementById('refresh-plan');
  // Keep the submit button available without JavaScript.
  refresh.hidden = true;
  selection.addEventListener('change', () => selection.requestSubmit());
}

const dayFilter = document.getElementById('day-filter');
if (dayFilter) {
  document.getElementById('day-control').hidden = false;
  dayFilter.addEventListener('change', () => {
    for (const row of document.querySelectorAll('tr[data-day]')) {
      row.hidden = Boolean(dayFilter.value) && row.dataset.day !== dayFilter.value;
    }
  });
}
