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
    avatar: "👑"
    // tgLink намеренно не указан
  },
  {
    id: "architect",
    name: "Марк Альбертович",
    codename: "Архитектор",
    role: "Главный проектировщик системы",
    short: "Архитектор системы, как тот чел из фильма Matrix",
    status: "HOST",
    statusText: "ERROR // ERROR",
    color: "#00ff66",
    avatar: "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/file_000000004784720a8c151f4c50a357d9.png?raw=true",
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
    avatar: "💬",
    tgLink: "https://t.me/naoayako"
  },
  {
    id: "yulia",
    name: "Юлия Витальевна",
    codename: "Юля",
    role: "АЛЬФА ВОЖАТАЯ",
    short: "В нашем сердечке. Поправляйтесь скорее!",
    status: "DEEP_WEB",
    statusText: "REMOTE ORBIT // НЕВИДИМЫЙ ОПЕРАТОР",
    color: "#fa00ff",
    avatar: "🛡️",
    tgLink: "https://t.me/Trufanova_Yulia"
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
    avatar: "🏮",
    tgLink: "https://t.me/+8617614130674"
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
