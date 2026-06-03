(function initDemoMode() {
  const params = new URLSearchParams(window.location.search || '');
  isDemoMode = params.has('demo');
  window.DEMO_MODE = isDemoMode;
  if (!isDemoMode) return;

  const DEMO_ID = 900000001;
  const DEMO_USER = {
    id: DEMO_ID,
    first_name: 'Демо',
    last_name: 'Участник',
    username: 'zhidao_demo',
  };

  currentUserId = DEMO_ID;
  currentPoints = 1280;
  currentThemePath = 'cyberpunk';
  isAdmin = false;
  isArchitect = false;

  try {
    if (tg && tg.initDataUnsafe) tg.initDataUnsafe.user = DEMO_USER;
  } catch (e) {}

  function demoPopup(title = 'Демо-режим', message = 'Эта функция откроется после запуска поездки.') {
    try {
      tg.showPopup({
        title,
        message,
        buttons: [{ type: 'ok', text: 'Понятно' }],
      });
    } catch (e) {
      alert(`${title}\n${message}`);
    }
  }

  function demoCard(title, body, icon = '◇') {
    return `<div class="demo-card">
      <div class="demo-card-icon">${icon}</div>
      <div>
        <div class="demo-card-title">${escapeHtml(title)}</div>
        <div class="demo-card-body">${escapeHtml(body)}</div>
      </div>
    </div>`;
  }

  function installDemoBanner() {
    if (document.getElementById('demoModeBanner')) return;
    const banner = document.createElement('div');
    banner.id = 'demoModeBanner';
    banner.className = 'demo-mode-banner';
    banner.innerHTML = `<b>DEMO ACCESS</b><span>витрина без записи в систему</span>`;
    document.body.prepend(banner);
    document.body.classList.add('demo-mode');
  }

  function installCatalogLocks() {
    const catalog = document.getElementById('implants-catalog');
    if (catalog) {
      catalog.style.display = 'none';
      if (!document.getElementById('demoImplantCatalogLock')) {
        const lock = document.createElement('div');
        lock.id = 'demoImplantCatalogLock';
        lock.className = 'demo-catalog-lock';
        lock.innerHTML = `<div class="demo-lock-kicker">CATALOG SEALED</div>
          <div class="demo-lock-title">Каталог имплантов скрыт</div>
          <div class="demo-lock-copy">Полный список имплантов и пассивок откроется только участникам после запуска поездки.</div>`;
        catalog.parentElement.insertBefore(lock, catalog);
      }
    }

    const cardsTab = document.getElementById('cards-tab');
    const exchange = document.getElementById('fragment-exchange-card-block');
    if (cardsTab && exchange && !document.getElementById('demoCardCatalogLock')) {
      let node = exchange.nextElementSibling;
      while (node) {
        node.style.display = 'none';
        node = node.nextElementSibling;
      }
      const lock = document.createElement('div');
      lock.id = 'demoCardCatalogLock';
      lock.className = 'demo-catalog-lock';
      lock.innerHTML = `<div class="demo-lock-kicker">CARD ARCHIVE LOCKED</div>
        <div class="demo-lock-title">Каталог карточек скрыт</div>
        <div class="demo-lock-copy">Карточки можно увидеть как пример владения, но полный архив не раскрывается в демо.</div>`;
      exchange.insertAdjacentElement('afterend', lock);
    }
  }

  window.installDemoCatalogLocks = installCatalogLocks;

  function renderDemoProfile() {
    const status = document.getElementById('status');
    const username = document.getElementById('username');
    const serverTag = document.getElementById('serverTag');
    const trafficValue = document.getElementById('trafficValue');
    const progressFill = document.getElementById('progressFill');
    if (status) {
      status.textContent = '● DEMO NODE';
      status.style.color = '#d4af37';
    }
    if (username) username.textContent = 'Демо-участник';
    if (serverTag) serverTag.textContent = 'PREVIEW MODE // данные не сохраняются';
    if (trafficValue) trafficValue.textContent = '— GB';
    if (progressFill) setTimeout(() => { progressFill.style.width = '18%'; }, 150);

    if (typeof renderProfileAvatarCard === 'function') {
      renderProfileAvatarCard({
        full_name: 'Демо-участник',
        username: 'zhidao_demo',
        avatar_url: '',
      });
    }
  }

  function renderDemoProfileDossier() {
    if (typeof renderProfileDossier !== 'function') return;
    renderProfileDossier({
      full_name: 'Демо-участник',
      theme_path: 'cyberpunk',
      rank: 'B',
      leaderboard_rank: 7,
      title: 'Кандидат протокола / Preview',
      status_line: '状态：DEMO // доступ: витрина // запись: отключена',
      showcase: {
        kind: 'implant',
        name: 'Linguasoft 口才',
        glyph: '言',
        detail: 'пример активного предмета',
      },
      stats: {
        case_opens: 4,
        prayers: 2,
        cards: 1,
        implants: 2,
        diaries: 3,
        raids: 1,
      },
    });
  }

  window.loadUserData = async function loadDemoUserData() {
    renderDemoProfile();
    renderDemoProfileDossier();
    if (typeof syncAdminUiVisibility === 'function') syncAdminUiVisibility();
    hideStartupCover();
  };

  window.loadPoints = async function loadDemoPoints() {
    currentPoints = 1280;
    updatePoints();
    if (typeof applyThemePath === 'function') applyThemePath('cyberpunk');
    renderDemoProfileDossier();
  };

  window.loadProfileDossier = async function loadDemoProfileDossier() {
    renderDemoProfileDossier();
  };

  window.loadAchievements = async function loadDemoAchievements() {
    const container = document.getElementById('achievementsContent');
    if (!container) return;
    const items = [
      ['early_bird', 'Ранний подъём', 'Демо: отметка без опоздания', true],
      ['helper', 'Помощник группы', 'Демо: помощь участнику', true],
      ['polyglot', 'Полиглот', 'Демо: прогресс в китайском', false],
      ['legend', 'Легенда протокола', 'Демо: высокий REP', false],
    ];
    container.innerHTML = `<div class="achievement-count">// Демо-витрина: <b style="color:var(--gold)">2</b> из 4</div>
      <div class="achievements-grid">${items.map(([code, name, desc, earned]) => {
        const svgIcon = ACHIEVEMENT_ICONS[code] || `<svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="20" fill="rgba(212,175,55,0.3)"/></svg>`;
        return `<div class="achievement-card ${earned ? '' : 'locked'}" onclick="showAchievementInfo(${JSON.stringify(name)},${JSON.stringify(desc)},${earned})">
          ${earned ? '<div class="achievement-earned-badge">DEMO</div>' : ''}
          <div class="achievement-svg">${svgIcon}</div>
          <div class="achievement-name">${escapeHtml(name)}</div>
        </div>`;
      }).join('')}</div>`;
  };

  window.loadLeaderboard = async function loadDemoLeaderboard() {
    const container = document.getElementById('leaderboardContent');
    if (!container) return;
    const rows = [
      ['🥇', 'Альфа протокола', 420, 'GENSHIN', 'genshin', 'top1'],
      ['🥈', 'Оператор Дозора', 390, 'NETWATCH', 'netwatch', 'top2'],
      ['🥉', 'Страж дневника', 350, 'GENSHIN', 'genshin', 'top3'],
      ['#7', 'Демо-участник', 180, 'NETWATCH', 'netwatch', 'me'],
    ];
    container.innerHTML = `<div class="demo-note">Демо-рейтинг показывает пример интерфейса. Реальные места появятся после поездки.</div>
      ${rows.map(([rank, name, rep, pathLabel, pathClass, cls]) => `<div class="lb-item ${cls}">
        <div class="lb-rank">${rank}</div>
        <div class="lb-avatar"><span class="lb-avatar-fallback">${escapeHtml(name[0])}</span></div>
        <div class="lb-name-wrap">
          <div class="lb-name-row"><div class="lb-name">${escapeHtml(name)}</div><span class="lb-path-badge ${pathClass}">${pathLabel}</span></div>
          <div class="lb-subline"><span>DEMO SIGNAL</span><span>${cls === 'me' ? 'это ты' : 'пример'}</span></div>
        </div>
        <div class="lb-points">${rep} REP</div>
      </div>`).join('')}`;
  };

  window.loadShop = async function loadDemoShop() {
    const container = document.getElementById('shopStoreContent');
    if (!container) return;
    const items = [
      ['Иммунитет', 'Блокирует один штраф', '🛡', 150],
      ['Доп. кейс', '+1 попытка кейса', '📦', 80],
      ['Смена пути 转换', 'Переключиться между NetWatch и Genshin', '🔁', 500],
      ['Bubble Tea', 'маленькая приятность', '🥤', 120],
    ];
    document.getElementById('shopPoints').textContent = currentPoints + ' ★';
    container.innerHTML = `<div class="demo-note">Магазин открыт как витрина. Покупки в демо не списывают звёзды.</div>
      <div class="shop-grid-modern">${items.map(([name, desc, icon, price]) => `<div class="shop-item">
        <div class="shop-item-topline"><div class="shop-item-icon">${icon}</div><div class="shop-item-tier">DEMO</div></div>
        <div class="shop-item-body">
          <div class="shop-item-name">${escapeHtml(name)}</div>
          <div class="shop-item-cn">${escapeHtml(desc)}</div>
          <div class="shop-item-meta"><div class="shop-item-limit">preview only</div><span class="shop-item-hint">витрина</span></div>
        </div>
        <div class="shop-item-footer"><div><div class="shop-item-price">${price} ★</div><div class="shop-item-state">демо-баланс</div></div>
          <button class="shop-item-buy" onclick="demoBlockedAction('Покупка')">Посмотреть</button>
        </div>
      </div>`).join('')}</div>`;
  };

  window.loadInventory = async function loadDemoInventory() {
    const container = document.getElementById('shopInventoryContent');
    if (!container) return;
    container.innerHTML = `${demoCard('Смена пути 转换', 'Пример предмета из магазина. В демо использование заблокировано.', '🔁')}
      ${demoCard('Иммунитет', 'Пример защитного предмета.', '🛡')}`;
  };

  window.loadImplants = async function loadDemoImplants() {
    const home = document.getElementById('homeImplants');
    const page = document.getElementById('myImplantsPage');
    const html = `${demoCard('Linguasoft 口才', '+30★ за сильный дневник. Пример установленного импланта.', '言')}
      ${demoCard('Панда 🐼', 'Кэшбек и улучшенная продажа предметов. Пример установленного импланта.', '熊')}`;
    if (home) home.innerHTML = html;
    if (page) page.innerHTML = html;
    installCatalogLocks();
  };

  window.loadCards = async function loadDemoCards() {
    const container = document.getElementById('myCardsContent');
    if (!container) return;
    container.innerHTML = demoCard('九尾狐灵 Лиса-Оборотень', 'Пример карточки. Полный каталог скрыт до запуска.', '狐');
    installCatalogLocks();
  };

  window.openContractsPage = function openDemoContractsPage() {
    const openList = document.getElementById('contractsOpenList');
    const myList = document.getElementById('contractsMyList');
    const disputedList = document.getElementById('contractsDisputedList');
    const main = document.getElementById('contractsMain');
    const bw = document.getElementById('contractsBlackwallMsg');
    if (main) main.style.display = 'block';
    if (bw) bw.style.display = 'none';
    if (openList) openList.innerHTML = `<div class="demo-note">Демо-доска показывает механику поручений без создания настоящих заказов.</div>
      ${demoCard('Помоги повторить 5 китайских фраз', 'Награда: 20★ · исполнитель получит 18★ после комиссии.', '契')}
      ${demoCard('Напомни сдать дневник вечером', 'Награда: 10★ · категория: Напоминание.', '契')}`;
    if (myList) myList.innerHTML = demoCard('Моё демо-поручение', 'Статус: принято. В реальном режиме тут появятся твои заказы.', '契');
    if (disputedList) disputedList.innerHTML = demoCard('Спорных поручений нет', 'В споре админ решает: возврат, выплата, раздел или сжигание.', '!');
  };

  window.startContractsAutoRefresh = function startDemoContractsAutoRefresh() {};
  window.stopContractsAutoRefresh = function stopDemoContractsAutoRefresh() {};
  window.refreshContractsActiveTab = function refreshDemoContractsActiveTab() {};
  window.refreshContractsAfterAction = function refreshDemoContractsAfterAction() {};
  window.loadOpenContracts = async function loadDemoOpenContracts() {
    openContractsPage();
  };
  window.loadMyContracts = async function loadDemoMyContracts() {
    openContractsPage();
  };
  window.showContractsTab = function showDemoContractsTab(tab) {
    contractsActiveTab = ['my', 'disputed'].includes(tab) ? tab : 'open';
    const openEl = document.getElementById('contracts-tab-open');
    const myEl = document.getElementById('contracts-tab-my');
    const disputedEl = document.getElementById('contracts-tab-disputed');
    const btnOpen = document.getElementById('ctab-open');
    const btnMy = document.getElementById('ctab-my');
    const btnDisputed = document.getElementById('ctab-disputed');
    if (openEl) openEl.style.display = contractsActiveTab === 'open' ? 'block' : 'none';
    if (myEl) myEl.style.display = contractsActiveTab === 'my' ? 'block' : 'none';
    if (disputedEl) disputedEl.style.display = contractsActiveTab === 'disputed' ? 'block' : 'none';
    if (btnOpen) btnOpen.classList.toggle('active', contractsActiveTab === 'open');
    if (btnMy) btnMy.classList.toggle('active', contractsActiveTab === 'my');
    if (btnDisputed) btnDisputed.classList.toggle('active', contractsActiveTab === 'disputed');
    openContractsPage();
  };

  window.loadDiaryPage = async function loadDemoDiaryPage() {
    const el = document.getElementById('diaryContent');
    if (el) el.innerHTML = `${demoCard('Дневник закрыт в демо', 'Форма видна как пример, но отправка записей отключена.', '日')}`;
    const page = document.getElementById('page-diary');
    if (page && !document.getElementById('demoDiaryNotice')) {
      const note = document.createElement('div');
      note.id = 'demoDiaryNotice';
      note.className = 'demo-note';
      note.textContent = 'Дневник показан как демо-форма. Сохранение, отправка и админские оценки в этом режиме не записываются.';
      const header = page.querySelector('.page-header');
      if (header) header.insertAdjacentElement('afterend', note);
    }
  };

  window.initDiaryStarsPage = function initDemoDiaryStarsPage() {
    const el = document.getElementById('diaryStarsContent');
    if (el) el.innerHTML = `${demoCard('Оценка дневников', 'В демо нельзя начислить реальные звёзды.', '★')}`;
    const page = document.getElementById('page-diary-stars');
    if (page && !document.getElementById('demoDiaryStarsNotice')) {
      const note = document.createElement('div');
      note.id = 'demoDiaryStarsNotice';
      note.className = 'demo-note';
      note.textContent = 'Оценка дневников в демо отключена. Настоящие начисления будут доступны только администраторам.';
      const header = page.querySelector('.page-header');
      if (header) header.insertAdjacentElement('afterend', note);
    }
  };

  window.demoBlockedAction = function demoBlockedAction(action = 'Действие') {
    demoPopup(action, 'Демо-режим только показывает интерфейс. Реальные действия откроются после запуска поездки.');
  };

  window.buyItem = async function demoBuyItem() { demoBlockedAction('Покупка'); };
  window.useItem = function demoUseItem() { demoBlockedAction('Использование предмета'); };
  window.sellItem = async function demoSellItem() { demoBlockedAction('Продажа предмета'); };
  window.giftItem = function demoGiftItem() { demoBlockedAction('Подарок'); };
  window.openCase = async function demoOpenCase() { demoBlockedAction('Кейс'); };
  window.openGenshinCase = async function demoOpenGenshinCase() { demoBlockedAction('Молитва'); };
  window.submitDiary = async function demoSubmitDiary() { demoBlockedAction('Дневник'); };
  window.submitDiaryStars = async function demoSubmitDiaryStars() { demoBlockedAction('Оценка дневника'); };
  window.saveDiaryDraft = async function demoSaveDiaryDraft() { demoBlockedAction('Сохранение дневника'); };
  window.saveDiaryToAPI = async function demoSaveDiaryToAPI() { demoBlockedAction('Сохранение дневника'); return false; };
  window.scoreDiary = async function demoScoreDiary() { demoBlockedAction('Оценка дневника'); };
  window.lockDiaryEntry = async function demoLockDiaryEntry() { demoBlockedAction('Блокировка дневника'); };
  window.resetDiaryForCurrentDate = function demoResetDiaryForCurrentDate() { demoBlockedAction('Сброс дневника'); };
  window.submitCreateContract = async function demoSubmitCreateContract() { demoBlockedAction('Создание поручения'); };
  window.acceptContract = async function demoAcceptContract() { demoBlockedAction('Принятие поручения'); };
  window.completeContract = async function demoCompleteContract() { demoBlockedAction('Подтверждение поручения'); };
  window.cancelContract = async function demoCancelContract() { demoBlockedAction('Отмена поручения'); };
  window.disputeContract = async function demoDisputeContract() { demoBlockedAction('Спор'); };
  window.joinRaid = async function demoJoinRaid() { demoBlockedAction('Рейд'); };
  window.exchangeFragments = async function demoExchangeFragments() { demoBlockedAction('Обмен фрагментов'); };
  window.loadCasinoStatus = async function loadDemoCasinoStatus() {
    scanAttempts = 2;
    protocolFragments = 6;
    if (typeof updateFragmentCounters === 'function') updateFragmentCounters(protocolFragments);
    if (typeof updateCaseButton === 'function') updateCaseButton({ scan_attempts: scanAttempts, protocol_fragments: protocolFragments });
  };
  window.chooseThemePath = async function demoChooseThemePath(path) {
    demoBlockedAction('Выбор пути');
    if (typeof applyThemePath === 'function') applyThemePath(path || 'cyberpunk');
  };

  document.addEventListener('DOMContentLoaded', () => {
    installDemoBanner();
    installCatalogLocks();
    if (typeof applyThemePath === 'function') applyThemePath('cyberpunk');
  });
})();
