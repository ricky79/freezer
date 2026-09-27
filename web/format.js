export const MAX_QUANTITY = 99999;

export function formatQuantity(quantity, unitCode, catalog) {
  const unit = catalog?.units?.find((u) => u.code === unitCode);
  if (!unit) return String(quantity);
  return `${quantity} ${quantity === 1 ? unit.singular : unit.plural}`;
}

export function categoryLabel(code, catalog) {
  return catalog?.categories?.find((c) => c.code === code)?.label ?? code;
}

export function normalizeText(text) {
  return String(text).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

// Testo di un campo quantità → intero tra 1 e max, oppure null.
export function parseQuantity(text, max = MAX_QUANTITY) {
  const trimmed = String(text ?? '').trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 && value <= max ? value : null;
}
