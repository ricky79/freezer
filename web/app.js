import { editOp, makeOp, removeSent, validateLot, viewLots } from './store.js';
import { createSyncer } from './sync.js';
import {
  addMonths, countAlerts, expiryStatus, expiryText, formatDate, formatDayMonth, todayIso,
} from './expiry.js';
import {
  MAX_QUANTITY, categoryLabel, escapeHtml, formatQuantity, normalizeText, parseQuantity,
} from './format.js';
import { persist } from './persist.js';

const KEYS = { snapshot: 'freezer.snapshot', queue: 'freezer.queue', lastSync: 'freezer.lastSync' };
const RETRY_MS = 30000;

const state = {
  snapshot: persist.load(KEYS.snapshot, null),
  queue: persist.load(KEYS.queue, []),
  lastSync: persist.load(KEYS.lastSync, null),
  failed: false,
  search: '',
  category: 'all',
  onlyAlerts: false,
};
if (!Array.isArray(state.queue)) state.queue = [];
if (!state.snapshot || !Array.isArray(state.snapshot.lots)) state.snapshot = null;

let registration = null; // service worker: dopo ogni sync controlla se c'è una versione nuova
let takeLotId = null;
let detailLotId = null;
let editingLot = null;

const $ = (id) => document.getElementById(id);
const catalog = () => state.snapshot?.catalog ?? { categories: [], units: [] };
const warnDays = () => state.snapshot?.warn_days ?? 7;
const currentLots = () => viewLots(state.snapshot?.lots ?? [], state.queue);
const findLot = (id) => currentLots().find((lot) => lot.id === id);
const pad = (n) => String(n).padStart(2, '0');

// ---- Rendering -----------------------------------------------------------

function stamp(iso) {
  const d = new Date(iso);
  return { day: `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

function syncStatusText() {
  const pending = state.queue.length;
  if (pending) {
    const text = pending === 1 ? '⏳ 1 modifica da inviare' : `⏳ ${pending} modifiche da inviare`;
    return state.failed ? `${text} · PC non raggiungibile` : text;
  }
  if (state.failed) {
    if (!state.lastSync) return '⚠ PC non raggiungibile';
    const { day, time } = stamp(state.lastSync);
    return `⚠ PC non raggiungibile · dati del ${day} ${time}`;
  }
  if (state.lastSync) return `✓ Aggiornato alle ${stamp(state.lastSync).time}`;
  return 'Connessione al PC…';
}

function renderBanner(lots, today) {
  const banner = $('alert-banner');
  const { expired, expiring } = countAlerts(lots, today, warnDays());
  if (!expired && !expiring) {
    banner.hidden = true;
    state.onlyAlerts = false;
    return;
  }
  const parts = [];
  if (expired) parts.push(`🔴 ${expired} ${expired === 1 ? 'scaduto' : 'scaduti'}`);
  if (expiring) parts.push(`🟠 ${expiring} in scadenza`);
  banner.hidden = false;
  banner.textContent = parts.join(' · ') + (state.onlyAlerts ? ' — mostra tutto' : '');
  banner.setAttribute('aria-pressed', String(state.onlyAlerts));
}

function renderChips(lots) {
  const present = new Set(lots.map((lot) => lot.category));
  if (state.category !== 'all' && !present.has(state.category)) state.category = 'all';
  const chips = [{ code: 'all', label: 'Tutti' }, ...catalog().categories.filter((c) => present.has(c.code))];
  const nav = $('category-filters');
  nav.hidden = present.size < 2;
  nav.innerHTML = chips
    .map((chip) => `<button type="button" class="chip" data-category="${escapeHtml(chip.code)}" aria-pressed="${chip.code === state.category}">${escapeHtml(chip.label)}</button>`)
    .join('');
}

function lotItem(lot, today) {
  const status = expiryStatus(lot.expiry, today, warnDays());
  const id = escapeHtml(lot.id);
  const meta = [
    formatQuantity(lot.quantity, lot.unit, catalog()),
    expiryText(lot.expiry, today),
    formatDayMonth(lot.expiry),
  ].map(escapeHtml).join(' · ');
  return `<li class="lot lot--${status}">
    <button type="button" class="lot__main" data-action="open" data-id="${id}">
      <span class="lot__desc">${escapeHtml(lot.description)}</span>
      <span class="lot__meta">${meta}</span>
    </button>
    <button type="button" class="lot__take" data-action="take" data-id="${id}">Prendi</button>
  </li>`;
}

function renderList(lots, today) {
  const query = normalizeText(state.search);
  const visible = lots.filter((lot) =>
    (state.category === 'all' || lot.category === state.category)
    && (!state.onlyAlerts || expiryStatus(lot.expiry, today, warnDays()) !== 'ok')
    && (!query || normalizeText(lot.description).includes(query)));
  $('lot-list').innerHTML = visible.map((lot) => lotItem(lot, today)).join('');
  const empty = $('empty');
  empty.hidden = visible.length > 0;
  if (!state.snapshot) empty.textContent = 'Connettiti al Wi-Fi di casa per caricare l\'inventario.';
  else if (!lots.length) empty.textContent = 'Il freezer è vuoto. Tocca «＋ Aggiungi» per registrare qualcosa.';
  else empty.textContent = 'Nessun risultato.';
}

function render() {
  const today = todayIso();
  const lots = currentLots();
  $('sync-status').textContent = syncStatusText();
  $('add-button').disabled = !state.snapshot;
  renderBanner(lots, today);
  renderChips(lots);
  renderList(lots, today);
}

// ---- Coda e sincronizzazione ---------------------------------------------

const syncer = createSyncer({
  getQueue: () => state.queue,
  onSuccess(snapshot, sentIds) {
    state.snapshot = snapshot;
    state.queue = removeSent(state.queue, sentIds);
    state.lastSync = new Date().toISOString();
    state.failed = false;
    persist.save(KEYS.snapshot, state.snapshot);
    persist.save(KEYS.queue, state.queue);
    persist.save(KEYS.lastSync, state.lastSync);
    render();
    registration?.update().catch(() => {});
  },
  onFailure() {
    state.failed = true;
    render();
  },
});

function enqueue(op) {
  state.queue = [...state.queue, op];
  persist.save(KEYS.queue, state.queue);
  render();
  syncer.syncNow();
}

// ---- Dialoghi --------------------------------------------------------------

function showError(id, message) {
  $(id).textContent = message;
  $(id).hidden = false;
}

function hideError(id) {
  $(id).hidden = true;
}

function openTake(id) {
  const lot = findLot(id);
  if (!lot) return;
  takeLotId = id;
  const grams = lot.unit === 'grammi';
  $('take-title').textContent = lot.description;
  $('take-available').textContent = `Disponibili: ${formatQuantity(lot.quantity, lot.unit, catalog())}`;
  $('take-amount').value = grams ? '' : '1';
  $('take-amount').dataset.max = String(lot.quantity);
  $('take-stepper').classList.toggle('is-grams', grams);
  hideError('take-error');
  $('take-dialog').showModal();
  if (grams) $('take-amount').focus();
}

function resetDeleteButton() {
  const button = $('detail-delete');
  delete button.dataset.confirm;
  button.textContent = 'Elimina';
}

function openDetail(id) {
  const lot = findLot(id);
  if (!lot) return;
  detailLotId = id;
  $('detail-title').textContent = lot.description;
  $('detail-info').innerHTML = `
    <dt>Tipo</dt><dd>${escapeHtml(categoryLabel(lot.category, catalog()))}</dd>
    <dt>Quantità</dt><dd>${escapeHtml(formatQuantity(lot.quantity, lot.unit, catalog()))}</dd>
    <dt>Scadenza</dt><dd>${escapeHtml(formatDate(lot.expiry))} (${escapeHtml(expiryText(lot.expiry, todayIso()))})</dd>`;
  resetDeleteButton();
  $('detail-dialog').showModal();
}

function fillSelect(select, options, placeholder) {
  select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`
    + options.map((o) => `<option value="${escapeHtml(o.code)}">${escapeHtml(o.label)}</option>`).join('');
}

function updateQuantityMode() {
  $('f-stepper').classList.toggle('is-grams', $('f-unit').value === 'grammi');
}

function openForm(lot = null) {
  editingLot = lot;
  const { categories, units } = catalog();
  $('form-title').textContent = lot ? 'Modifica' : 'Aggiungi';
  fillSelect($('f-category'), categories, 'Scegli il tipo…');
  fillSelect($('f-unit'), units.map((u) => ({ code: u.code, label: u.plural })), 'Scegli l\'unità…');
  $('suggestions').innerHTML = (state.snapshot?.suggestions ?? [])
    .map((s) => `<option value="${escapeHtml(s.description)}"></option>`).join('');
  $('f-description').value = lot?.description ?? '';
  $('f-category').value = lot?.category ?? '';
  $('f-unit').value = lot?.unit ?? '';
  $('f-quantity').value = lot ? String(lot.quantity) : '1';
  $('f-quantity').dataset.max = String(MAX_QUANTITY);
  $('f-expiry').value = lot?.expiry ?? '';
  updateQuantityMode();
  hideError('form-error');
  $('form-dialog').showModal();
}

// ---- Eventi ----------------------------------------------------------------

$('lot-list').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  if (button.dataset.action === 'take') openTake(button.dataset.id);
  else openDetail(button.dataset.id);
});

$('category-filters').addEventListener('click', (event) => {
  const chip = event.target.closest('[data-category]');
  if (!chip) return;
  state.category = chip.dataset.category;
  render();
});

$('alert-banner').addEventListener('click', () => {
  state.onlyAlerts = !state.onlyAlerts;
  render();
});

$('search').addEventListener('input', (event) => {
  state.search = event.target.value;
  render();
});

$('add-button').addEventListener('click', () => openForm());

document.querySelectorAll('[data-close]').forEach((button) => {
  button.addEventListener('click', () => button.closest('dialog').close());
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-step]');
  if (!button) return;
  const input = $(button.dataset.target);
  const max = Number(input.dataset.max) || MAX_QUANTITY;
  const current = parseQuantity(input.value, MAX_QUANTITY) ?? 0;
  input.value = String(Math.min(max, Math.max(1, current + Number(button.dataset.step))));
});

$('take-all').addEventListener('click', () => {
  const lot = findLot(takeLotId);
  if (lot) $('take-amount').value = String(lot.quantity);
});

$('take-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const lot = findLot(takeLotId);
  if (!lot) {
    $('take-dialog').close();
    return;
  }
  const amount = parseQuantity($('take-amount').value, lot.quantity);
  if (amount === null) {
    showError('take-error', `Scrivi un numero intero tra 1 e ${lot.quantity}.`);
    return;
  }
  $('take-dialog').close();
  enqueue(makeOp('take', { lot_id: lot.id, amount }));
});

$('detail-edit').addEventListener('click', () => {
  const lot = findLot(detailLotId);
  $('detail-dialog').close();
  if (lot) openForm(lot);
});

$('detail-delete').addEventListener('click', () => {
  const button = $('detail-delete');
  if (button.dataset.confirm !== 'yes') {
    button.dataset.confirm = 'yes';
    button.textContent = 'Conferma eliminazione';
    return;
  }
  $('detail-dialog').close();
  if (findLot(detailLotId)) enqueue(makeOp('delete', { lot_id: detailLotId }));
});

$('f-description').addEventListener('input', () => {
  if (editingLot) return;
  const key = normalizeText($('f-description').value);
  const match = (state.snapshot?.suggestions ?? []).find((s) => normalizeText(s.description) === key);
  if (!match) return;
  $('f-category').value = match.category;
  $('f-unit').value = match.unit;
  updateQuantityMode();
});

$('f-unit').addEventListener('change', updateQuantityMode);

$('quick-expiry').addEventListener('click', (event) => {
  const button = event.target.closest('[data-months]');
  if (button) $('f-expiry').value = addMonths(todayIso(), Number(button.dataset.months));
});

$('lot-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const values = {
    description: $('f-description').value.trim(),
    category: $('f-category').value,
    unit: $('f-unit').value,
    quantity: parseQuantity($('f-quantity').value),
    expiry: $('f-expiry').value,
  };
  const error = validateLot(values);
  if (error) {
    showError('form-error', error);
    return;
  }
  $('form-dialog').close();
  if (!editingLot) {
    enqueue(makeOp('add', { lot: { id: crypto.randomUUID(), ...values } }));
    return;
  }
  const op = editOp(editingLot, findLot(editingLot.id), values);
  if (op) enqueue(op);
});

// ---- Avvio -----------------------------------------------------------------

window.addEventListener('online', () => syncer.syncNow());
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  render(); // "oggi"/"domani" possono essere cambiati mentre l'app era in background
  syncer.syncNow();
});
setInterval(() => {
  if (state.queue.length) syncer.syncNow();
}, RETRY_MS);

render();
syncer.syncNow();

async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) window.location.reload(); // nuova versione installata
  });
  try {
    registration = await navigator.serviceWorker.register('sw.js');
  } catch {
    // Senza HTTPS non c'è modalità offline, ma l'app funziona lo stesso.
  }
}

registerServiceWorker();
