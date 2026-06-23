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
  'path_switch':  '<i class="ti ti-arrows-right-left" style="color:rgba(230,160,60,0.9);font-size:22px;"></i>',
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

function getShopCategoryInfo(category) {
  const info = {
    'privilege': { name:'Бонусы и права', tone:'violet', icon:'⚡', note:'Защита, доп. попытки и особые действия' },
    'points':    { name:'Баллы', tone:'gold', icon:'★', note:'Всё, что связано со звёздами' },
    'social':    { name:'Для команды', tone:'cyan', icon:'🤝', note:'Помощь друзьям и общие действия' },
    'food':      { name:'Еда и приятности', tone:'red', icon:'🍜', note:'Вкусное и реальные бонусы' },
    'vip':       { name:'Редкое', tone:'gold', icon:'👑', note:'Дорогие и особые товары' },
  };
  return info[category] || { name:'Другое', tone:'cyan', icon:'◇', note:'Системные товары' };
}

function getShopItemTier(item) {
  if (item.daily_limit > 0 && Math.max(0, item.daily_limit - item.sold_today) <= 1) return 'hot';
  if ((item.price || 0) >= 500) return 'legendary';
  if ((item.price || 0) >= 180) return 'rare';
  return 'standard';
}

function getShopTierLabel(tier) {
  return {
    hot: 'HOT',
    legendary: 'LEGEND',
    rare: 'RARE',
    standard: 'ITEM'
  }[tier] || 'ITEM';
}

function getShopItemHint(item) {
  const code = item.code || '';
  if (code.includes('case')) return 'для кейсов';
  if (code.includes('raid')) return 'для рейда';
  if (code.includes('immunity') || code.includes('amnesty')) return 'защита';
  if (code.includes('food') || code === 'kfc' || code === 'bubbletea' || code === 'snack') return 'приятность';
  if (code.includes('path') || code.includes('title')) return 'профиль';
  if (code.includes('double')) return 'усиление';
  return item.category === 'social' ? 'команда' : 'бонус';
}

function shopEscapeHtml(value) {
  if (typeof escapeHtml === 'function') return escapeHtml(value);
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function shopJsArg(value) {
  return String(value || '')
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\n/g, ' ');
}

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

    const categories = {};
    data.items.forEach(item => {
      const key = item.category || 'protocol';
      if (!categories[key]) categories[key] = { ...getShopCategoryInfo(key), key, items:[] };
      categories[key].items.push(item);
    });

    const totalItems = data.items.length;
    const availableItems = data.items.filter(item => item.available && !(item.daily_limit > 0 && Math.max(0, item.daily_limit - item.sold_today) <= 0)).length;
    const limitedItems = data.items.filter(item => item.daily_limit > 0).length;
    const purchasableItems = data.items.filter(item => {
      const remaining = item.daily_limit > 0 ? Math.max(0, item.daily_limit - item.sold_today) : Infinity;
      return item.available && remaining > 0;
    });
    const suggestionPriority = ['immunity', 'extra_raid_attempt', 'amnesty', 'double_win', 'laundry_vip', 'title_player'];
    const priorityIndex = (item) => {
      const index = suggestionPriority.indexOf(item.code);
      return index === -1 ? 99 : index;
    };
    const suggestedItem = purchasableItems
      .filter(item => currentPoints >= item.price)
      .sort((a, b) => priorityIndex(a) - priorityIndex(b) || a.price - b.price)[0]
      || purchasableItems.sort((a, b) => a.price - b.price)[0]
      || null;
    const canBuyNow = data.items.filter(item => {
      const remaining = item.daily_limit > 0 ? Math.max(0, item.daily_limit - item.sold_today) : Infinity;
      return item.available && remaining > 0 && currentPoints >= item.price;
    }).length;

    let html = `<div class="shop-command-card">
      <div class="shop-command-bg">商店</div>
      <div class="shop-command-main">
        <div class="shop-command-kicker">ZHIDAO MARKET // ПРОСТОЙ РЕЖИМ</div>
        <div class="shop-command-title">Что можно купить?</div>
        <div class="shop-command-sub">Выбирай категорию, смотри цену и жми “Купить”. Если звёзд не хватает, кнопка сама покажет сколько нужно накопить.</div>
      </div>
      <div class="shop-command-stats">
        <div><span>твои звёзды</span><strong>${currentPoints} ★</strong></div>
        <div><span>можно сейчас</span><strong>${canBuyNow}</strong></div>
        <div><span>товаров</span><strong>${availableItems}/${totalItems}</strong></div>
      </div>
    </div>`;

    if (suggestedItem) {
      const enough = currentPoints >= suggestedItem.price;
      html += `<div class="shop-featured-item">
        <div class="shop-featured-icon">${SHOP_ICONS[suggestedItem.code] || suggestedItem.icon || '◇'}</div>
        <div class="shop-featured-copy">
          <div class="shop-featured-kicker">${enough ? 'МОЖНО КУПИТЬ СЕЙЧАС' : 'БЛИЖАЙШАЯ ЦЕЛЬ'}</div>
          <div class="shop-featured-name">${shopEscapeHtml(suggestedItem.name)}</div>
          <div class="shop-featured-desc">${enough ? 'Звёзд хватает. Хороший вариант, если не знаешь, с чего начать.' : `Нужно ещё ${Math.max(0, suggestedItem.price - currentPoints)} ★.`}</div>
        </div>
        <div class="shop-featured-price">${suggestedItem.price} ★</div>
      </div>`;
    }

    for (const cat of Object.values(categories)) {
      if (!cat.items.length) continue;
      html += `<section class="shop-section shop-section-${cat.tone}">
        <div class="shop-cat">
          <div>
            <span class="shop-cat-kicker">${cat.icon || '◇'} КАТЕГОРИЯ</span>
            <strong>${shopEscapeHtml(cat.name)}</strong>
            <em>${cat.note}</em>
          </div>
          <span class="shop-cat-count">${cat.items.length}</span>
        </div>
        <div class="shop-grid-modern">`;
      cat.items.forEach(item => {
        const remaining = item.daily_limit > 0 ? Math.max(0, item.daily_limit - item.sold_today) : Infinity;
        const isSoldOut = item.daily_limit > 0 && remaining <= 0;
        const canAfford = currentPoints >= item.price;
        const isUnavailable = !item.available || isSoldOut;
        const tier = getShopItemTier(item);
        const escapedName = shopEscapeHtml(item.name);
        const escapedDesc = shopEscapeHtml(item.description || '');

        let limitHtml = '';
        if (item.daily_limit > 0) {
          if (isSoldOut) {
            limitHtml = `<div class="shop-item-limit limit-soldout">Сегодня всё разобрали</div>`;
          } else if (remaining === 1) {
            limitHtml = `<div class="shop-item-limit limit-low">Последний слот</div>`;
          } else if (remaining <= 2) {
            limitHtml = `<div class="shop-item-limit limit-medium">Осталось ${remaining} из ${item.daily_limit}</div>`;
          } else {
            limitHtml = `<div class="shop-item-limit">${remaining} из ${item.daily_limit} сегодня</div>`;
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
          btnHtml = `<button class="shop-item-buy no-money" disabled>Нужно +${need} ★</button>`;
        } else {
          btnHtml = `<button class="shop-item-buy" onclick="buyItem('${shopJsArg(item.code)}','${shopJsArg(item.name)}',${item.price})">Купить · ${item.price} ★</button>`;
        }

        html += `<div class="shop-item shop-item-${tier} ${isSoldOut ? 'sold-out' : ''} ${!item.available && !isSoldOut ? 'unavailable' : ''}" data-item-code="${item.code}">
          <div class="shop-item-topline">
            <div class="shop-item-icon">${SHOP_ICONS[item.code] || item.icon || '◇'}</div>
            <div class="shop-item-tier">${getShopTierLabel(tier)}</div>
          </div>
          <div class="shop-item-body">
            <div class="shop-item-name">${escapedName}</div>
            <div class="shop-item-cn">${escapedDesc}</div>
            <div class="shop-item-meta">
              ${limitHtml}
              <span class="shop-item-hint">${getShopItemHint(item)}</span>
            </div>
          </div>
          <div class="shop-item-footer">
            <div>
              <div class="shop-item-price">${item.price} ★</div>
              <div class="shop-item-state">${canAfford ? 'звёзд хватает' : `не хватает ${item.price - currentPoints} ★`}</div>
            </div>
            ${btnHtml}
          </div>
        </div>`;
      });
      html += `</div></section>`;
    }

    document.getElementById('shopStoreContent').innerHTML = html || '<div class="empty-state">Магазин пуст</div>';
    if (typeof applyWildAiShopDisguise === 'function') applyWildAiShopDisguise();
  } catch(e) {
    document.getElementById('shopStoreContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function buyItem(code, name, price) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  if (code === 'title_player') {
    openTitleStyleModal(name, price);
    return;
  }
  safeShowPopup({
    title: `Купить ${name}?`,
    message: `Стоимость: ${price} ★\nТвой баланс: ${currentPoints} ★`,
    buttons: [{id:'confirm',type:'default',text:'✅ Купить'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    await submitShopPurchase(code, name);
  });
}

async function submitShopPurchase(code, name, style) {
  try {
    const body = {telegram_id:currentUserId, item_code:code};
    if (style) body.style = style;
    const r = await fetch(`${API_URL}/api/shop/buy`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    if (r.ok) {
      const data = await r.json();
      currentPoints = data.new_points;
      updatePoints();
      if (typeof handleDiaryUnlocks === 'function') handleDiaryUnlocks(data.diary_unlocked);
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
}

// Title Player ("Титул дня") highlight presets — must match TITLE_STYLE_PRESETS
// on the backend. Purely cosmetic full-row glow on the leaderboard for the day.
const TITLE_STYLE_PRESETS = [
  {id:'cyan',    name:'Кибер-циан'},
  {id:'gold',    name:'Золото протокола'},
  {id:'violet',  name:'Фиолетовый сигнал'},
  {id:'crimson', name:'Багровая тревога'},
  {id:'emerald', name:'Изумрудный канал'},
];

function openTitleStyleModal(name, price) {
  const box = document.getElementById('titleStyleOptions');
  if (box) {
    box.innerHTML = TITLE_STYLE_PRESETS.map(p => `
      <button class="profile-showcase-option" onclick="confirmTitlePlayerPurchase('${p.id}',${price})">
        <span class="profile-frame-swatch title-style-swatch title-${p.id}"></span>
        <span class="profile-showcase-option-copy">
          <span>ПОДСВЕТКА СТРОКИ</span>
          <strong>${p.name}</strong>
          <em>Выделит всю твою строку в рейтинге на сегодня</em>
        </span>
      </button>`).join('');
  }
  const modal = document.getElementById('titleStyleModal');
  if (modal) modal.style.display = 'flex';
}

function closeTitleStyleModal() {
  const modal = document.getElementById('titleStyleModal');
  if (modal) modal.style.display = 'none';
}

async function confirmTitlePlayerPurchase(styleId, price) {
  closeTitleStyleModal();
  safeShowPopup({
    title: 'Купить Титул дня?',
    message: `Стоимость: ${price} ★\nТвой баланс: ${currentPoints} ★`,
    buttons: [{id:'confirm',type:'default',text:'✅ Купить'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    await submitShopPurchase('title_player', 'Титул дня', styleId);
  });
}

const SHOP_CATEGORY_LABEL = {
  living: '🏠 БЫТ', chinese: '🀄 КИТ. КУЛЬТУРА', app: '📱 СЕРВИС',
  reminder: '🔔 НАПОМИНАНИЕ', trade: '🔄 ОБМЕН', privilege: '⚡ ПРИВИЛЕГИЯ', other: '📦 ПРОЧЕЕ',
};

function _bjDateStr(d) {
  // Shift to Beijing (UTC+8) then take the date portion
  const bj = new Date(d.getTime() + (8 * 60 + d.getTimezoneOffset()) * 60000);
  return bj.toISOString().slice(0, 10);
}

function _inventoryExpiryLine(item, sellValue) {
  const bought = new Date(item.purchased_at).toLocaleDateString('ru-RU');
  const base = `Куплено: ${bought} · продажа ${sellValue}★`;
  if (!item.expires_at) return base;
  const now = new Date();
  const todayStr = _bjDateStr(now);
  const tomorrow = new Date(now); tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = _bjDateStr(tomorrow);
  const expDate = item.expires_at.slice(0, 10);
  if (expDate === todayStr)
    return `<span class="inventory-expiry-warn">⚠ Сгорает сегодня в 23:59</span> · продажа ${sellValue}★`;
  if (expDate === tomorrowStr)
    return `<span class="inventory-expiry-soon">↯ Истекает завтра в 23:59</span> · продажа ${sellValue}★`;
  return `${base} · до ${expDate}`;
}

async function loadInventory() {
  try {
    const r = await fetch(`${API_URL}/api/shop/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('shopInventoryContent');
    const digital = ['extra_case','extra_cases','additional_case','case_extra','extra_raid_attempt','double_win','title_player','immunity','raid_insurance','raid_beacon','raid_overclock'];
    const physical = data.filter(item => !digital.includes(item.code));
    if (!physical.length) { container.innerHTML = '<div class="empty-state">Инвентарь пуст<br>Купи что-нибудь в магазине!</div>'; return; }
    const sellRate = typeof hasPandaImplant !== 'undefined' && hasPandaImplant ? 0.6 : 0.5;
    container.innerHTML = physical.map(item => {
      const catLabel = SHOP_CATEGORY_LABEL[item.category] || '📦 ' + (item.category || 'ITEM').toUpperCase();
      const sellValue = Math.floor(item.price * sellRate);
      const tier = item.price >= 500 ? 'LEGEND' : item.price >= 180 ? 'RARE' : 'ITEM';
      const descHtml = item.description ? `<div class="inventory-desc">${item.description}</div>` : '';
      return `<div class="inventory-item inventory-item-shop">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div class="inventory-info">
            <div class="inventory-kicker">${tier} · ${catLabel}</div>
            <div class="inventory-name">${item.name}</div>
            ${descHtml}
            <div class="inventory-date">${_inventoryExpiryLine(item, sellValue)}</div>
          </div>
          <div class="inventory-side">
            <div class="inventory-pill">${item.price}★</div>
          </div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useItem(${item.id},'${shopJsArg(item.name)}')">✅ Использовать</button>
          <button class="inv-btn inv-btn-gift" onclick="giftItem(${item.id},'${shopJsArg(item.name)}')">🎁 Подарить</button>
          <button class="inv-btn inv-btn-sell" onclick="sellItem(${item.id},'${shopJsArg(item.name)}',${item.price})">💰 Продать</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('shopInventoryContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function useItem(id, name) {
  safeShowPopup({
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
        const data = await r.json();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        if (data.new_path) {
          try { localStorage.setItem('zhidao_theme_path', data.new_path); } catch(e) {}
          if (typeof applyThemePath === 'function') applyThemePath(data.new_path);
          const pathLabel = data.new_path === 'genshin' ? 'Геншин ✦' : 'Киберпанк 🏮';
          showToast(`✅ Путь сменён → ${pathLabel}`);
        } else {
          showToast(`✅ ${name} использован!\nПокажи это сообщение вожатому.`);
        }
        loadInventory();
      } else {
        showToast('Ошибка использования');
      }
    } catch(e) { showToast('Ошибка соединения'); }
  });
}
let _giftItemId = null, _giftItemName = null, _giftSelectedUser = null;
let _giftSearchTimer = null, _giftSearchSeq = 0;

function giftItem(id, name) {
  _giftItemId = id;
  _giftItemName = name;
  _giftSelectedUser = null;

  let modal = document.getElementById('giftUserModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'giftUserModal';
    modal.className = 'gift-modal-overlay';
    modal.innerHTML = `
      <div class="gift-modal">
        <div class="gift-modal-header">
          <div>
            <div class="gift-modal-kicker">TRANSFER // 转让</div>
            <div class="gift-modal-title">🎁 Подарить</div>
          </div>
          <button class="gift-modal-close" onclick="closeGiftModal()">✕</button>
        </div>
        <div class="gift-modal-item" id="giftModalItemLabel"></div>
        <div class="gift-modal-tax">Налог на дарение: <b>20★</b> &nbsp;·&nbsp; Лимит: <b>5</b> подарков в день</div>
        <input class="gift-modal-search" id="giftUserSearchInput" placeholder="Поиск по имени..." oninput="giftSearchDebounced()" autocomplete="off" spellcheck="false">
        <div class="gift-modal-results" id="giftUserResults"></div>
        <div class="gift-modal-selected" id="giftSelectedDisplay" style="display:none"></div>
        <div class="gift-modal-actions">
          <button class="inv-btn" style="flex:0 0 auto;padding:9px 18px;" onclick="closeGiftModal()">Отмена</button>
          <button class="inv-btn inv-btn-use gift-modal-confirm" id="giftConfirmBtn" onclick="confirmGift()" disabled>🎁 Подарить</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) closeGiftModal(); });
  }

  document.getElementById('giftModalItemLabel').textContent = name;
  const input = document.getElementById('giftUserSearchInput');
  input.value = '';
  document.getElementById('giftUserResults').innerHTML = '';
  document.getElementById('giftSelectedDisplay').style.display = 'none';
  document.getElementById('giftConfirmBtn').disabled = true;
  _giftSelectedUser = null;
  modal.classList.add('show');
  _giftSearchUsers('');
  setTimeout(() => input.focus(), 120);
}

function closeGiftModal() {
  const m = document.getElementById('giftUserModal');
  if (m) m.classList.remove('show');
}

function giftSearchDebounced() {
  clearTimeout(_giftSearchTimer);
  _giftSearchTimer = setTimeout(() => {
    _giftSearchUsers(document.getElementById('giftUserSearchInput')?.value || '');
  }, 280);
}

async function _giftSearchUsers(q) {
  const container = document.getElementById('giftUserResults');
  if (!container || !currentUserId) return;
  const seq = ++_giftSearchSeq;
  container.innerHTML = '<div class="gift-modal-hint">Поиск...</div>';
  try {
    const r = await fetch(`${API_URL}/api/users/search?q=${encodeURIComponent(q)}&caller_id=${currentUserId}`);
    if (seq !== _giftSearchSeq) return;
    const data = await r.json();
    const users = Array.isArray(data.users) ? data.users : [];
    if (!users.length) {
      container.innerHTML = '<div class="gift-modal-hint">Никого не найдено</div>';
      return;
    }
    container.innerHTML = users.map(u => {
      const initials = (u.full_name || '?')[0].toUpperCase();
      const avatarHtml = u.avatar_url
        ? `<img src="${escapeHtml(u.avatar_url)}" class="gift-user-img" onerror="this.style.display='none'">`
        : `<span class="gift-user-initials">${initials}</span>`;
      const _gn = JSON.stringify(u.full_name).replace(/"/g, '&quot;');
      const _ga = JSON.stringify(u.avatar_url || '').replace(/"/g, '&quot;');
      return `<div class="gift-user-row" onclick="giftSelectUser(${u.telegram_id},${_gn},${_ga})">
        <div class="gift-user-ava">${avatarHtml}</div>
        <div class="gift-user-info">
          <div class="gift-user-name">${u.full_name}</div>
        </div>
        <div class="gift-user-pts">${u.points||0}★</div>
      </div>`;
    }).join('');
  } catch(e) {
    if (seq !== _giftSearchSeq) return;
    container.innerHTML = '<div class="gift-modal-hint">Ошибка соединения</div>';
  }
}

function giftSelectUser(id, name, avatar) {
  _giftSelectedUser = {id, name, avatar};
  document.getElementById('giftUserResults').innerHTML = '';
  document.getElementById('giftUserSearchInput').value = name;
  const display = document.getElementById('giftSelectedDisplay');
  display.style.display = 'flex';
  const initials = (name || '?')[0].toUpperCase();
  const avatarHtml = avatar
    ? `<img src="${escapeHtml(avatar)}" class="gift-user-img" onerror="this.style.display='none'">`
    : `<span class="gift-user-initials">${initials}</span>`;
  display.innerHTML = `
    <div class="gift-user-ava">${avatarHtml}</div>
    <div class="gift-user-info" style="flex:1">
      <div class="gift-user-name">${name}</div>
      <div class="gift-modal-hint" style="margin:0">Выбран получатель</div>
    </div>
    <button class="gift-clear-btn" onclick="giftClearUser()" title="Изменить">✕</button>
  `;
  document.getElementById('giftConfirmBtn').disabled = false;
}

function giftClearUser() {
  _giftSelectedUser = null;
  document.getElementById('giftSelectedDisplay').style.display = 'none';
  document.getElementById('giftUserSearchInput').value = '';
  document.getElementById('giftConfirmBtn').disabled = true;
  _giftSearchUsers('');
}

async function confirmGift() {
  if (!_giftSelectedUser || !_giftItemId || !currentUserId) return;
  const btn = document.getElementById('giftConfirmBtn');
  btn.disabled = true;
  btn.textContent = '...';
  try {
    const r = await fetch(`${API_URL}/api/shop/gift`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({purchase_id: _giftItemId, from_id: currentUserId, to_id: _giftSelectedUser.id})
    });
    const data = await r.json();
    if (r.ok && data.success) {
      closeGiftModal();
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      if (typeof handleDiaryUnlocks === 'function') handleDiaryUnlocks(data.diary_unlocked);
      showToast(`🎁 Подарено: ${_giftItemName} → ${_giftSelectedUser.name}`);
      setTimeout(loadInventory, 500);
    } else {
      btn.disabled = false;
      btn.textContent = '🎁 Подарить';
      const msg = data.detail || '';
      showToast(
        msg === 'Daily gift limit reached' ? 'Лимит подарков на сегодня исчерпан' :
        msg === 'Not enough points for tax' ? 'Не хватает очков для налога (20★)' :
        msg || 'Ошибка при отправке подарка'
      );
    }
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🎁 Подарить';
    showToast('Ошибка соединения');
  }
}

async function sellItem(id, name, price) {
  const pandaActive = typeof hasPandaImplant !== 'undefined' && hasPandaImplant;
  const rate = pandaActive ? 0.6 : 0.5;
  const refund = Math.floor(price * rate);
  const rateLabel = pandaActive ? '60% · Панда 🐼' : '50%';
  safeShowPopup({
    title:`Продать ${name}?`,
    message:`Ты получишь ${refund} ★ (${rateLabel} от стоимости ${price} ★)`,
    buttons:[{id:'confirm',type:'destructive',text:`💰 Продать за ${refund} ★`},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/sell`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purchase_id:id,telegram_id:currentUserId})});
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        const pandaNote = data.sell_rate === 0.6 ? ' · Панда 🐼' : '';
        if (typeof handleDiaryUnlocks === 'function') handleDiaryUnlocks(data.diary_unlocked);
        showToast(`✅ Продано! +${data.refund} ★${pandaNote}`);
        loadInventory();
      }
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
