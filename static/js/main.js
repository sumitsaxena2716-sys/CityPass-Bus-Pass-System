document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.primary-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      toggle.setAttribute('aria-label', open ? 'Open navigation menu' : 'Close navigation menu');
      nav.classList.toggle('is-open', !open);
    });
    nav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
      nav.classList.remove('is-open'); toggle.setAttribute('aria-expanded', 'false');
    }));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { nav.classList.remove('is-open'); toggle.setAttribute('aria-expanded', 'false'); } });
  }
  document.querySelectorAll('.flash-close').forEach(b => b.addEventListener('click', () => b.closest('.flash')?.remove()));
  const year = document.getElementById('copyright-year'); if (year) year.textContent = String(new Date().getFullYear());
  const back = document.querySelector('.history-back'); if (back) back.addEventListener('click', () => history.length > 1 ? history.back() : location.assign('/'));
  const date = document.getElementById('start_date'); if (date) { const d = new Date(); const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); date.min = local; if (!date.value) date.value = local; }
});
