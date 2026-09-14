"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync(path.join(__dirname,"../zhidao_v4/static/app/games.js"),"utf8");
const code=source.slice(source.indexOf("  async function refresh()"),source.indexOf("  /* Какой финал"));
let wins=0, scheduled=0, draws=0;const note={};
const c=vm.createContext({quietRefresh:true,refreshing:false,retryTimer:null,session:{account:{id:1}},
  view:null,switches:{},signature:"",phaseKey:null,phaseEntrance:false,local:{},armed:null,timers:{},zeroRefreshed:new Set(),chatLog:[],
  document:{hidden:false},onScreen:()=>true,signedIn:()=>true,drawIntro:()=>{},draw:()=>{draws++;},
  startPolling:()=>{},stopPolling:()=>{},setNote:text=>{note.textContent=text;},$:()=>note,
  setTimeout:()=>{scheduled++;return 1;},clearTimeout:()=>{},POLL_MS:1000,
  window:{ZhidaoSounds:{play:()=>{wins++;}}},finaleFor:()=>({}),
  renderers:{spy:{phaseKey:g=>g.phase,finished:g=>g.phase==="over"}},api:async()=>{throw Error("offline");}});
vm.runInContext(code,c);
const state=(phase,revision)=>({room:{code:"1234",game:"spy",revision},game:{phase},players:[]});
(async()=>{
  c.apply(state("play",1));assert.equal(wins,0);
  c.apply(state("over",2));assert.equal(wins,1);c.apply(state("over",2));assert.equal(wins,1);
  c.apply(state("play",3));c.quietRefresh=true;c.apply(state("over",4));assert.equal(wins,1);assert.equal(c.phaseEntrance,false);
  await c.refresh();assert.equal(scheduled,1);assert.equal(c.quietRefresh,true);
  c.api=async()=>state("over",4);const before=draws;await c.refresh();assert.equal(draws,before+1);assert.equal(note.textContent,"");
  const prior=c.view;c.api=async()=>{c.session={account:{id:2}};return state("play",5);};await c.refresh();assert.equal(c.view,prior);
  console.log("Rooms recovery passed: live finale once, quiet resume, retry, unchanged recovery, stale account.");
})().catch(error=>{console.error(error);process.exitCode=1;});
