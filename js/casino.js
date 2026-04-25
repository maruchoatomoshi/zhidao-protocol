const PRIZES = [
  { code:'empty',   icon:'🍚', name:'Пустая миска риса', desc:'Ничего не выпало...', points:0,   rarity:'common' },
  { code:'small',   icon:'⭐', name:'+30 баллов',        desc:'Небольшой бонус',     points:30,  rarity:'common' },
  { code:'medium',  icon:'💫', name:'+60 баллов',        desc:'Неплохо!',            points:60,  rarity:'uncommon' },
  { code:'walk',    icon:'🕐', name:'+30 мин свободы',   desc:'Покажи скрин вожатому', points:0, rarity:'uncommon' },
  { code:'laundry', icon:'🧺', name:'Вне очереди!',      desc:'Первым на стирку',    points:0,   rarity:'rare' },
  { code:'skip',    icon:'🛡', name:'Иммунитет!',        desc:'Один пропуск без штрафа', points:0, rarity:'rare' },
  { code:'jackpot', icon:'👑', name:'ДЖЕКПОТ!',          desc:'+250 баллов! Невероятно!', points:250, rarity:'jackpot' },
];
const PURPLE_PRIZES = [
  { code:'implant_guanxi',    icon:'🤝', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true',           name:'Гуаньси 关系',       desc:'Имплант: -10% к ценам в магазине', points:0, rarity:'rare' },
  { code:'implant_terracota', icon:'🗿', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/armor.png?raw=true',                    name:'Терракота 兵马俑',   desc:'Имплант: блок 1 штрафа в день',    points:0, rarity:'rare' },
  { code:'implant_panda',     icon:'🐼', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/panda_implant.png?raw=true',      name:'Панда 🐼',           desc:'Кэшбек +10★ с покупки',            points:0, rarity:'rare' },
  { code:'implant_shaolin',   icon:'🥋', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/shaolin_implant.png?raw=true',    name:'Шаолинь 少林',       desc:'+20★ за перекличку вовремя',       points:0, rarity:'rare' },
  { code:'implant_linguasoft',icon:'🎙', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/linguasoft_implant.png?raw=true', name:'Linguasoft 口才',    desc:'+30★ за оценку 5/5 в дневнике',   points:0, rarity:'rare' },
  { code:'implant_caishen',   icon:'💰', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/caishen.png?raw=true',            name:'Цайшэнь 财神',       desc:'+15★ каждые 24 часа',              points:0, rarity:'rare' },
  { code:'implant_qilin',     icon:'🐉', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/qilin_implant.png?raw=true',      name:'Цилинь 麒麟',        desc:'+10★ за каждого владельца Цилиня', points:0, rarity:'rare' },
];
const BLACK_PRIZES = [
  { code:'implant_red_dragon', icon:'🐉', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true',           name:'Красный Дракон 红龙',    desc:'⚡ ЛЕГЕНДАРНЫЙ ПРОТОКОЛ!', points:0, rarity:'jackpot' },
  { code:'implant_netwatch',   icon:'🔴', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/wangluoshouwei_implant.png?raw=true', name:'Сетевой Дозор 网络守卫', desc:'⚡ ЛЕГЕНДАРНЫЙ ПРОТОКОЛ!', points:0, rarity:'jackpot' },
];
const PRIZE_MAP = {};
[...PRIZES, ...PURPLE_PRIZES, ...BLACK_PRIZES].forEach(p => PRIZE_MAP[p.code] = p);
const CASE_IMAGES = {
  gold:   'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/1774509730760.png',
  purple: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/purple_case.png',
  black:  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/legendary_case.png',
};

async function loadImplants(telegramId) {
  if (!telegramId) return;
  const IMPLANT_IMGS = {
    'implant_guanxi':     'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true',
    'implant_terracota':  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/armor.png',
    'implant_red_dragon': 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true',
    'implant_panda':      'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/panda_implant.png?raw=true',
    'implant_shaolin':    'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/shaolin_implant.png?raw=true',
    'implant_linguasoft': 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/linguasoft_implant.png?raw=true',
    'implant_caishen':    'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/caishen.png?raw=true',
    'implant_qilin':      'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/qilin_implant.png?raw=true',
    'implant_netwatch':   'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/wangluoshouwei_implant.png?raw=true',
  };
  try {
    const r = await fetch(`${API_URL}/api/casino/implants/${telegramId}`);
    if (!r.ok) return;
    const data = await r.json();

    const homeContainer = document.getElementById('homeImplants');
    const pageContainer = document.getElementById('myImplantsPage');

    if (!data.length) {
      const empty = '<div class="empty-state" style="padding:12px;">Импланты не установлены<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Открывай фиолетовые и чёрные кейсы!</span></div>';
      if (homeContainer) homeContainer.innerHTML = empty;
      if (pageContainer) pageContainer.innerHTML = empty;
      return;
    }

    // Считаем дубли
    const implantCounts = {};
    data.forEach(imp => { implantCounts[imp.implant_id] = (implantCounts[imp.implant_id] || 0) + 1; });
    const seenTypes = {};

    // Главная страница — компактно
    const homeHtml = data.map(imp => {
      const img = IMPLANT_IMGS[imp.implant_id];
      const dots = Array(3).fill(0).map((_,i) => {
        const cls = i < imp.durability ? (imp.implant_id==='implant_red_dragon'?'dur-dot on-r':'dur-dot on') : 'dur-dot off';
        return `<div class="${cls}"></div>`;
      }).join('');
      return `<div class="implant-row">
        <div class="implant-icon ${imp.implant_id==='implant_red_dragon'?'legendary':''}">
          ${img ? `<img src="${img}" style="width:24px;height:24px;object-fit:contain;border-radius:4px;">` : imp.icon}
        </div>
        <div>
          <div class="implant-cn">${imp.name}</div>
          <div class="implant-py">${imp.desc}</div>
        </div>
        <div class="implant-dur">${dots}</div>
      </div>`;
    }).join('');
    if (homeContainer) homeContainer.innerHTML = homeHtml;

    // Страница имплантов — с кнопкой разборки для дублей
    const pageHtml = data.map(imp => {
      const img = IMPLANT_IMGS[imp.implant_id];
      const isLeg = imp.implant_id === 'implant_red_dragon';
      const isDuplicate = implantCounts[imp.implant_id] > 1;
      seenTypes[imp.implant_id] = (seenTypes[imp.implant_id] || 0) + 1;
      const isSecond = seenTypes[imp.implant_id] > 1;

      const dots = Array(3).fill(0).map((_,i) => {
        const cls = i < imp.durability ? (isLeg?'dur-dot on-r':'dur-dot on') : 'dur-dot off';
        return `<div class="${cls}"></div>`;
      }).join('');

      const duplicateBadge = isDuplicate
        ? `<span style="background:rgba(212,175,55,0.15);border:1px solid rgba(212,175,55,0.3);color:var(--gold);font-size:8px;padding:1px 6px;border-radius:3px;font-family:monospace;margin-left:6px;">ДУБЛЬ</span>`
        : '';

      const disassembleBtn = isSecond
        ? `<button onclick="disassembleImplant(${imp.id})" style="margin-top:8px;width:100%;padding:7px;background:rgba(212,175,55,0.08);border:1px solid rgba(212,175,55,0.25);color:var(--gold);border-radius:6px;font-size:9px;font-family:monospace;cursor:pointer;letter-spacing:1px;">⚙️ [ РАЗОБРАТЬ +100 ★ ]</button>`
        : '';

      return `<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
        <div style="display:flex;align-items:center;gap:10px;">
          ${img ? `<img src="${img}" style="width:52px;height:52px;object-fit:contain;border-radius:8px;border:1px solid ${isLeg?'rgba(180,20,20,0.4)':'rgba(155,89,182,0.3)'};flex-shrink:0;">` : `<div style="font-size:28px;">${imp.icon}</div>`}
          <div style="flex:1;">
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;">
              <div style="font-size:13px;font-weight:700;color:#fff;">${imp.name}</div>
              ${duplicateBadge}
            </div>
            <div style="font-size:10px;color:rgba(212,175,55,0.6);font-family:serif;font-style:italic;margin-top:1px;">${imp.desc}</div>
            <div style="font-size:9px;color:var(--text3);font-family:monospace;margin-top:2px;">Получен: ${new Date(imp.obtained_at).toLocaleDateString('ru-RU')}</div>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
            <div style="font-size:8px;color:var(--text3);font-family:monospace;">ЗАРЯДЫ</div>
            <div class="implant-dur">${dots}</div>
          </div>
        </div>
        ${disassembleBtn}
      </div>`;
    }).join('');
    if (pageContainer) pageContainer.innerHTML = pageHtml;

  } catch(e) {}
}

function gsGetThemeBg(c) {
  const isLight = document.body.classList.contains('theme-genshin-light') || document.body.classList.contains('theme-nw-light');
  return `radial-gradient(ellipse at 50% 40%,${c.bgFrom} 0%,${c.bgTo} 60%,${c.bgFrom} 100%)`;
}

function gsRunVortex(c) {
  const v = document.getElementById('gsVortex'); v.innerHTML = '';
  [0.3,0.5,0.7].forEach((a,i) => {
    const ring = document.createElement('div');
    ring.style.cssText = `width:${80+i*50}px;height:${80+i*50}px;border-radius:50%;border:${2-i*0.3}px solid ${c.vortexColor}${a});animation:gsVortexSpin ${0.8+i*0.2}s ease-out ${i*0.1}s forwards;position:absolute;`;
    v.appendChild(ring);
  });
}

function gsRunParticles(c) {
  const p = document.getElementById('gsParticles'); p.innerHTML = '';
  for(let i=0;i<c.partCount;i++){
    const el=document.createElement('div');
    const isText=Math.random()>0.55;
    const px=(Math.random()-0.5)*300,py=(Math.random()-0.5)*300;
    if(isText){
      el.textContent=c.petals[Math.floor(Math.random()*c.petals.length)];
      el.style.cssText=`position:absolute;font-size:${10+Math.random()*10}px;color:${c.petalColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:gsPartFloat ${1.5+Math.random()*1.5}s ease-out ${Math.random()*0.5}s forwards;opacity:0;`;
    } else {
      const sz=Math.random()*5+2;
      el.style.cssText=`position:absolute;width:${sz}px;height:${sz}px;border-radius:50%;background:${c.petalColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:gsPartFloat ${1.5+Math.random()}s ease-out ${Math.random()*0.4}s forwards;opacity:0;`;
    }
    p.appendChild(el);
  }
}

function gsRunRays(c) {
  const r = document.getElementById('gsRays'); r.innerHTML = '';
  if(!c.rayColor){r.style.opacity='0';return;}
  r.style.opacity='1';
  for(let i=0;i<c.rayCount;i++){
    const ray=document.createElement('div');
    ray.style.cssText=`position:absolute;width:3px;height:180px;border-radius:2px;background:linear-gradient(0deg,${c.rayColor},transparent);transform:rotate(${i*(360/c.rayCount)}deg) translateX(-50%);transform-origin:bottom;left:50%;top:calc(50% - 180px);margin-left:-1.5px;animation:gsRayIn 0.4s ease-out ${i*0.015}s both;opacity:0;`;
    r.appendChild(ray);
  }
}

function gsRunCardStars(c) {
  const w = document.getElementById('gsCardStars'); w.innerHTML = '';
  const positions=[[-50,-30,30,'30deg'],[50,-30,-30,'-30deg'],[-60,10,60,'15deg'],[60,10,-60,'-15deg'],[-40,-55,20,'45deg'],[40,-55,-20,'-45deg'],[-55,50,40,'20deg'],[55,50,-40,'-20deg'],[0,-65,0,'0deg'],[0,65,0,'0deg']];
  positions.slice(0,Math.min(c.rayCount/2,10)).forEach(([tx,ty,tr],i)=>{
    const el=document.createElement('div');
    el.style.cssText=`position:absolute;left:50%;top:50%;font-size:${12+Math.random()*8}px;color:${c.petalColor};--tx:${tx}px;--ty:${ty}px;--tr:${tr};animation:gsStarPop 0.8s ease-out ${0.2+i*0.05}s forwards;opacity:0;font-family:serif;`;
    el.textContent=c.petals[Math.floor(Math.random()*c.petals.length)];
    w.appendChild(el);
  });
}

function gsBuildCard(cardId, cardInfo) {
  const c = GS_CARD_CONFIGS[cardId] || GS_PRIZE_CONFIGS.points;
  const back = document.getElementById('gsCardBack');
  back.style.background = `linear-gradient(135deg,${c.backGrad?c.backGrad[0]:'#c0d5f0'},${c.backGrad?c.backGrad[1]:'#dce8f8'})`;
  back.style.border = `2px solid ${c.backBorder||'rgba(74,122,204,0.6)'}`;
  back.innerHTML = `<svg width="150" height="210" viewBox="0 0 150 210" xmlns="http://www.w3.org/2000/svg">
    <rect width="150" height="210" rx="12" fill="none"/>
    <rect x="8" y="8" width="134" height="194" rx="8" fill="none" stroke="${c.backBorder||'rgba(74,122,204,0.6)'}" stroke-width="1.2" stroke-dasharray="6 3" opacity="0.7"/>
    <circle cx="75" cy="105" r="40" fill="none" stroke="${c.backBorder||'rgba(74,122,204,0.6)'}" stroke-width="1" opacity="0.4"/>
    <circle cx="75" cy="105" r="30" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" opacity="0.08"/>
    <text x="75" y="120" font-size="34" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" opacity="0.75">${c.backCn||'知'}</text>
    <text x="75" y="168" font-size="9" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" letter-spacing="3" opacity="0.6">✦ 祈愿 ✦</text>
    <text x="24" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">龙</text>
    <text x="118" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">月</text>
    <text x="24" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">花</text>
    <text x="118" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">星</text>
  </svg>`;
  const front = document.getElementById('gsCardFront');
  front.style.background = `linear-gradient(180deg,${c.frontGrad?c.frontGrad[0]:'#dceef8'},${c.frontGrad?c.frontGrad[1]:'#eef5fc'})`;
  front.style.border = `2px solid ${c.frontBorder||'rgba(74,122,204,0.7)'}`;
  front.innerHTML = `
    <div style="flex:1;width:100%;display:flex;align-items:center;justify-content:center;position:relative;">
      <div style="position:absolute;inset:4px;border-radius:10px;background:${c.frontBg||'rgba(74,122,204,0.08)'};border:1px solid ${(c.frontBorder||'rgba(74,122,204,0.7)').replace(/[\d.]+\)$/,'0.2)')}"></div>
      ${(c.img) ? `<img src="${c.img}" style="width:110px;height:130px;object-fit:contain;position:relative;z-index:2;border-radius:8px;">` : `<div style="font-size:58px;position:relative;z-index:2;filter:drop-shadow(0 4px 10px ${c.petalColor||'rgba(74,122,204,0.5)'})">${c.emoji||'✦'}</div>`}
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:3px;padding-bottom:2px;">
      <div style="font-size:10px;font-weight:700;color:#2a2040;font-family:serif;letter-spacing:1px;text-align:center;">${cardInfo?cardInfo.name:''}</div>
      <div style="font-size:12px;color:${c.starsColor||'#4a9af5'};letter-spacing:3px;">${c.stars||'★★★★'}</div>
      <div style="font-size:7px;color:rgba(42,32,64,0.6);text-align:center;line-height:1.4;padding:0 4px;font-family:serif;">${cardInfo?cardInfo.passive:''}</div>
    </div>`;
}

async function openGenshinCase() {
  if (gsAnimating) return;
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  // Проверяем заморозку
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('⛔ Аккаунт заморожен. Молитвы недоступны.'); return; }
  } catch(e) {}
  const btn = document.getElementById('genshinOpenBtn');
  btn.disabled = true; btn.textContent = '✦ Молитва совершается... ✦';
  gsAnimating = true; gsCardFlipped = false;
  document.getElementById('gsCard3dNew').style.transform = '';
  document.getElementById('gsCard3dNew').classList.remove('flipped');
  document.getElementById('gsTapHint').style.display = 'none';
  document.getElementById('gsResultInfo').style.opacity = '0';
  document.getElementById('gsCardWrap').style.opacity = '0';
  document.getElementById('gsRays').style.opacity = '0';
  document.getElementById('gsParticles').innerHTML = '';
  document.getElementById('gsVortex').innerHTML = '';
  document.getElementById('gsCardStars').innerHTML = '';

  try {
    const r = await fetch(`${API_URL}/api/genshin/open`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telegram_id: currentUserId})
    });
    const data = await r.json();
    if (!r.ok) {
      if (data.detail==='Only for girls') tg.showAlert('Молитвы доступны только девочкам 🌸');
      else if (data.detail==='Not enough points') tg.showAlert('Недостаточно ✦! Нужно минимум 80');
      else if (data.detail==='Daily limit reached') tg.showAlert('Лимит молитв на сегодня исчерпан');
      else tg.showAlert('Ошибка: ' + (data.detail||''));
      gsAnimating = false; btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
      currentPoints = data.new_points || currentPoints;
      updatePoints();
      return;
    }

    currentPoints = data.new_points; updatePoints();
    curGsCardId = data.card_id || null;
    const cfg = GS_CARD_CONFIGS[data.card_id] || GS_PRIZE_CONFIGS[data.type] || GS_PRIZE_CONFIGS.points;

    // Фон
    document.getElementById('gsBgLayer').style.background = gsGetThemeBg(cfg);

    // Строим карточку (перевёрнутая рубашкой)
    gsBuildCard(data.card_id, {name: data.name||'', passive: data.passive||''});

    // ШАГ 1: Вихрь
    gsRunVortex(cfg);
    gsRunParticles(cfg);

    // ШАГ 2: Вспышка + лучи + карточка
    setTimeout(() => {
      const fl = document.getElementById('gsFlash');
      fl.style.background = cfg.flashColor;
      fl.style.animation = 'gsFlashIn 0.5s ease-out forwards';
      setTimeout(() => { fl.style.animation='none'; fl.style.opacity='0'; }, 500);
      gsRunRays(cfg);
      const cw = document.getElementById('gsCardWrap');
      cw.style.animation = 'none'; cw.offsetHeight;
      cw.style.cssText += 'animation:gsCardIn 0.6s cubic-bezier(0.34,1.4,0.64,1) forwards;opacity:1;';
      setTimeout(() => gsRunCardStars(cfg), 350);
      setTimeout(() => {
        document.getElementById('gsTapHint').style.display = 'block';
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        gsAnimating = false;
        btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
      }, 700);
    }, cfg.revealDelay);

    // Подготавливаем инфо
    document.getElementById('gsResStars').textContent = cfg.stars || '★★★★';
    document.getElementById('gsResStars').style.color = cfg.starsColor || '#4a9af5';
    document.getElementById('gsResName').textContent = data.name || '';
    document.getElementById('gsResPassive').textContent = data.passive || (data.amount ? `+${data.amount}★ начислено` : '');

    if (data.rarity === 5) { setTimeout(() => launchConfetti(80), cfg.revealDelay + 400); }

  } catch(e) {
    tg.showAlert('Ошибка соединения');
    gsAnimating=false; btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
  }
}

// Клик по экрану молитвы — переворачивает карточку
document.addEventListener('DOMContentLoaded', () => {
  const screen = document.getElementById('gsPrayScreen');
  if (screen) screen.addEventListener('click', () => {
    if (gsAnimating || gsCardFlipped) return;
    gsCardFlipped = true;
    document.getElementById('gsCard3dNew').style.transform = 'rotateY(180deg)';
    document.getElementById('gsTapHint').style.display = 'none';
    setTimeout(() => {
      const info = document.getElementById('gsResultInfo');
      info.style.opacity = '1';
      info.style.animation = 'fadeUpAnim 0.4s ease-out forwards';
    }, 600);
  });
});

// Переключатель табов импланты/карточки
function switchImplantsTab(tab) {
  document.getElementById('implants-tab').style.display = tab === 'implants' ? 'block' : 'none';
  document.getElementById('cards-tab').style.display = tab === 'cards' ? 'block' : 'none';
  document.getElementById('tab-implants-btn').classList.toggle('active', tab === 'implants');
  document.getElementById('tab-cards-btn').classList.toggle('active', tab === 'cards');
  if (tab === 'cards') loadCards(currentUserId);
}

const GENSHIN_EMOJIS = {
  'card_zhongli':'🪨','card_pyro':'🔥','card_fox':'🦊',
  'card_fairy':'🌸','card_literature':'📜','card_forest':'🌿',
  'card_sea':'🌊','card_star':'⭐','card_moon':'🌙'
};

const GENSHIN_IMGS = {
  'card_zhongli':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',
  'card_pyro':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',
  'card_fox':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',
  'card_fairy':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',
  'card_literature':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',
  'card_forest':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',
  'card_sea':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',
  'card_moon':'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/moon_card.png?raw=true',
  'card_star':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',
};

const GENSHIN_HISTORY_MAP = {
  'genshin_card_zhongli': { icon: '🪨', name: '岩王帝君 Архонт Земли' },
  'genshin_card_pyro': { icon: '🔥', name: '焰莲使者 Страж Огня' },
  'genshin_card_fox': { icon: '🦊', name: '九尾狐灵 Лиса-Оборотень' },
  'genshin_card_fairy': { icon: '🌸', name: '桃花仙子 Небесная Фея' },
  'genshin_card_literature': { icon: '📜', name: '文曲星君 Звезда Литературы' },
  'genshin_card_forest': { icon: '🌿', name: '木灵仙君 Дух Леса' },
  'genshin_card_sea': { icon: '🌊', name: '海灵仙后 Дух Морей' },
  'genshin_card_star': { icon: '⭐', name: '紫微星君 Императорская Звезда' },
  'genshin_card_moon': { icon: '🌙', name: '嫦娥仙子 Богиня Луны' },
  'genshin_duplicate_card_moon': { icon: '🌙', name: '嫦娥仙子 Богиня Луны · дубль +50★' },
  'genshin_points_30': { icon: '⭐', name: '+30★' },
  'genshin_points_60': { icon: '💫', name: '+60★' },
  'genshin_immunity': { icon: '🛡', name: 'Иммунитет' },
  'genshin_walk': { icon: '🕐', name: '+30 мин свободы' },
};

function formatCasinoHistoryItem(item) {
  const code = item.code || item.name || '';
  if (GENSHIN_HISTORY_MAP[code]) return GENSHIN_HISTORY_MAP[code];

  const cardCode = code.replace(/^genshin_duplicate_/, 'genshin_').replace(/^genshin_/, '');
  const genshinCardKey = `genshin_${cardCode}`;
  if (GENSHIN_HISTORY_MAP[genshinCardKey]) return GENSHIN_HISTORY_MAP[genshinCardKey];

  return {
    icon: item.icon || '🎁',
    name: item.name || code || 'Приз',
  };
}

async function loadCards(telegramId) {
  if (!telegramId) {
    const container = document.getElementById('myCardsContent');
    if (container) container.innerHTML = '<div class="empty-state">Карточек пока нет<br><span style="font-size:10px;font-family:serif;color:var(--text3);">Соверши молитву во вкладке Кейсы!</span></div>';
    return;
  }
  const container = document.getElementById('myCardsContent');
  if (!container) return;
  try {
    const r = await fetch(`${API_URL}/api/cards/${telegramId}`);
    if (!r.ok) { container.innerHTML = '<div class="empty-state">Карточек пока нет</div>'; return; }
    const data = await r.json();
    if (!data.length) {
      container.innerHTML = '<div class="empty-state">Карточек пока нет<br><span style="font-size:10px;font-family:serif;color:var(--text3);">Соверши молитву во вкладке Кейсы!</span></div>';
      return;
    }
    const cardCounts = {};
    data.forEach(c => { cardCounts[c.card_id] = (cardCounts[c.card_id] || 0) + 1; });
    const seen = {};
    container.innerHTML = data.map(card => {
      seen[card.card_id] = (seen[card.card_id] || 0) + 1;
      const isDup = cardCounts[card.card_id] > 1;
      const isSecond = seen[card.card_id] > 1;
      const rarity = card.rarity || 4;
      const rarityColor = rarity === 5 ? '#ffd700' : rarity === 4 ? '#9b59b6' : '#4b8fcf';
      const stars = '★'.repeat(rarity);
      const emoji = GENSHIN_EMOJIS[card.card_id] || '✨';
      const imgSrc = GENSHIN_IMGS[card.card_id];
      const cardPassive = card.passive || '';
      const cardVisual = imgSrc
        ? `<img src="${imgSrc}" style="width:50px;height:60px;object-fit:contain;border-radius:8px;border:1px solid ${rarityColor}44;">`
        : `<div style="font-size:28px;">${emoji}</div>`;
      const dots = Array(3).fill(0).map((_,i) =>
        `<div style="width:8px;height:8px;border-radius:50%;background:${i < card.durability ? rarityColor : 'rgba(255,255,255,0.1)'};"></div>`
      ).join('');
      const disassembleBtn = isSecond
        ? `<button onclick="disassembleCard(${card.id})" style="margin-top:8px;width:100%;padding:6px;background:rgba(219,177,101,0.08);border:1px solid rgba(219,177,101,0.25);color:var(--gold);border-radius:16px;font-size:9px;font-family:serif;cursor:pointer;">✦ [ РАЗОБРАТЬ +50 ✦ ]</button>`
        : '';
      return `<div style="background:var(--bg2);border:1px solid ${isDup ? 'rgba(219,177,101,0.3)' : 'var(--border)'};border-radius:12px;padding:12px;margin-bottom:8px;position:relative;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:50px;height:60px;background:var(--bg3);border:1px solid ${rarityColor}33;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">${cardVisual}</div>
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <div style="font-size:12px;font-weight:700;color:var(--text);font-family:serif;">${card.name}</div>
              ${isDup ? `<span style="font-size:7px;background:rgba(219,177,101,0.15);border:1px solid rgba(219,177,101,0.3);color:var(--gold);padding:1px 6px;border-radius:10px;font-family:monospace;">ДУБЛЬ</span>` : ''}
            </div>
            <div style="font-size:10px;color:${rarityColor};margin-top:2px;">${stars}</div>
            <div style="font-size:9px;color:var(--text2);font-family:serif;margin-top:3px;">${cardPassive}</div>
          </div>
          <div style="display:flex;gap:3px;">${dots}</div>
        </div>
        ${disassembleBtn}
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function disassembleCard(id) {
  tg.showPopup({
    title: '✦ Разобрать карточку?',
    message: 'Ты получишь +50 ✦ за дубль. Карточка будет уничтожена.',
    buttons: [{id:'confirm', type:'default', text:'✦ Разобрать +50 ✦'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/cards/disassemble/${id}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✦ Разобрано! +50 ✦\nБаланс: ${data.new_points} ✦`);
        loadCards(currentUserId);
      } else tg.showAlert('Ошибка разборки');
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

function switchCasinoTab(mode, btn) {
  loadPoints(currentUserId);
  document.querySelectorAll('#page-casino .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const ids = ['casinoPlayContent','casinoInventoryContent','casinoHistoryContent','casinoRulesContent','casinoGenshinContent','genshinRulesContent'];
  ids.forEach(id => { const el=document.getElementById(id); if(el) el.style.display='none'; });
  const isGenshin = currentThemePath === 'genshin';
  if (mode==='play') {
    if (isGenshin) { document.getElementById('casinoGenshinContent').style.display='flex'; }
    else { document.getElementById('casinoPlayContent').style.display='flex'; setTimeout(initRoulette,50); }
  }
  else if (mode==='inventory') { document.getElementById('casinoInventoryContent').style.display='flex'; loadCasinoInventory(); }
  else if (mode==='history') { document.getElementById('casinoHistoryContent').style.display='flex'; loadCasinoHistory(); }
  else if (mode==='rules') {
    if (isGenshin) { const el = document.getElementById('genshinRulesContent'); if(el) el.style.display='flex'; }
    else { document.getElementById('casinoRulesContent').style.display='flex'; }
  }
  else if (mode==='genshin') { document.getElementById('casinoGenshinContent').style.display='flex'; }
}

function initRoulette(caseType = 'gold') {
  const strip = document.getElementById('rouletteStrip');
  if (!strip) return;
  strip.innerHTML = '';
  const imgUrl = CASE_IMAGES[caseType] || CASE_IMAGES.gold;
  const borderColor = caseType==='black' ? 'rgba(180,20,20,0.4)' : caseType==='purple' ? 'rgba(155,89,182,0.4)' : 'rgba(212,175,55,0.2)';
  for (let i = 0; i < 50; i++) {
    const el = document.createElement('div');
    el.className = 'roulette-item';
    el.style.borderColor = borderColor;
    el.innerHTML = `<img src="${imgUrl}" style="width:110px;height:110px;object-fit:contain;">`;
    strip.appendChild(el);
  }
  strip.style.transform = 'translateX(135px)';
  isSpinning = false;
  document.getElementById('openCaseBtn').disabled = false;
  
  document.getElementById('prizeResult').classList.remove('show');
  document.getElementById('prizeResult').style.borderColor = '';
  const track = document.querySelector('.roulette-track');
  if (track) {
    if (caseType==='black') track.style.borderColor='rgba(180,20,20,0.6)';
    else if (caseType==='purple') track.style.borderColor='rgba(155,89,182,0.6)';
    else track.style.borderColor='rgba(180,20,20,0.35)';
  }
}

async function openCase() {
  if (isSpinning) return;
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  if (currentPoints < 80) { tg.showAlert('Недостаточно баллов! Нужно минимум 80 ★'); return; }
  // Проверяем заморозку
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('⛔ Аккаунт заморожен. Кейсы недоступны.'); return; }
  } catch(e) {}
  isSpinning = true;
  document.getElementById('openCaseBtn').disabled = true;
  document.getElementById('prizeResult').classList.remove('show');
  try {
    const r = await fetch(`${API_URL}/api/casino/open`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telegram_id:currentUserId})
    });
    if (!r.ok) {
      const err = await r.json();
      if (err.detail==='Daily limit reached') tg.showAlert('Лимит 3 кейса в день! Купи доп кейс в магазине 😄');
      else if (err.detail==='Not enough points') tg.showAlert('Недостаточно баллов!');
      else tg.showAlert('Ошибка!');
      isSpinning = false;
      document.getElementById('openCaseBtn').disabled = false;
      return;
    }
    const data = await r.json();
    const caseType = data.prize.case_type || 'gold';
    initRoulette(caseType);
    isSpinning = true;
    document.getElementById('openCaseBtn').disabled = true;
    const prize = PRIZE_MAP[data.prize.code] || { code:data.prize.code, icon:data.prize.icon||'🎁', name:data.prize.name, desc:'Редкий приз!', points:data.prize.points||0 };
    await spinRoulette(prize, caseType);
    showPrizeResult(prize, caseType);
    currentPoints = data.new_points;
    updatePoints();
    // Обновляем кнопку после открытия
    const casBtn = document.getElementById('openCaseBtn');
    if (data.remaining_today !== undefined && data.remaining_today <= 0) {
      casBtn.disabled = true;
      casBtn.style.background = 'rgba(255,255,255,0.05)';
      casBtn.style.borderColor = 'rgba(255,255,255,0.08)';
      casBtn.style.color = 'rgba(255,255,255,0.2)';
      casBtn.textContent = '[ Попытки исчерпаны // Приходите завтра ]';
    } else {
      casBtn.disabled = false;
      casBtn.style.background = '';
      casBtn.style.borderColor = '';
      casBtn.style.color = '';
      casBtn.textContent = '🏮 [ 开箱 // ОТКРЫТЬ КЕЙС — 50 ★ ] 🏮';
    }
    if (prize.code==='jackpot'||prize.code==='implant_red_dragon') { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(100); }
    else if (prize.code.startsWith('implant_')) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(50); }
    else if (prize.points > 50) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(30); }
    else if (prize.code==='empty') try{tg.HapticFeedback.notificationOccurred('error');}catch(e){}
    else try{tg.HapticFeedback.impactOccurred('medium');}catch(e){}
    
    if (prize.code.startsWith('implant_')) loadImplants(currentUserId);
  } catch(e) {
    tg.showAlert('Ошибка соединения');
    isSpinning = false;
    document.getElementById('openCaseBtn').disabled = false;
  }
}

async function spinRoulette(targetPrize, caseType = 'gold') {
  return new Promise(resolve => {
    const strip = document.getElementById('rouletteStrip');
    const items = strip.querySelectorAll('.roulette-item');
    const itemWidth = 130;
    const centerOffset = 135;
    const targetIdx = 38 + Math.floor(Math.random() * 4);
    const finalX = centerOffset - targetIdx * itemWidth;
    const startX = centerOffset;
    const duration = 4500;
    let startTime = null;
    function easeOut(t) { return 1 - Math.pow(1-t, 4); }
    function animate(timestamp) {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOut(progress);
      const currentX = startX + (finalX - startX) * eased;
      strip.style.transition = 'none';
      strip.style.transform = `translateX(${currentX}px)`;
      const speed = 1 - eased;
      if (speed > 0.1 && Math.random() < speed * 0.3) { try { try{tg.HapticFeedback.selectionChanged();}catch(e){} } catch(e) {} }
      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        const winner = items[targetIdx];
        winner.classList.add('winner', 'opening');
        setTimeout(() => {
          winner.classList.remove('opening');
          winner.classList.add('opened');
          const prizeContent = targetPrize.img
            ? `<img src="${targetPrize.img}" class="roulette-prize-reveal" style="width:80px;height:80px;object-fit:contain;border-radius:10px;"><div class="roulette-item-name">${targetPrize.name}</div>`
            : `<div class="roulette-item-icon roulette-prize-reveal">${targetPrize.icon}</div><div class="roulette-item-name">${targetPrize.name}</div>`;
          winner.innerHTML = prizeContent;
          if (targetPrize.code==='jackpot') winner.style.animation='shimmer 0.5s infinite';
          resolve();
        }, 600);
      }
    }
    requestAnimationFrame(animate);
  });
}

function showPrizeResult(prize, caseType = 'gold') {
  const isLegendary = caseType === 'black';
  const isPurple = caseType === 'purple';
  const isDark = !document.body.classList.contains('theme-nw-light') &&
                 !document.body.classList.contains('theme-genshin-light') &&
                 !document.body.classList.contains('theme-genshin-dark');

  // Создаём оверлей
  let ov = document.getElementById('cyberResultOverlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'cyberResultOverlay';
    document.getElementById('page-casino').appendChild(ov);
  }

  const bgColor = isLegendary
    ? 'radial-gradient(ellipse at 50% 35%,#2a1800 0%,#150c00 60%,#050300 100%)'
    : isPurple
    ? 'radial-gradient(ellipse at 50% 35%,#1e0a30 0%,#0d0518 60%,#050310 100%)'
    : 'radial-gradient(ellipse at 50% 35%,#0d0d20 0%,#050510 100%)';

  const glowColor = isLegendary ? 'rgba(255,200,0,0.8)' : isPurple ? 'rgba(155,89,182,0.7)' : 'rgba(212,175,55,0.4)';
  const particleColor = isLegendary ? '#ffd700' : isPurple ? '#9b59b6' : '#d4af37';
  const rayColor = isLegendary ? 'rgba(255,215,0,0.8)' : isPurple ? 'rgba(155,89,182,0.7)' : null;
  const tagBg = isLegendary ? 'rgba(212,175,55,0.2)' : isPurple ? 'rgba(155,89,182,0.15)' : 'rgba(100,150,200,0.15)';
  const tagBorder = isLegendary ? 'rgba(212,175,55,0.6)' : isPurple ? 'rgba(155,89,182,0.5)' : 'rgba(100,150,200,0.3)';
  const tagColor = isLegendary ? '#d4af37' : isPurple ? '#9b59b6' : '#6aa0d4';
  const tagText = isLegendary ? '★ ЛЕГЕНДАРНЫЙ ★' : isPurple ? 'РЕДКИЙ // ФИОЛЕТОВЫЙ' : 'ОБЫЧНЫЙ';

  let imgHtml = prize.img
    ? `<img src="${prize.img}" style="width:110px;height:110px;object-fit:contain;filter:drop-shadow(0 0 20px ${glowColor});animation:cyberPulse 2s ease-in-out infinite;">`
    : `<div style="font-size:72px;filter:drop-shadow(0 0 16px ${glowColor});">${prize.icon}</div>`;

  let contentHtml = '';
  if (prize.points > 0) {
    contentHtml = `<div style="font-size:36px;font-weight:900;font-family:monospace;color:${particleColor};text-shadow:0 0 20px ${particleColor};animation:fadeUpAnim 0.4s ease-out 0.5s both;">+${prize.points}★</div>`;
  } else {
    contentHtml = `<div style="font-size:14px;font-weight:700;color:#fff;font-family:monospace;letter-spacing:1px;text-align:center;animation:fadeUpAnim 0.3s ease-out 0.7s both;">${prize.name}</div>`;
  }

  // Лучи
  let raysHtml = '';
  if (rayColor) {
    const count = isLegendary ? 24 : 16;
    for (let i = 0; i < count; i++) {
      raysHtml += `<div style="position:absolute;width:3px;height:${isLegendary?170:150}px;border-radius:2px;background:linear-gradient(0deg,${rayColor},transparent);transform:rotate(${i*(360/count)}deg) translateX(-50%);transform-origin:bottom;left:50%;top:calc(50% - ${isLegendary?170:150}px);margin-left:-1.5px;animation:cyberRayIn 0.4s ease-out ${i*0.015}s both;opacity:0;"></div>`;
    }
  }

  // Частицы
  let partsHtml = '';
  const count = isLegendary ? 40 : isPurple ? 25 : 15;
  const symbols = isLegendary ? ['龙','★','福','✦'] : isPurple ? ['✦','★','◈'] : ['★','✦'];
  for (let i = 0; i < count; i++) {
    const px = (Math.random()-0.5)*300, py = (Math.random()-0.5)*300;
    const isText = Math.random() > 0.6;
    if (isText) {
      const sym = symbols[Math.floor(Math.random()*symbols.length)];
      partsHtml += `<div style="position:absolute;font-size:${12+Math.random()*10}px;color:${particleColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:cyberPartFloat ${1.5+Math.random()*1.5}s ease-out ${Math.random()*0.5}s forwards;opacity:0;">${sym}</div>`;
    } else {
      const sz = Math.random()*5+2;
      partsHtml += `<div style="position:absolute;width:${sz}px;height:${sz}px;border-radius:50%;background:${particleColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:cyberPartFloat ${1.5+Math.random()}s ease-out ${Math.random()*0.4}s forwards;opacity:0;"></div>`;
    }
  }

  ov.style.cssText = `position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;background:${bgColor};animation:cyberOverlayIn 0.3s ease-out forwards;`;
  ov.onclick = () => {
    ov.style.animation = 'cyberOverlayOut 0.3s ease-out forwards';
    setTimeout(() => { ov.style.display='none'; resetCasino(); }, 300);
  };
  ov.innerHTML = `
    <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;">${raysHtml}</div>
    <div style="position:absolute;inset:0;overflow:hidden;pointer-events:none;">${partsHtml}</div>
    <div style="position:relative;z-index:5;display:flex;flex-direction:column;align-items:center;gap:10px;">
      <div style="animation:cyberItemIn 0.6s cubic-bezier(0.34,1.56,0.64,1) forwards;">${imgHtml}</div>
      <div style="font-size:8px;font-family:monospace;letter-spacing:2px;padding:3px 14px;background:${tagBg};border:1px solid ${tagBorder};color:${tagColor};border-radius:2px;animation:fadeUpAnim 0.3s ease-out 0.5s both;opacity:0;">${tagText}</div>
      ${contentHtml}
      <div style="font-size:9px;color:rgba(255,255,255,0.4);font-family:monospace;text-align:center;max-width:200px;line-height:1.6;animation:fadeUpAnim 0.3s ease-out 0.9s both;opacity:0;">${prize.desc||''}</div>
    </div>
    <div style="position:absolute;bottom:24px;font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;letter-spacing:2px;animation:cyberBlink 2s ease-in-out 1.2s infinite;">нажми чтобы продолжить ▼</div>`;
}

function resetCasino() {
  isSpinning = false;
  document.getElementById('prizeResult').classList.remove('show');
  
  document.getElementById('openCaseBtn').disabled = false;
  initRoulette();
}

function launchConfetti(count) {
  const container = document.getElementById('confettiContainer');
  const colors = ['#f5d05a','#d4af37','#fff','#cc2200','#9b59b6','#ff4444'];
  for (let i = 0; i < count; i++) {
    const piece = document.createElement('div');
    piece.className = 'confetti-piece';
    piece.style.left = Math.random() * 100 + '%';
    piece.style.background = colors[Math.floor(Math.random() * colors.length)];
    piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '0';
    piece.style.width = (Math.random() * 8 + 6) + 'px';
    piece.style.height = (Math.random() * 8 + 6) + 'px';
    piece.style.animationDuration = (Math.random() * 2 + 2) + 's';
    piece.style.animationDelay = (Math.random() * 1) + 's';
    container.appendChild(piece);
    setTimeout(() => piece.remove(), 4000);
  }
}

async function disassembleImplant(id) {
  tg.showPopup({
    title: '⚙️ Разобрать имплант?',
    message: 'Ты получишь +100 ★ за разборку дубля. Имплант будет уничтожен.',
    buttons: [{id:'confirm', type:'default', text:'⚙️ Разобрать +100 ★'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/casino/implants/disassemble/${id}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✅ Разобрано! +100 ★\nБаланс: ${data.new_points} ★`);
        loadImplants(currentUserId);
      } else {
        const err = await r.json();
        if (err.detail === 'Not a duplicate') tg.showAlert('Это не дубль — нельзя разобрать!');
        else tg.showAlert('Ошибка разборки');
      }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadCasinoInventory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoInventoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Призов пока нет<br>Открывай кейсы!</div>'; return; }
    container.innerHTML = data.map(item => {
      const expires = item.expires_at ? `<div style="color:#cc4444;font-size:10px;margin-top:3px;">⏰ До ${item.expires_at.slice(11,16)}</div>` : '';
      return `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div><div class="inventory-name">${item.name}</div><div class="inventory-date">${item.desc}</div>${expires}</div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useCasinoPrize(${item.id},'${item.name}')">✅ Использовать</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoInventoryList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function useCasinoPrize(id, name) {
  tg.showPopup({
    title:`Использовать ${name}?`, message:'Покажи этот экран вожатому для подтверждения.',
    buttons:[{id:'confirm',type:'default',text:'✅ Показать вожатому'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/casino/use/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
      if (r.ok) { tg.showAlert('✅ Приз использован!'); loadCasinoInventory(); }
      else { const err=await r.json(); tg.showAlert(err.detail==='Prize expired'?'⏰ Приз истёк!':'Ошибка'); }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadCasinoHistory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/history/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoHistoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">История пуста<br>Открой первый кейс!</div>'; return; }
    container.innerHTML = data.map(item => {
      const date = new Date(item.created_at).toLocaleDateString('ru-RU');
      const time = item.created_at.slice(11,16);
      const historyItem = formatCasinoHistoryItem(item);
      return `<div class="schedule-item">
        <div style="font-size:24px;min-width:35px;text-align:center;">${historyItem.icon}</div>
        <div class="schedule-info"><div class="schedule-subject">${historyItem.name}</div><div class="schedule-location">${date} в ${time}</div></div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoHistoryList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

// ===== ПОГОДА =====
