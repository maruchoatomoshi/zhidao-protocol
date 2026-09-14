"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync(path.join(__dirname,"../zhidao_v4/static/app/royale.js"),"utf8");
const code=source.slice(source.indexOf("  function accept(body)"),source.indexOf("  async function act("));
const status={};
let draws=0;
const c=vm.createContext({
  data:null,quietRefresh:true,refreshing:false,signature:"",seenRound:null,seenReveal:null,
  justOut:0,tickSecond:null,celebrated:null,stageOpen:false,session:{account:{id:1}},
  stageAlive:new Map(),stageSeen:new Set(),
  document:{hidden:false},onGames:()=>true,signedIn:()=>true,draw:()=>{draws++;},schedule:()=>{},
  sound:()=>{throw Error("Replayed sound");},renderPanel:()=>{},$:()=>status,
  api:async()=>{throw Error("offline");}
});
vm.runInContext(code,c);
const state=(phase,round=1)=>({game:{id:4,status:phase,round,question:{},me:{alive:true}}});
c.accept(state("question")); assert.equal(c.seenRound,"4:1");
c.quietRefresh=true;c.accept(state("reveal"));assert.equal(c.seenReveal,"4:1");
c.quietRefresh=true;c.accept(state("over"));assert.equal(c.celebrated,4);
const gridState=state("reveal");gridState.game.grid=[{name:"Player",alive:false}];
c.quietRefresh=true;c.accept(gridState);
assert.equal(c.stageAlive.get("Player"),false);assert.equal(c.stageSeen.has("Player"),true);
const beforeDraws=draws;c.quietRefresh=true;c.accept(gridState);assert.equal(draws,beforeDraws+1);
(async()=>{
  await c.refresh();assert.equal(c.quietRefresh,true);assert.equal(c.refreshing,false);assert.match(status.textContent,/Нет связи/);
  c.api=async()=>state("question",3);await c.refresh();assert.equal(c.seenRound,"4:3");
  const previous=c.data;c.api=async()=>{c.session={account:{id:2}};return state("over");};
  await c.refresh();assert.equal(c.data,previous);
  console.log("Protocol 60 recovery passed: silent question/reveal/finale, retry, reconnect, account change.");
})().catch(error=>{console.error(error);process.exitCode=1;});
