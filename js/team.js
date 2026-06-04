/**
 * ZHIDAO Protocol — Операторы Управления Контуром
 */

const TEAM_DATA = [
  {
    id: "architect",
    name: "Марк Альбертович",
    codename: "Архитектор",
    role: "Главный проектировщик системы",
    short: "Создатель ZHIDAO Protocol. Проектирует систему, события и скрытые уровни поездки. Отвечает за интерфейс между реальностью и протоколом.",
    status: "HOST",
    statusText: "ONLINE // РУТ-ДОСТУП",
    color: "#00ff66",
    avatar: "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo.png",
    tgLink: "https://t.me/ТВОЙ_ЮЗЕРНЕЙМ"   // ← замени на свой
  },
  {
    id: "mju",
    name: "Михаил Юрьевич",
    codename: "МЮ",
    role: "Главный куратор порядка",
    short: "Главный куратор порядка. Отвечает за дисциплину, сборы, правила и стабильность группы. Его задача — не дать поездке уйти в хаос.",
    status: "ACTIVE_NODE",
    statusText: "FIELD CONTROL // ОПЕРАТИВНИК",
    color: "#ff003c",
    avatar: "👑"
    // tgLink намеренно не указан
  },
  {
    id: "liza",
    name: "Елизавета Сергеевна",
    codename: "Лиза",
    role: "Коммуникационный узел",
    short: "Коммуникационный узел ZHIDAO Protocol. Помогает детям понимать правила, ориентироваться в поездке и чувствовать, что система создана для них.",
    status: "ACTIVE_NODE",
    statusText: "METERED PROXY // СВЯЗЬ",
    color: "#00f0ff",
    avatar: "💬",
    tgLink: "https://t.me/ЮЗЕРНЕЙМ_ЛИЗЫ"   // ← замени
  },
  {
    id: "yulia",
    name: "Юлия Витальевна",
    codename: "Юля",
    role: "Стабилизатор системы",
    short: "Стабилизатор системы. Помогает удерживать баланс между правилами и реальностью. Удалённый надзор за стабильностью структуры из глубокой сети.",
    status: "DEEP_WEB",
    statusText: "REMOTE ORBIT // НЕВИДИМЫЙ ОПЕРАТОР",
    color: "#fa00ff",
    avatar: "🛡️",
    tgLink: "https://t.me/ЮЗЕРНЕЙМ_ЮЛИ"    // ← замени
  },
  {
    id: "tianhao",
    name: "Сунь Тяньхао",
    codename: "Тяньхао",
    role: "Проводник внешнего контура",
    short: "Локальный проводник внешнего контура. Связывает группу с реальным Китаем: языком, городом, маршрутами и местной китайской логикой.",
    status: "FIELD_PROXY",
    statusText: "PEK-NODE DISPATCH // ЛОКАЛ",
    color: "#ffaa00",
    avatar: "🏮",
    tgLink: "https://t.me/ЮЗЕРНЕЙМ_ТЯНЬХАО" // ← замени
  }
];

function _buildTeamCard(member) {
  const avatarHtml = member.avatar.startsWith('http')
    ? `<img src="${member.avatar}" style="width:100%;height:100%;object-fit:cover;" onerror="this.parentElement.textContent='⬡'">`
    : member.avatar;

  return `
    <div class="card" style="border-left:4px solid ${member.color};margin-bottom:10px;background:rgba(10,10,18,0.7);">
      <div class="card-inner" style="padding:12px 14px;">
        <div style="display:flex;gap:12px;align-items:flex-start;">
          <div style="
            width:46px;height:46px;border-radius:8px;
            background:rgba(255,255,255,0.03);
            border:1px solid ${member.color}44;
            display:flex;align-items:center;justify-content:center;
            font-size:20px;overflow:hidden;flex-shrink:0;">
            ${avatarHtml}
          </div>
          <div style="flex:1;min-width:0;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:4px;flex-wrap:wrap;">
              <div style="font-size:11px;font-family:monospace;color:${member.color};letter-spacing:1px;font-weight:700;">
                ${member.codename.toUpperCase()} // ${member.status}
              </div>
              <span style="font-size:8px;font-family:monospace;color:var(--text3);background:rgba(255,255,255,0.05);padding:1px 5px;border-radius:4px;white-space:nowrap;">
                ${member.statusText}
              </span>
            </div>
            <div style="font-size:15px;font-weight:800;color:#fff;margin-top:2px;">${member.name}</div>
            <div style="font-size:10px;color:var(--text2);font-style:italic;margin-top:1px;">${member.role}</div>
          </div>
        </div>
        <div style="margin-top:8px;font-size:11px;color:#bbb;line-height:1.5;">${member.short}</div>
        ${member.tgLink ? `
        <button onclick="try{tg.openLink('${member.tgLink}')}catch(e){window.open('${member.tgLink}')}"
          style="margin-top:10px;width:100%;padding:7px;background:rgba(255,255,255,0.04);border:1px solid ${member.color}44;border-radius:8px;color:${member.color};font-size:10px;font-family:monospace;letter-spacing:1px;cursor:pointer;">
          联系 // НАПИСАТЬ
        </button>` : ''}
      </div>
    </div>`;
}

function renderTeamCards() {
  const html = TEAM_DATA.map(_buildTeamCard).join('');
  const el = document.getElementById('teamCardsContainerFull');
  if (el) el.innerHTML = html;
}

window.addEventListener('DOMContentLoaded', () => setTimeout(renderTeamCards, 300));
