(function initDemoMode() {
  const params = new URLSearchParams(window.location.search || '');
  isDemoMode = params.has('demo') || !!window.ZHIDAO_FORCE_DEMO;
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

  const SITE_INTRO_SRC = './cyberpunktheme_intro.mp4';
  let siteIntroPlaying = false;

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

  function demoLockedCard(title = 'Откроется в Пекине', body = 'Раздел скрыт в демо-версии, чтобы не раскрывать игровые механики до поездки.') {
    return `<div class="demo-catalog-lock demo-section-lock">
      <div class="demo-lock-kicker">BEIJING ACCESS ONLY</div>
      <div class="demo-lock-title">${escapeHtml(title)}</div>
      <div class="demo-lock-copy">${escapeHtml(body)}</div>
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

  function finishSiteIntro() {
    if (!siteIntroPlaying) return;
    siteIntroPlaying = false;
    const overlay = document.getElementById('siteIntroOverlay');
    const video = document.getElementById('siteIntroVideo');
    if (video) {
      video.onended = null;
      video.onerror = null;
      video.pause();
    }
    if (!overlay) return;
    overlay.classList.add('closing');
    setTimeout(() => {
      overlay.style.display = 'none';
      overlay.classList.remove('closing');
      if (video) video.removeAttribute('src');
    }, 420);
  }

  window.skipSiteIntro = function skipSiteIntro() {
    finishSiteIntro();
  };

  function playSiteIntroIfNeeded() {
    const forceIntro = params.has('intro');
    if (!forceIntro && sessionStorage.getItem('zhidao_demo_site_intro_done')) return;
    const overlay = document.getElementById('siteIntroOverlay');
    const video = document.getElementById('siteIntroVideo');
    if (!overlay || !video) return;

    sessionStorage.setItem('zhidao_demo_site_intro_done', '1');
    siteIntroPlaying = true;
    overlay.style.display = 'flex';
    overlay.classList.remove('closing');
    video.pause();
    video.src = SITE_INTRO_SRC;
    video.currentTime = 0;
    video.onended = finishSiteIntro;
    video.onerror = finishSiteIntro;

    const playPromise = video.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => setTimeout(finishSiteIntro, 1400));
    }
    setTimeout(finishSiteIntro, 9000);
  }

  function installDemoSpoilerLocks() {
    document.body.classList.add('demo-mode');

    const teamItem = document.querySelector(".more-item[onclick=\"openMore('team')\"]");
    if (teamItem) teamItem.style.display = 'none';

    const teamSection = document.getElementById('more-team');
    if (teamSection) teamSection.style.display = 'none';

    const casinoNav = document.querySelector(".nav-item[onclick=\"showPage('casino',this)\"]");
    if (casinoNav) casinoNav.style.display = 'none';

    const showcaseBtn = document.querySelector('.profile-card-actions .profile-mini-btn');
    if (showcaseBtn) showcaseBtn.style.display = 'none';

    const showcaseText = document.getElementById('profileShowcaseText');
    if (showcaseText) showcaseText.textContent = 'SHOWCASE: LOCKED // Beijing launch';

    const casinoPage = document.getElementById('page-casino');
    if (casinoPage && !document.getElementById('demoCasinoLock')) {
      const header = casinoPage.querySelector('.page-header');
      const lock = document.createElement('div');
      lock.id = 'demoCasinoLock';
      lock.innerHTML = demoLockedCard('Кейсы откроются в Пекине', 'Система призов, шансов и редких предметов скрыта в демо. На подготовительном курсе показываем только общий интерфейс.');
      if (header) header.insertAdjacentElement('afterend', lock);
    }
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
          <div class="demo-lock-title">Импланты откроются в Пекине</div>
          <div class="demo-lock-copy">Каталог, пассивки и редкие эффекты скрыты в демо-версии.</div>`;
        catalog.parentElement.insertBefore(lock, catalog);
      }
    }

    const cardsTab = document.getElementById('cards-tab');
    const exchange = document.getElementById('fragment-exchange-card-block');
    if (exchange) exchange.style.display = 'none';
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
        <div class="demo-lock-title">Карточки откроются в Пекине</div>
        <div class="demo-lock-copy">Архив карточек, редкости и пассивки скрыты до официального запуска.</div>`;
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
        kind: 'locked',
        name: 'Beijing launch',
        glyph: '禁',
        detail: 'showcase hidden',
      },
      stats: {
        case_opens: 0,
        prayers: 0,
        cards: 0,
        implants: 0,
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
      ['#1', 'Участник №1', 420, 'PATH HIDDEN', 'netwatch', 'top1'],
      ['#2', 'Участник №2', 390, 'PATH HIDDEN', 'netwatch', 'top2'],
      ['#3', 'Участник №3', 350, 'PATH HIDDEN', 'netwatch', 'top3'],
      ['#7', 'Демо-профиль', 180, 'PREVIEW', 'netwatch', 'me'],
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
      ['Базовый товар', 'Пример карточки товара без раскрытия реального каталога', '◇', 120],
      ['Сервисный бонус', 'Пример цифрового предмета. Покупки отключены.', '◇', 150],
      ['Смена пути 转换', 'Пример настройки профиля. Использование отключено.', '◇', 500],
      ['Пекинский слот', 'Реальные товары появятся после запуска.', '◇', 200],
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
    container.innerHTML = demoLockedCard('Инвентарь откроется в Пекине', 'В демо не показываем реальные предметы, подарки и накопленные игровые ресурсы.');
  };

  window.loadImplants = async function loadDemoImplants() {
    const home = document.getElementById('homeImplants');
    const page = document.getElementById('myImplantsPage');
    const html = demoLockedCard('Импланты откроются в Пекине', 'Установленные импланты, пассивки и легендарные действия скрыты в демо.');
    if (home) home.innerHTML = html;
    if (page) page.innerHTML = html;
    installCatalogLocks();
  };

  window.loadCards = async function loadDemoCards() {
    const container = document.getElementById('myCardsContent');
    if (!container) return;
    container.innerHTML = demoLockedCard('Карточки откроются в Пекине', 'Коллекция, редкости и эффекты скрыты до официального запуска.');
    installCatalogLocks();
  };

  window.openProfileShowcaseModal = function openDemoProfileShowcaseModal() {
    demoBlockedAction('Витрина профиля');
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
    installDemoSpoilerLocks();
  };
  window.chooseThemePath = async function demoChooseThemePath(path) {
    demoBlockedAction('Выбор пути');
    if (typeof applyThemePath === 'function') applyThemePath(path || 'cyberpunk');
  };

  if (typeof showPage === 'function') {
    const realShowPage = showPage;
    window.showPage = function showDemoPage(name, btn) {
      if (name === 'casino') {
        realShowPage(name, btn);
        setTimeout(installDemoSpoilerLocks, 0);
        return;
      }
      realShowPage(name, btn);
      setTimeout(() => {
        installCatalogLocks();
        installDemoSpoilerLocks();
      }, 0);
    };
  }

  if (typeof openMore === 'function') {
    const realOpenMore = openMore;
    window.openMore = function openDemoMore(section) {
      if (section === 'team') {
        demoBlockedAction('Команда');
        installDemoSpoilerLocks();
        return;
      }
      realOpenMore(section);
      setTimeout(installDemoSpoilerLocks, 0);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    installDemoBanner();
    installCatalogLocks();
    installDemoSpoilerLocks();
    if (typeof applyThemePath === 'function') applyThemePath('cyberpunk');
    setTimeout(() => {
      installCatalogLocks();
      installDemoSpoilerLocks();
    }, 250);
    setTimeout(() => {
      installCatalogLocks();
      installDemoSpoilerLocks();
    }, 900);
    setTimeout(playSiteIntroIfNeeded, 120);
  });
})();
