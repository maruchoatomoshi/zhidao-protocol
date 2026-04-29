function switchShopTab(mode, btn) {
  shopMode = mode;
  document.querySelectorAll('#page-shop .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  ['shopStoreContent','shopInventoryContent','shopFolkContent'].forEach(id => {
    const el = document.getElementById(id); if (el) el.style.display = 'none';
  });
  if (mode === 'store') {
    document.getElementById('shopStoreContent').style.display = 'block';
    loadShop();
  } else if (mode === 'inventory') {
    document.getElementById('shopInventoryContent').style.display = 'block';
    loadInventory();
  } else if (mode === 'folk') {
    document.getElementById('shopFolkContent').style.display = 'block';
  }
}

// Маппинг иконок магазина — Tabler вместо эмодзи
const SHOP_ICON_EXTRA_CASE = '<span style="position:relative;display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;color:var(--gold);font-size:22px;"><i class="ti ti-package"></i><i class="ti ti-plus" style="position:absolute;right:-3px;bottom:-2px;font-size:12px;color:#60b4d4;background:var(--bg2);border-radius:50%;"></i></span>';
const SHOP_ICONS = {
  'immunity':     '<i class="ti ti-shield-half" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'laundry_vip':  '<i class="ti ti-wash" style="color:#60b4d4;font-size:22px;"></i>',
  'dj':           '<i class="ti ti-music" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'solo_seat':    '<i class="ti ti-brain" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'amnesty':      '<i class="ti ti-heart-handshake" style="color:#60b4d4;font-size:22px;"></i>',
  'kfc':          '<i class="ti ti-meat" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'bubbletea':    '<i class="ti ti-cup" style="color:#60b4d4;font-size:22px;"></i>',
  'snack':        '<i class="ti ti-ice-cream" style="color:var(--gold);font-size:22px;"></i>',
  'no_report':    '<i class="ti ti-file-off" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'poizon':       '<i class="ti ti-shirt" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'extra_case':   SHOP_ICON_EXTRA_CASE,
  'extra_cases':  SHOP_ICON_EXTRA_CASE,
  'additional_case': SHOP_ICON_EXTRA_CASE,
  'case_extra':   SHOP_ICON_EXTRA_CASE,
  'extra_raid_attempt': '<i class="ti ti-sword" style="color:#cc4444;font-size:22px;"></i>',
  'raid_insurance': '<i class="ti ti-shield-dollar" style="color:var(--gold);font-size:22px;"></i>',
  'raid_beacon': '<i class="ti ti-link" style="color:#60b4d4;font-size:22px;"></i>',
  'raid_overclock': '<i class="ti ti-bolt" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'double_win':   '<i class="ti ti-arrows-double-sw-ne" style="color:var(--gold);font-size:22px;"></i>',
  'title_player': '<i class="ti ti-crown" style="color:var(--gold);font-size:22px;"></i>',
};

const GS_CARD_CONFIGS = {
  card_zhongli:   {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',emoji:'🪨',stars:'★★★★★',starsColor:'#c0a040',pool:'gold',backCn:'岩',petals:['✦','★','🌟','◆','✧'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_star:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',emoji:'⭐',stars:'★★★★★',starsColor:'#c0a040',pool:'gold',backCn:'星',petals:['✦','★','🌟','◆'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_pyro:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',emoji:'🔥',stars:'★★★★',starsColor:'#c39ef5',pool:'purple',backCn:'焰',petals:['🌸','✦','💜','✿'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fox:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',emoji:'🦊',stars:'★★★★',starsColor:'#c39ef5',pool:'purple',backCn:'狐',petals:['✦','💜','✿','◈'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fairy:     {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',emoji:'🌸',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'桃',petals:['🌸','✦','💧','❀'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_literature:{img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',emoji:'📜',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'文',petals:['📜','✦','❀','✿'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_forest:    {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',emoji:'🌿',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'木',petals:['🌿','✦','🍃','❀'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_sea:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',emoji:'🌊',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'海',petals:['🌊','✦','💧','◈'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_moon:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/moon_card.png',emoji:'🌙',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'月',petals:['🌙','✦','⭐','✿'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
};
// Призы не-карточки
const GS_PRIZE_CONFIGS = {
  points: {emoji:'✦',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:15,petalColor:'rgba(219,177,101,0.7)',petals:['✦','★'],revealDelay:1200},
  immunity:{emoji:'🛡',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(74,122,204,0.6)',petals:['🛡','✦'],revealDelay:1200},
  walk:    {emoji:'🏮',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(219,177,101,0.6)',petals:['🏮','✦'],revealDelay:1200},
};

let gsAnimating = false, gsCardFlipped = false, curGsCardId = null;

async function loadShop() {
  try {
    const settingsR = await fetch(`${API_URL}/api/settings`);
    if (!settingsR.ok) throw new Error('settings');
    const settings = await settingsR.json();
    if (settings.blackwall && !isAdmin) {
      setShopBlackwallState(true);
      return;
    }

    setShopBlackwallState(false);

    const r = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId||0}`);
    if (!r.ok) throw new Error('shop');
    const data = await r.json();
    document.getElementById('shopPoints').textContent = currentPoints + ' ★';
    document.getElementById('shopFrozenBanner').style.display = data.frozen ? 'block' : 'none';

    const catInfo = {
      'privilege': { name:'特权 ПРИВИЛЕГИИ', cn:'🎮' },
      'points':    { name:'积分 БАЛЛЫ', cn:'⭐' },
      'social':    { name:'社交 СОЦИАЛЬНОЕ', cn:'🤝' },
      'food':      { name:'食物 ЕДА', cn:'🍜' },
      'vip':       { name:'VIP 特设', cn:'👑' },
    };

    const categories = {};
    Object.keys(catInfo).forEach(k => { categories[k] = { ...catInfo[k], items:[] }; });
    data.items.forEach(item => { if (categories[item.category]) categories[item.category].items.push(item); });

    let html = '';
    for (const cat of Object.values(categories)) {
      if (!cat.items.length) continue;
      html += `<div class="shop-cat"><span class="cn">${cat.cn}</span> ${cat.name}</div>`;
      cat.items.forEach(item => {
        const remaining = item.daily_limit > 0 ? Math.max(0, item.daily_limit - item.sold_today) : Infinity;
        const isSoldOut = item.daily_limit > 0 && remaining <= 0;
        const canAfford = currentPoints >= item.price;
        const isUnavailable = !item.available || isSoldOut;

        let limitHtml = '';
        if (item.daily_limit > 0) {
          if (isSoldOut) {
            limitHtml = `<div class="shop-item-limit limit-soldout">⛔ Сегодня всё разобрали</div>`;
          } else if (remaining === 1) {
            limitHtml = `<div class="shop-item-limit limit-low">🔥 Последний!</div>`;
          } else if (remaining <= 2) {
            limitHtml = `<div class="shop-item-limit limit-medium">⏳ Осталось ${remaining} из ${item.daily_limit}</div>`;
          } else {
            limitHtml = `<div class="shop-item-limit">📦 ${remaining} из ${item.daily_limit}</div>`;
          }
        } else {
          limitHtml = `<div class="shop-item-limit">∞ Без ограничений</div>`;
        }

        let btnHtml;
        if (isSoldOut) {
          btnHtml = `<div class="shop-item-badge soldout">РАСПРОДАНО</div>`;
        } else if (!item.available) {
          btnHtml = `<div class="shop-item-badge unavailable">НЕДОСТУПНО</div>`;
        } else if (!canAfford) {
          const need = item.price - currentPoints;
          btnHtml = `<button class="shop-item-buy no-money" disabled>−${need} ★</button>`;
        } else {
          btnHtml = `<button class="shop-item-buy" onclick="buyItem('${item.code}','${item.name}',${item.price})">${item.price} ★</button>`;
        }

        html += `<div class="shop-item ${isSoldOut ? 'sold-out' : ''} ${!item.available && !isSoldOut ? 'unavailable' : ''}" data-item-code="${item.code}">
          <div class="shop-item-icon">${SHOP_ICONS[item.code] || item.icon}</div>
          <div style="flex:1;min-width:0;">
            <div class="shop-item-name">${item.name}</div>
            <div class="shop-item-cn">${item.description}</div>
            ${limitHtml}
          </div>
          ${btnHtml}
        </div>`;
      });
    }

    document.getElementById('shopStoreContent').innerHTML = html || '<div class="empty-state">Магазин пуст</div>';
  } catch(e) {
    document.getElementById('shopStoreContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function buyItem(code, name, price) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  tg.showPopup({
    title: `Купить ${name}?`,
    message: `Стоимость: ${price} ★\nТвой баланс: ${currentPoints} ★`,
    buttons: [{id:'confirm',type:'default',text:'✅ Купить'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/buy`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({telegram_id:currentUserId, item_code:code})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        const itemEl = document.querySelector(`.shop-item[data-item-code="${code}"]`);
        if (itemEl) {
          itemEl.classList.add('shop-item-bought');
          spawnShopSparkles(itemEl);
        }
        showToast(`✅ Куплено: ${data.item}!\nОстаток: ${data.new_points} ★`, 'success');
        setTimeout(() => loadShop(), 650);
      } else {
        const err = await r.json();
        if (err.detail === 'Daily limit reached') showToast('Этот товар уже разобрали!');
        else if (err.detail === 'Not enough points') showToast('Недостаточно баллов!');
        else if (err.detail === 'Account frozen') showToast('⛔ Аккаунт под надзором NetWatch');
        else showToast('Ошибка покупки');
      }
    } catch(e) { showToast('Ошибка соединения'); }
  });
}

async function loadInventory() {
  try {
    const r = await fetch(`${API_URL}/api/shop/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('shopInventoryContent');
    const digital = ['extra_case','extra_cases','additional_case','case_extra','extra_raid_attempt','double_win','title_player','immunity','raid_insurance','raid_beacon','raid_overclock'];
    const physical = data.filter(item => !digital.includes(item.code));
    if (!physical.length) { container.innerHTML = '<div class="empty-state">Инвентарь пуст<br>Купи что-нибудь в магазине!</div>'; return; }
    container.innerHTML = physical.map(item =>
      `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div class="inventory-info">
            <div class="inventory-kicker">STORE ITEM</div>
            <div class="inventory-name">${item.name}</div>
            <div class="inventory-date">Получен: ${new Date(item.purchased_at).toLocaleDateString('ru-RU')} · ID: ${item.id}</div>
          </div>
          <div class="inventory-side">
            <div class="inventory-pill">${item.category || 'ITEM'}</div>
          </div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useItem(${item.id},'${item.name}')">✅ Использовать</button>
          <button class="inv-btn inv-btn-gift" onclick="giftItem(${item.id},'${item.name}')">🎁 Подарить</button>
          <button class="inv-btn inv-btn-sell" onclick="sellItem(${item.id},'${item.name}',${item.price})">💰 Продать</button>
        </div>
      </div>`
    ).join('');
  } catch(e) { document.getElementById('shopInventoryContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function useItem(id, name) {
  tg.showPopup({
    title: `Использовать ${name}?`,
    message: 'Покажи этот экран вожатому. После подтверждения товар спишется.',
    buttons: [{id:'confirm', type:'default', text:'✅ Использовать'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/use/${id}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        showToast(`✅ ${name} использован!\nПокажи это сообщение вожатому.`);
        loadInventory();
      } else {
        showToast('Ошибка использования');
      }
    } catch(e) { showToast('Ошибка соединения'); }
  });
}
function giftItem(id, name) { tg.showPopup({title:`Подарить ${name}?`,message:'Введи имя получателя в чате бота командой /подарить ИМЯ\n\nНалог на дарение: 20 баллов',buttons:[{type:'ok'}]}); }

async function sellItem(id, name, price) {
  const refund = Math.floor(price / 2);
  tg.showPopup({
    title:`Продать ${name}?`,
    message:`Ты получишь ${refund} ★ (50% от стоимости ${price} ★)`,
    buttons:[{id:'confirm',type:'destructive',text:`💰 Продать за ${refund} ★`},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/sell`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purchase_id:id,telegram_id:currentUserId})});
      if (r.ok) { const data=await r.json(); currentPoints=data.new_points; updatePoints(); showToast(`✅ Продано! +${data.refund} ★`); loadInventory(); }
    } catch(e) { showToast('Ошибка'); }
  });
}

function spawnShopSparkles(itemEl) {
  const icon = itemEl.querySelector('.shop-item-icon');
  if (!icon) return;
  const count = 8;
  for (let i = 0; i < count; i++) {
    const s = document.createElement('span');
    s.className = 'shop-sparkle';
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.6;
    const dist = 28 + Math.random() * 18;
    s.style.setProperty('--sx', `${Math.cos(angle) * dist}px`);
    s.style.setProperty('--sy', `${Math.sin(angle) * dist}px`);
    s.style.animationDelay = `${Math.random() * 80}ms`;
    s.textContent = ['✦','✧','★','◆'][i % 4];
    icon.appendChild(s);
    setTimeout(() => s.remove(), 700);
  }
}

async function resetShop() {
  try {
    const r = await fetch(`${API_URL}/api/admin/reset_shop`,{method:'POST',headers:{'x-admin-id':currentUserId}});
    if (r.ok) showToast('✅ Магазин сброшен!');
  } catch(e) { showToast('Ошибка'); }
}

// ===== КАЗИНО =====
