let currentUserId = null;
let currentThemePath = null; // "cyberpunk" | "genshin" | null
let isDemoMode = false;
let currentPoints = 0;
let currentAvatarUrl = null;
let userConfig = null;
let isAdmin = false;
let isArchitect = false;
let isSpinning = false;
let selectedLaundryDate = null;
let laundryData = [];
let shopMode = 'store';
let currentMoreSection = null;
let currentArchitectEvent = null;
let currentArchitectEventId = null;
let globalAlertPollingHandle = null;
let casinoPlayOriginalMarkup = '';
let casinoGenshinOriginalMarkup = '';
let shopStoreOriginalMarkup = '';


const COHORT_BEIJING = 'beijing';
const COHORT_MJU = 'mju';
const MJU_SCOPED_ADMIN_ID = 244487659;

function normalizeClientCohort(value) {
  return value === COHORT_MJU ? COHORT_MJU : COHORT_BEIJING;
}

function readSavedAdminCohort() {
  try {
    return normalizeClientCohort(localStorage.getItem('zhidao_admin_cohort'));
  } catch (e) {
    return COHORT_BEIJING;
  }
}

let currentUserCohort = COHORT_BEIJING;
let selectedAdminCohort = readSavedAdminCohort();

function isMjuScopedAdmin() {
  return Number(currentUserId) === MJU_SCOPED_ADMIN_ID;
}

function getActiveCohortCode() {
  if (isMjuScopedAdmin()) return COHORT_MJU;
  if (isAdmin) return normalizeClientCohort(selectedAdminCohort);
  return normalizeClientCohort(currentUserCohort);
}

function initializeCohortStateForUser() {
  if (isMjuScopedAdmin()) {
    currentUserCohort = COHORT_MJU;
    selectedAdminCohort = COHORT_MJU;
  }
  syncAdminCohortUi();
}

function syncUserCohortFromPayload(payload) {
  const cohort = normalizeClientCohort(payload?.cohort_code);
  currentUserCohort = isMjuScopedAdmin() ? COHORT_MJU : cohort;
  syncAdminCohortUi();
}

function syncAdminCohortUi() {
  const switcher = document.getElementById('adminCohortSwitcher');
  if (!switcher) return;

  const activeCohort = getActiveCohortCode();
  const locked = isMjuScopedAdmin();
  switcher.classList.toggle('is-locked', locked);
  switcher.querySelectorAll('[data-cohort]').forEach((button) => {
    const cohort = normalizeClientCohort(button.dataset.cohort);
    button.classList.toggle('active', cohort === activeCohort);
    button.disabled = locked;
    button.hidden = locked && cohort !== COHORT_MJU;
  });

  const label = document.getElementById('adminCohortLabel');
  if (label) {
    label.textContent = locked
      ? 'МЮ // закреплено за Альфабоссом'
      : (activeCohort === COHORT_MJU ? 'МЮ // Шанхай' : 'Пекин // основной контур');
  }
}

function setAdminCohort(cohortCode) {
  if (!isAdmin) return;
  const nextCohort = isMjuScopedAdmin()
    ? COHORT_MJU
    : normalizeClientCohort(cohortCode);
  if (nextCohort === getActiveCohortCode()) {
    syncAdminCohortUi();
    return;
  }

  selectedAdminCohort = nextCohort;
  try {
    localStorage.setItem('zhidao_admin_cohort', nextCohort);
  } catch (e) {}
  syncAdminCohortUi();
  try {
    tg.HapticFeedback.selectionChanged();
  } catch (e) {}
  window.setTimeout(() => window.location.reload(), 80);
}
