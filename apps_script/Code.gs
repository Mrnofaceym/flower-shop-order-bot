/**
 * Google Apps Script backend for the Telegram order bot.
 *
 * The spreadsheet is the "database":
 *   sheet "Каталог"    — products the owner edits by hand (the bot reads them);
 *   sheet "Замовлення" — orders the bot appends; the owner changes "Статус".
 *
 * Setup (once):
 *   1. Extensions → Apps Script, paste this file, save.
 *   2. Run setup() — it creates both sheets with sample data and a secret key.
 *      Copy the key from View → Logs (Execution log) into the bot's .env as SHEET_SECRET.
 *   3. Deploy → New deployment → type "Web app", Execute as: Me, Who has access: Anyone.
 *      Copy the Web app URL into .env as SHEET_URL.
 */

const CATALOG = 'Каталог';
const ORDERS = 'Замовлення';
const STATUSES = ['Нове', 'Підтверджено', 'Доставляється', 'Виконано', 'Скасовано'];
const ORDER_HEADERS = ['№', 'Створено', 'Клієнт', 'Телефон', 'Telegram ID', 'Склад замовлення',
  'Сума, грн', 'Отримання', 'Адреса', 'Дата', 'Коментар', 'Статус'];

function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  let cat = ss.getSheetByName(CATALOG);
  if (!cat) {
    cat = ss.insertSheet(CATALOG);
    cat.appendRow(['ID', 'Назва', 'Опис', 'Ціна, грн', 'В наявності']);
    [
      [1, 'Букет «Ніжність»', '15 рожевих троянд, евкаліпт, крафт-папір', 1250, true],
      [2, 'Букет «Сонячний»', '7 соняшників і ромашки', 890, true],
      [3, 'Тюльпани (25 шт)', 'Мікс кольорів, стрічка', 1100, true],
      [4, 'Коробка з півоніями', '9 півоній у капелюшній коробці', 2300, true],
      [5, 'Кошик «Святковий»', 'Хризантеми, альстромерії, гвоздики', 1650, true],
      [6, 'Монобукет троянд (51 шт)', 'Червоні троянди 60 см', 3900, false],
    ].forEach(r => cat.appendRow(r));
    styleHeader(cat, 5);
    cat.getRange('E2:E').insertCheckboxes();
    cat.setColumnWidths(1, 1, 50); cat.setColumnWidth(2, 220); cat.setColumnWidth(3, 330);
  }

  let ord = ss.getSheetByName(ORDERS);
  if (!ord) {
    ord = ss.insertSheet(ORDERS);
    ord.appendRow(ORDER_HEADERS);
    styleHeader(ord, ORDER_HEADERS.length);
    const status = ord.getRange('L2:L');
    status.setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).build());
    const colors = {'Нове': '#FFF4CC', 'Підтверджено': '#DCEBFF', 'Доставляється': '#E8DCFF',
                    'Виконано': '#D9F5DD', 'Скасовано': '#F3D6D6'};
    // colour the whole row by its status
    ord.setConditionalFormatRules(Object.keys(colors).map(s =>
      SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied('=$L2="' + s + '"')
        .setBackground(colors[s]).setRanges([ord.getRange('A2:L')]).build()));
    ord.setColumnWidth(6, 320); ord.setColumnWidth(11, 200);
  }

  const old = ss.getSheetByName('Sheet1') || ss.getSheetByName('Аркуш1') || ss.getSheetByName('Лист1');
  if (old && ss.getSheets().length > 2) ss.deleteSheet(old);

  const props = PropertiesService.getScriptProperties();
  let secret = props.getProperty('SECRET');
  if (!secret) {
    secret = Utilities.getUuid().replace(/-/g, '');
    props.setProperty('SECRET', secret);
  }
  Logger.log('SHEET_SECRET=' + secret);
}

function styleHeader(sheet, n) {
  sheet.getRange(1, 1, 1, n).setFontWeight('bold').setBackground('#4F46E5').setFontColor('#FFFFFF');
  sheet.setFrozenRows(1);
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function authorized(secret) {
  return secret && secret === PropertiesService.getScriptProperties().getProperty('SECRET');
}

/** GET ?action=catalog | ?action=orders&user=<telegram id>, always with &secret=... */
function doGet(e) {
  const p = e.parameter || {};
  if (!authorized(p.secret)) return json({ok: false, error: 'forbidden'});
  if (p.action === 'catalog') return json({ok: true, items: readCatalog()});
  if (p.action === 'orders') return json({ok: true, orders: readOrders(String(p.user || ''))});
  if (p.action === 'statuses') return json({ok: true, orders: readStatuses()});
  return json({ok: false, error: 'unknown action'});
}

/** POST JSON {secret, order:{name, phone, user_id, items:[{name, qty, price}], total, delivery, address, date, comment}} */
function doPost(e) {
  let data;
  try { data = JSON.parse(e.postData.contents); } catch (err) { return json({ok: false, error: 'bad json'}); }
  if (!authorized(data.secret)) return json({ok: false, error: 'forbidden'});
  const o = data.order || {};
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ORDERS);
    const last = sh.getLastRow();
    const num = last < 2 ? 1 : Number(sh.getRange(last, 1).getValue()) + 1;
    const items = (o.items || []).map(i => `${i.name} × ${i.qty} = ${i.qty * i.price} грн`).join('\n');
    sh.appendRow([num, new Date(), o.name, "'" + (o.phone || ''), String(o.user_id || ''), items,
                  o.total, o.delivery, o.address || '—', o.date, o.comment || '', 'Нове']);
    sh.getRange(sh.getLastRow(), 2).setNumberFormat('dd.MM.yyyy HH:mm');
    return json({ok: true, number: num});
  } finally {
    lock.releaseLock();
  }
}

function readCatalog() {
  const rows = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CATALOG).getDataRange().getValues();
  return rows.slice(1)
    .filter(r => r[1] !== '' && r[4] === true)
    .map(r => ({id: String(r[0]), name: String(r[1]), description: String(r[2]), price: Number(r[3])}));
}

/** Number, customer id and status of the last 300 orders: the bot compares them to notify customers. */
function readStatuses() {
  const rows = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ORDERS).getDataRange().getValues();
  return rows.slice(1).slice(-300)
    .filter(r => r[0] !== '' && String(r[4]) !== '')
    .map(r => ({number: r[0], user: String(r[4]), status: String(r[11])}));
}

function readOrders(user) {
  const rows = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ORDERS).getDataRange().getValues();
  return rows.slice(1)
    .filter(r => String(r[4]) === user)
    .slice(-5)
    .reverse()
    .map(r => ({number: r[0], total: r[6], date: String(r[9]), status: r[11],
                created: Utilities.formatDate(new Date(r[1]), 'Europe/Kyiv', 'dd.MM.yyyy')}));
}
