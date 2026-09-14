"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), assert = require("node:assert/strict");
(async () => {
  for (const code of ["agent", "zombie", "sabotage"]) {
    const source = fs.readFileSync(path.join(__dirname, "../zhidao_v4/static/app", code + ".js"), "utf8");
    const accept = source.slice(source.indexOf("  function accept(body)"), source.indexOf("  async function refresh()"));
    const refresh = source.slice(source.indexOf("  async function refresh()"), source.indexOf("  async function act("));
    const counters = { reveal:0, sound:0, scheduled:0 };
    const status = {};
    const context = vm.createContext({
      data:null, signature:"", quietRefresh:true, refreshing:false, question:null,
      session:{account:{id:1}}, signedIn:()=>true, onGames:()=>true,
      document:{hidden:false, getElementById:()=>status},
      window:{ZhidaoRetro:{reveal:()=>counters.reveal++}, ZhidaoSounds:{play:()=>counters.sound++}, showToast:()=>{}},
      draw:()=>{}, schedule:()=>counters.scheduled++, api:async()=>{throw Error("offline");}
    });
    vm.runInContext(accept + refresh, context);
    const state = value => code === "agent" ? {you:{news:{kind:"mission",at:value}}}
      : code === "zombie" ? {game:{me:{side:value === 1 ? "human":"zombie"}}}
      : {game:{status:value === 1 ? "running":"meeting",me:{alive:true},meeting:{caller:"Учебный капитан"}}};
    context.accept(state(1)); assert.equal(counters.reveal, 0, code + " initial");
    context.accept(state(2)); assert.equal(counters.reveal, 1, code + " new event");
    context.accept(state(2)); assert.equal(counters.reveal, 1, code + " polling");
    context.quietRefresh = true;
    context.accept(state(1)); assert.equal(counters.reveal, 1, code + " resume");
    context.document.hidden = true;
    context.accept(state(2)); assert.equal(counters.reveal, 1, code + " hidden");
    context.document.hidden = false;
    const scheduled = counters.scheduled;
    await context.refresh();
    assert.equal(context.quietRefresh, true);
    assert.equal(context.refreshing, false);
    assert.ok(counters.scheduled > scheduled, code + " retry");
    assert.match(status.textContent, /Нет связи/);
    context.api = async()=>state(1);
    await context.refresh();
    assert.equal(counters.reveal, 1, code + " quiet reconnect");
    // An old account response cannot replace a newly authenticated account's data.
    const previous = context.data;
    context.api = async()=>{context.session = {account:{id:2}}; return state(2);};
    await context.refresh();
    assert.equal(context.data, previous, code + " stale account response");
  }
  console.log("3 game recovery controllers passed: initial/event/poll/hidden/reconnect/retry/account change.");
})().catch(error=>{console.error(error); process.exitCode=1;});
