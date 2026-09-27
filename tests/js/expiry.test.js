import { test, assertEqual } from './harness.js';
import {
  addMonths, countAlerts, daysLeft, expiryStatus, expiryText, formatDate, formatDayMonth, todayIso,
} from '../../web/expiry.js';

test('todayIso usa la data locale anche vicino a mezzanotte', () => {
  assertEqual(todayIso(new Date(2026, 8, 27, 23, 59)), '2026-09-27');
  assertEqual(todayIso(new Date(2026, 8, 28, 0, 1)), '2026-09-28');
  assertEqual(todayIso(new Date(2027, 0, 5, 12, 0)), '2027-01-05');
});

test('daysLeft attraversa mesi e cambio ora legale', () => {
  assertEqual(daysLeft('2026-10-02', '2026-09-27'), 5);
  assertEqual(daysLeft('2026-10-26', '2026-10-24'), 2);
  assertEqual(daysLeft('2026-09-26', '2026-09-27'), -1);
});

test('expiryStatus ai confini', () => {
  const today = '2026-09-27';
  assertEqual(expiryStatus('2026-09-26', today, 7), 'expired');
  assertEqual(expiryStatus('2026-09-27', today, 7), 'expiring');
  assertEqual(expiryStatus('2026-10-04', today, 7), 'expiring');
  assertEqual(expiryStatus('2026-10-05', today, 7), 'ok');
  assertEqual(expiryStatus('2026-09-28', today, 0), 'ok');
});

test('expiryText', () => {
  const today = '2026-09-27';
  assertEqual(expiryText('2026-09-20', today), 'scaduto da 7 giorni');
  assertEqual(expiryText('2026-09-26', today), 'scaduto ieri');
  assertEqual(expiryText('2026-09-27', today), 'oggi');
  assertEqual(expiryText('2026-09-28', today), 'domani');
  assertEqual(expiryText('2026-10-02', today), 'tra 5 giorni');
});

test('countAlerts conta scaduti e in scadenza', () => {
  const lots = [{ expiry: '2026-09-01' }, { expiry: '2026-09-27' }, { expiry: '2026-09-30' }, { expiry: '2027-01-01' }];
  assertEqual(countAlerts(lots, '2026-09-27', 7), { expired: 1, expiring: 2 });
});

test('formattazione date', () => {
  assertEqual(formatDayMonth('2026-09-07'), '07/09');
  assertEqual(formatDate('2026-09-07'), '07/09/2026');
});

test('addMonths gestisce fine mese e anni bisestili', () => {
  assertEqual(addMonths('2026-09-27', 1), '2026-10-27');
  assertEqual(addMonths('2026-09-27', 6), '2027-03-27');
  assertEqual(addMonths('2026-11-15', 3), '2027-02-15');
  assertEqual(addMonths('2026-01-31', 1), '2026-02-28');
  assertEqual(addMonths('2028-01-31', 1), '2028-02-29');
  assertEqual(addMonths('2026-08-31', 3), '2026-11-30');
});
