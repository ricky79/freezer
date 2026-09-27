// Date come stringhe 'YYYY-MM-DD' nel calendario locale. Stessa regola di freezer/expiry.py.
// Mai new Date('YYYY-MM-DD'): verrebbe letta come UTC e la scadenza potrebbe slittare di un giorno.

const pad = (n) => String(n).padStart(2, '0');

export function todayIso(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function dayNumber(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d) / 86400000;
}

export function daysLeft(expiryIso, today) {
  return dayNumber(expiryIso) - dayNumber(today);
}

export function expiryStatus(expiryIso, today, warnDays) {
  const days = daysLeft(expiryIso, today);
  if (days < 0) return 'expired';
  if (days <= warnDays) return 'expiring';
  return 'ok';
}

export function expiryText(expiryIso, today) {
  const days = daysLeft(expiryIso, today);
  if (days < -1) return `scaduto da ${-days} giorni`;
  if (days === -1) return 'scaduto ieri';
  if (days === 0) return 'oggi';
  if (days === 1) return 'domani';
  return `tra ${days} giorni`;
}

export function countAlerts(lots, today, warnDays) {
  const counts = { expired: 0, expiring: 0 };
  for (const lot of lots) {
    const status = expiryStatus(lot.expiry, today, warnDays);
    if (status !== 'ok') counts[status] += 1;
  }
  return counts;
}

export function formatDayMonth(iso) {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
}

export function formatDate(iso) {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

export function addMonths(iso, months) {
  const [y, m, d] = iso.split('-').map(Number);
  const first = new Date(Date.UTC(y, m - 1 + months, 1));
  const year = first.getUTCFullYear();
  const month = first.getUTCMonth();
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return `${year}-${pad(month + 1)}-${pad(Math.min(d, lastDay))}`;
}
