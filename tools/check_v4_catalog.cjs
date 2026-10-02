/* Behaviour checks for the real catalog controller; no browser/network dependency.
   Run: node --test tools/check_v4_catalog.cjs */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.listeners = {};
  }
  set textContent(text) { this.children = [{ textContent: text }]; }
  get textContent() { return this.children.map(child => child.textContent).join(''); }
  get firstChild() { return this.children[0]; }
  get childElementCount() { return this.children.filter(child => child instanceof Element).length; }
  append(...children) {
    for (const child of children) {
      if (child.parent) child.parent.children = child.parent.children.filter(item => item !== child);
      child.parent = this;
      this.children.push(child);
    }
  }
  setAttribute() {}
  removeAttribute() {}
  addEventListener(type, listener) { this.listeners[type] = listener; }
  querySelectorAll() { return []; }
  focus() {}
}

function setup() {
  const catalog = new Element(), screen = new Element(), back = new Element();
  const room = new Element(), button = new Element('button');
  room.hidden = true;
  back.querySelector = () => button;
  const listeners = {}, requests = [];
  const window = {
    ZhidaoSession: { mode: 'preview' },
    addEventListener(name, callback) { (listeners[name] ||= []).push(callback); },
    dispatchEvent(event) { for (const callback of listeners[event.type] || []) callback(event); },
    scrollTo() {},
  };
  const document = {
    hidden: false,
    documentElement: { dataset: { currentScreen: 'games' } },
    createElement: tag => new Element(tag),
    getElementById: id => ({ gamesCatalog: catalog, gamesBack: back, gameRoom: room })[id],
    querySelector: () => screen,
    addEventListener() {},
  };
  const context = {
    window, document, setTimeout: () => 1, clearTimeout() {},
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    Event: class { constructor(type) { this.type = type; } },
    MutationObserver: class { observe() {} },
    fetch: () => new Promise((resolve, reject) => requests.push({ resolve, reject })),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../zhidao_v4/static/app/games-catalog.js'), 'utf8'), context);
  const auth = (mode, id = 1) => window.dispatchEvent({ type: 'zhidao:auth', detail: { mode, account: mode === 'authenticated' ? { id } : undefined } });
  const reply = async (data, status = 200, index = requests.length - 1) => {
    requests[index].resolve({ ok: status === 200, status, json: async () => data });
    await new Promise(resolve => setImmediate(resolve));
  };
  const group = key => catalog.children.find(child => child.className === `catalog-group is-${key}`);
  return { catalog, requests, auth, reply, window, group };
}

test('preview does not claim that unknown games are scheduled for later', () => {
  const app = setup();
  assert.equal(app.requests.length, 0);
  assert.match(app.catalog.textContent, /Правила доступны без входа/);
  assert.match(app.group('later').textContent, /Игры сезона/);
});

test('successful snapshot separates lobby, waiting window and absent round', async () => {
  const app = setup(); app.auth('authenticated');
  await app.reply({ season_id: 1, items: [
    { key: 'royale', state: 'lobby', players: 3 },
    { key: 'capture', state: 'waiting', until: '2026-10-02T18:00:00+08:00' },
  ] });
  assert.match(app.group('live').textContent, /ЛОББИ · 3/);
  assert.match(app.group('later').textContent, /откроется в 18:00/);
  assert.match(app.group('later').textContent, /Раунд не запущен/);
});

test('no season and failed request are different from a stopped game', async () => {
  const app = setup(); app.auth('authenticated');
  await app.reply({ season_id: null, items: [] });
  assert.match(app.catalog.textContent, /нет активного сезона/);
  assert.doesNotMatch(app.catalog.textContent, /Раунд не запущен/);
  app.auth('authenticated');
  await app.reply({}, 503);
  assert.match(app.catalog.textContent, /Не удалось обновить/);
  assert.doesNotMatch(app.catalog.textContent, /Раунд не запущен/);
});

test('network failure clears stale live status', async () => {
  const app = setup(); app.auth('authenticated');
  await app.reply({ season_id: 1, items: [{ key: 'zombie', state: 'running' }] });
  app.window.dispatchEvent({ type: 'zhidao:screen', detail: 'games' });
  app.requests.at(-1).reject(new Error('offline'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.group('live').hidden, true);
  assert.match(app.catalog.textContent, /Проверьте связь/);
});

test('late response cannot restore another account or preview state', async () => {
  const app = setup(); app.auth('authenticated', 1);
  app.auth('authenticated', 2);
  await app.reply({ season_id: null, items: [] }, 200, 1);
  await app.reply({ season_id: 1, items: [{ key: 'royale', state: 'lobby' }] }, 200, 0);
  assert.match(app.catalog.textContent, /нет активного сезона/);
  app.auth('authenticated', 2);
  app.auth('preview');
  await app.reply({ season_id: 1, items: [{ key: 'royale', state: 'lobby' }] });
  assert.match(app.catalog.textContent, /Правила доступны без входа/);
  assert.equal(app.group('live').hidden, true);
});
