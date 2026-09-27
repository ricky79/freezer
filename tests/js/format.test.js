import { test, assertEqual } from './harness.js';
import { CATALOG } from './catalog.fixture.js';
import { categoryLabel, escapeHtml, formatQuantity, normalizeText, parseQuantity } from '../../web/format.js';

test('formatQuantity usa singolare e plurale', () => {
  assertEqual(formatQuantity(1, 'buste', CATALOG), '1 busta');
  assertEqual(formatQuantity(3, 'buste', CATALOG), '3 buste');
  assertEqual(formatQuantity(2, 'barattoli_grandi', CATALOG), '2 barattoli grandi');
  assertEqual(formatQuantity(500, 'grammi', CATALOG), '500 g');
  assertEqual(formatQuantity(4, 'sconosciuta', CATALOG), '4');
});

test('categoryLabel', () => {
  assertEqual(categoryLabel('sughi', CATALOG), 'Sughi');
  assertEqual(categoryLabel('boh', CATALOG), 'boh');
});

test('normalizeText ignora maiuscole e accenti', () => {
  assertEqual(normalizeText('  Ragù ÀBC '), 'ragu abc');
});

test('escapeHtml neutralizza i caratteri HTML e lascia il resto', () => {
  assertEqual(
    escapeHtml(`Pollo <arrosto> & "patate" l'altro 🍝`),
    'Pollo &lt;arrosto&gt; &amp; &quot;patate&quot; l&#39;altro 🍝',
  );
});

test('parseQuantity accetta solo interi nel limite', () => {
  assertEqual(parseQuantity(' 12 '), 12);
  assertEqual(parseQuantity('007'), 7);
  assertEqual(parseQuantity('99999'), 99999);
  assertEqual(parseQuantity('100000'), null);
  assertEqual(parseQuantity('1,5'), null);
  assertEqual(parseQuantity('1.5'), null);
  assertEqual(parseQuantity('0'), null);
  assertEqual(parseQuantity('-3'), null);
  assertEqual(parseQuantity(''), null);
  assertEqual(parseQuantity('abc'), null);
  assertEqual(parseQuantity(undefined), null);
  assertEqual(parseQuantity('5', 3), null);
  assertEqual(parseQuantity('3', 3), 3);
});
