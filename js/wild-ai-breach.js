// ===== WILD AI BREACH (野生AI入侵) =====
// Глобальный режим хаоса, активируемый при поражении в ивенте Wild AI Breach
// (или вручную админом). Меняет только визуальный слой — функционал не теряется.

let _wildAiBreachActive = false;
let _wildAiBreachNavOriginal = null;
let _wildAiBreachTimerInterval = null;

function seededShuffle(array, seed) {
  const arr = array.slice();
  let s = (seed || 0) + 1;
  for (let i = arr.length - 1; i > 0; i--) {
    s = (s * 9301 + 49297) % 233280;
    const j = Math.floor((s / 233280) * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function applyWildAiBreachState(settings) {
  const active = !!(settings && settings.breach_active);
  _wildAiBreachActive = active;
  document.body.classList.toggle('wild-ai-breach', active);

  if (active) {
    renderWildAiBreachBanner(settings);
    scrambleNavLabels(settings.breach_seed || 0);
  } else {
    removeWildAiBreachBanner();
    restoreNavLabels();
  }

  const status = document.getElementById('adminWildAiBreachStatus');
  if (status) {
    status.textContent = active ? 'STATUS // BREACH ACTIVE (3 ДНЯ)' : 'STATUS // CONTAINED';
    status.classList.toggle('enabled', active);
  }
}

function isWildAiBreachActive() {
  return _wildAiBreachActive;
}

function renderWildAiBreachBanner(settings) {
  let banner = document.getElementById('wildAiBreachBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'wildAiBreachBanner';
    banner.className = 'wild-ai-breach-banner';
    document.body.prepend(banner);
  }
  const phrase = settings.breach_phrase || { glitch: '', translation: '' };
  banner.innerHTML = `
    <div class="wab-line1">SYSTEM ERROR // BLACKWALL: ОФФЛАЙН</div>
    <div class="wab-line2">${phrase.glitch}<span class="wab-translation"> — "${phrase.translation}"</span></div>
    <div class="wab-timer" id="wildAiBreachTimer"></div>
  `;

  const until = settings.breach_until ? new Date(settings.breach_until) : null;
  if (until) startWildAiBreachTimer(until);
}

function startWildAiBreachTimer(until) {
  if (_wildAiBreachTimerInterval) clearInterval(_wildAiBreachTimerInterval);
  const update = () => {
    const el = document.getElementById('wildAiBreachTimer');
    if (!el) return;
    const diff = until.getTime() - Date.now();
    if (diff <= 0) {
      el.textContent = 'ВОССТАНОВЛЕНИЕ СИСТЕМЫ...';
      return;
    }
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    el.textContent = `ВОССТАНОВЛЕНИЕ: ${d}д ${h}ч ${m}м`;
  };
  update();
  _wildAiBreachTimerInterval = setInterval(update, 30000);
}

function removeWildAiBreachBanner() {
  const banner = document.getElementById('wildAiBreachBanner');
  if (banner) banner.remove();
  if (_wildAiBreachTimerInterval) {
    clearInterval(_wildAiBreachTimerInterval);
    _wildAiBreachTimerInterval = null;
  }
}

function scrambleNavLabels(seed) {
  const spans = Array.from(document.querySelectorAll('.bottom-nav .nav-cn'));
  if (!spans.length) return;
  if (!_wildAiBreachNavOriginal) {
    _wildAiBreachNavOriginal = spans.map(s => s.textContent);
  }
  const shuffled = seededShuffle(_wildAiBreachNavOriginal, seed);
  spans.forEach((s, i) => { s.textContent = shuffled[i]; });
}

function restoreNavLabels() {
  if (!_wildAiBreachNavOriginal) return;
  const spans = Array.from(document.querySelectorAll('.bottom-nav .nav-cn'));
  spans.forEach((s, i) => { s.textContent = _wildAiBreachNavOriginal[i]; });
}
