/**
 * ZHIDAO Protocol — Операторы Управления Контуром
 */

const TEAM_DATA = [
  {
    id: "mju",
    name: "Михаил Юрьевич",
    codename: "МЮ",
    role: "АЛЬФА СТАИ",
    short: "Хранитель и босс. Отвечает за дисциплину, сборы, правила и стабильность группы. Его задача — не дать поездке уйти в хаос",
    status: "ACTIVE_NODE",
    statusText: "BIG BROTHER CONTROL // АЛЬФАБОСС",
    color: "#ff003c",
    // avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/team_mju.png"
    avatar: "👑"
    // tgLink намеренно не указан
  },
  {
    id: "architect",
    name: "Марк Альбертович",
    codename: "Архитектор",
    role: "СИГМА ВОЖАТЫЙ",
    short: "Сисадмин, как тот чел из фильма Matrix. Что-то не работает? Пишите",
    status: "HOST",
    statusText: "ERROR // ERROR",
    color: "#00ff66",
    avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architector_logo.png",
    tgLink: "https://t.me/christianpastor"
  },
  {
    id: "liza",
    name: "Елизавета Сергеевна",
    codename: "Инь-янь",
    role: "СИГМА ВОЖАТАЯ",
    short: "Помогает понимать правила, ориентироваться в поездке и чувствовать комфорт",
    status: "ACTIVE_NODE",
    statusText: "EQUILIBRIUM SUPPORT // РАВНОВЕСИЕ",
    color: "#00f0ff",
    // avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/team_liza.png"
    avatar: "💬",
    tgLink: "https://t.me/naoayako"
  },
  {
    id: "tianhao",
    name: "Сунь Тяньхао",
    codename: "孙舒珩",
    role: "СИГМА ВОЖАТЫЙ",
    short: "Китайский товарищ. Связывает группу с реальным Китаем: языком, городом, маршрутами и местной китайской логикой",
    status: "FIELD_PROXY",
    statusText: "PEK-NODE DISPATCH // ЛОКАЛ",
    color: "#ffaa00",
    // avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/team_tianhao.png"
    avatar: "🏮",
    tgLink: "https://t.me/suntianhao"
  },
  {
    id: "wunan",
    name: "Ву Нан",
    codename: "Ву Нан",
    role: "СИГМА ВОЖАТАЯ",
    short: "Помогает с сопровождением и дисциплиной группы",
    status: "ACTIVE_NODE",
    statusText: "SUPPORT NODE // СОПРОВОЖДЕНИЕ",
    color: "#9b6bff",
    avatar: "🧭",
    tgLink: "https://t.me/nannan_vu"
  },
  {
    id: "olga",
    name: "Ольга Михайловна",
    codename: "SUPPORT",
    role: "СИГМА ВОЖАТАЯ",
    short: "Помогает с сопровождением и дисциплиной группы",
    status: "ACTIVE_NODE",
    statusText: "SUPPORT NODE // СОПРОВОЖДЕНИЕ",
    color: "#ffd23f",
    avatar: "🔑",
    tgLink: "https://t.me/helga_kul"
  },
  {
    id: "yulia",
    name: "Юлия Витальевна",
    codename: "Мудрец Шести Путей Китая",
    role: "АЛЬФА ВОЖАТАЯ",
    short: "В нашем сердечке. Поправляйтесь скорее!",
    status: "DEEP_WEB",
    statusText: "REMOTE ORBIT // НЕВИДИМЫЙ ОПЕРАТОР",
    color: "#fa00ff",
    // avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/team_yulia.png"
    avatar: "🛡️",
    tgLink: "https://t.me/Trufanova_Yulia"
  },
];

function _buildTeamCard(member) {
  const avatarHtml = member.avatar.startsWith('http')
    ? `<div class="no-leak-bg" style="width:100%;height:100%;background-image:url('${escapeHtml(member.avatar)}')" oncontextmenu="return false"></div>`
    : member.avatar;

  return `
    <div class="card team-card-item" style="border-left:4px solid ${member.color};margin-bottom:10px;">
      <div class="card-inner" style="padding:12px 14px;">
        <div style="display:flex;gap:12px;align-items:flex-start;">
          <div class="team-card-avatar" style="border-color:${member.color}88;box-shadow:0 0 10px ${member.color}33;">
            ${avatarHtml}
          </div>
          <div style="flex:1;min-width:0;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:4px;flex-wrap:wrap;">
              <div style="font-size:11px;font-family:monospace;color:${member.color};letter-spacing:1px;font-weight:700;">
                ${member.codename.toUpperCase()} // ${member.status}
              </div>
              <span class="team-card-status-badge">${member.statusText}</span>
            </div>
            <div class="team-card-name">${member.name}</div>
            <div style="font-size:10px;color:var(--text2);font-style:italic;margin-top:1px;">${member.role}</div>
          </div>
        </div>
        <div class="team-card-desc">${member.short}</div>
        ${member.tgLink ? `
        <button onclick="try{tg.openLink('${member.tgLink}')}catch(e){window.open('${member.tgLink}')}"
          class="team-card-btn" style="border-color:${member.color}44;color:${member.color};">
          联系 // НАПИСАТЬ
        </button>` : ''}
      </div>
    </div>`;
}

function renderTeamCards() {
  const visible = TEAM_DATA.filter(m => !m.hidden || (typeof isAdmin !== 'undefined' && isAdmin));
  const html = visible.map(_buildTeamCard).join('');
  const el = document.getElementById('teamCardsContainerFull');
  if (el) el.innerHTML = html;
}

window.addEventListener('DOMContentLoaded', () => setTimeout(renderTeamCards, 300));
