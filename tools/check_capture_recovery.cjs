"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(path.join(__dirname, "../zhidao_v4/static/app/capture.js"), "utf8");
const code = source.slice(source.indexOf("  async function refresh()"), source.indexOf("  function tick()"));
let now = 10000, events = 0;
const c = vm.createContext({refreshVersion:0, state:null, selected:null, cooldownUntil:new Map(),
  signedIn:()=>true, draw:()=>{}, drawHud:()=>{}, showCard:()=>{},
  Date:{now:()=>now}, CustomEvent:class {constructor(type, init){this.detail=init.detail;}},
  window:{dispatchEvent:()=>{events++;}}, api:async()=>({points:[{code:"a",cooldown_seconds:10}]})});
vm.runInContext(code,c);
(async()=>{
  await c.refresh();assert.equal(c.cooldownUntil.get("a"),20000);
  now=15000;c.api=async()=>{throw Error("offline");};await c.refresh();
  assert.equal(c.cooldownUntil.get("a"),20000);assert.equal(events,1);
  let resolveOld;c.api=()=>new Promise(resolve=>{resolveOld=resolve;});const old=c.refresh();
  const fresh={points:[]};c.api=async()=>fresh;await c.refresh();resolveOld({points:[{code:"old"}]});await old;
  assert.equal(c.state,fresh);
  let resolveAccount;c.api=()=>new Promise(resolve=>{resolveAccount=resolve;});const pending=c.refresh();
  c.refreshVersion++;c.state=null;resolveAccount(fresh);await pending;assert.equal(c.state,null);
  assert.match(source,/if \(document\.hidden\) stop\(\)/);
  console.log("Capture recovery passed: offline cooldown, out-of-order response, auth invalidation; hidden stop hook present.");
})().catch(error=>{console.error(error);process.exitCode=1;});
