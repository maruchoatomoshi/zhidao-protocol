"use strict";
// Dependency-free behavioral checks of the isolated teaching controller.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const root = path.resolve(__dirname, "..", "zhidao_v4/static/app");
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.dataset = {}; this.disabled = false; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute() {}
  addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
  click() { if (!this.disabled) (this.events.click || []).forEach(fn => fn()); }
  querySelectorAll() { return []; }
  querySelector(tag) { return this.children.find(n => n.tag === tag); }
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
}
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const ids = [...new Set([...html.matchAll(/data-game-guide="([^"]+)"/g)].map(m => m[1]))];
const links = ids.map(code => { const el = new Element("button"); el.dataset.gameGuide = code; return el; });
const nodes = Object.fromEntries(["gameGuide", "gameGuideBody", "gameGuideTitle"].map(id => [id, new Element("div")]));
const source = fs.readFileSync(path.join(root, "games.js"), "utf8").split("/* Игры за столом:")[0];
vm.runInNewContext(source, {
  document: { getElementById: id => nodes[id], createElement: tag => new Element(tag), querySelectorAll: () => links },
  // Training must not need any network or authenticated game state.
  fetch() { throw new Error("Training attempted network access"); }
});
for (const link of links) {
  link.click();
  assert.equal(nodes.gameGuide.open, true, link.dataset.gameGuide);
  const body = nodes.gameGuideBody;
  assert.ok(body.children[0].children.length >= 3);
  body.children.find(n => n.tag === "button").click();
  for (let i = 0; i < 3; i++) {
    assert.equal(body.children[0].textContent, `Шаг ${i + 1} из 3`);
    const buttons = body.children.filter(n => n.tag === "button");
    const next = buttons.at(-1);
    assert.equal(next.disabled, true);
    let valid = 0, invalid = 0;
    for (const choice of buttons.slice(0, -1)) {
      choice.click();
      if (next.disabled) invalid++; else valid++;
    }
    assert.equal(valid, 1); assert.equal(invalid, 1);
    for (const choice of buttons.slice(0, -1)) { choice.click(); if (!next.disabled) break; }
    next.click();
  }
  assert.equal(body.children[0].textContent, "Основы пройдены");
}
console.log(`${ids.length} lessons passed: rules, 3 steps, wrong/correct answers, completion; no API.`);
