const { Window, Note, Button, StatusBar, LcdPanel, Tabs } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Захват кампуса 校园争夺 (capture.css), Шифровальщики 密码员 и Сбой
   системы 系统故障 (cipher-* / outage-* из games.css). Имён и чисел
   экономики нет: сезон не начался, всё числовое подписано как пример. */

const Body = ({ children }) => <div className="spy-body" style={{ padding: 0, gap: 10 }}>{children}</div>;

/* ---------- Захват кампуса ---------- */
const FACTIONS = [
  ["Море", "#0a86f0"],
  ["Джунгли", "#2f9c3f"],
  ["Песок", "#d9822b"]
];

function CaptureLobby() {
  return (
    <Window title="Захват кампуса" titleCn="校园争夺" meta="лобби"
      status={<StatusBar items={["Точки не открыты", "Пример в макете"]} />}>
      <Body>
        <p className="sabotage-safety">Точки по кампусу: ходить шагом, к воде и дороге не подходить.</p>
        <p className="spy-lead">Фракции забирают точки, спор за точку решает дуэль на словах.</p>
        <div className="capture-hud" style={{ "--faction": "#0a86f0" }}>
          <div className="capture-hud-head">
            <span className="capture-label">ТВОЯ ФРАКЦИЯ</span>
            <span className="capture-you">Море 海</span>
          </div>
          <p className="capture-meta">Фракцию назначит вожатый при старте.</p>
        </div>
        <span className="spy-label">ТОЧКИ</span>
        <div className="capture-board">
          {FACTIONS.map(([name, color]) => (
            <div className="capture-score" key={name} style={{ "--faction": color }}>
              <b>{name}</b>
              <span className="capture-track"><span className="capture-bar" style={{ width: "0%" }} /></span>
              <span className="capture-score-value">—</span>
            </div>
          ))}
        </div>
        <div className="spy-actions"><Button variant="primary" disabled>Ждём старт</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function CaptureRound() {
  return (
    <Window title="Захват кампуса" titleCn="校园争夺" meta="точки открыты"
      status={<StatusBar items={["Пример в макете", "Ты во фракции Море"]} />}>
      <Body>
        <LcdPanel value="12:30" ghost="88:88" caption="ДО КОНЦА КРУГА" />
        <div className="capture-board">
          {[["Море","#0a86f0","58%","7"],["Джунгли","#2f9c3f","33%","4"],["Песок","#d9822b","25%","3"]].map(([n,c,w,v],i) => (
            <div className={i === 0 ? "capture-score is-mine" : "capture-score"} key={n} style={{ "--faction": c }}>
              <b>{n}</b>
              <span className="capture-track"><span className="capture-bar" style={{ width: w }} /></span>
              <span className="capture-score-value">{v} точек</span>
            </div>
          ))}
        </div>
        <div className="capture-card" style={{ "--faction": "#2f9c3f" }}>
          <span className="capture-label">ТОЧКА</span>
          <span className="capture-title">Библиотека</span>
          <span className="capture-zh">图书馆</span>
          <span className="capture-owner">сейчас за Джунглями</span>
          <div className="capture-question">
            <span className="capture-hanzi">书</span>
            <span className="capture-pinyin">shū</span>
          </div>
          {/* Своей карты в окне игры нет (решение от 2026-09-16): режим
              фракций накладывается на настоящий экран «Карта кампуса»,
              чтобы не дублировать географию и не выдумывать схему. */}
          <div className="capture-actions">
            <Button variant="action">Забрать точку</Button>
            <Button variant="secondary">Открыть карту кампуса</Button>
            <Button variant="secondary">Как играть?</Button>
          </div>
        </div>
        <p className="zd-sub">Кнопка активна, когда ты у точки. Автоматически захват не срабатывает.</p>
      </Body>
    </Window>
  );
}

function CaptureResult() {
  return (
    <Window title="Захват кампуса" titleCn="校园争夺" meta="дуэль за точку"
      status={<StatusBar items={["Пример в макете", "Итог круга"]} />}>
      <Body>
        <div className="capture-duel">
          <span className="capture-label">ДУЭЛЬ</span>
          <span className="capture-duel-code">4 7 2 1</span>
          <p className="capture-meta">Код называют друг другу вслух у точки.</p>
          <div className="capture-duel-moves">
            <span className="capture-duel-move cipher-card"><b>山</b><small>shān</small></span>
            <span className="capture-duel-move cipher-card"><b>水</b><small>shuǐ</small></span>
            <span className="capture-duel-move cipher-card"><b>天</b><small>tiān</small></span>
          </div>
          <span className="capture-duel-result is-win">ТОЧКА ЗА ТОБОЙ</span>
        </div>
        <span className="spy-label">ИТОГ КРУГА</span>
        <div className="capture-board">
          {[["Море","#0a86f0","58%","8"],["Джунгли","#2f9c3f","25%","3"],["Песок","#d9822b","25%","3"]].map(([n,c,w,v],i) => (
            <div className={i === 0 ? "capture-score is-mine" : "capture-score"} key={n} style={{ "--faction": c }}>
              <b>{n}</b>
              <span className="capture-track"><span className="capture-bar" style={{ width: w }} /></span>
              <span className="capture-score-value">{v} точек</span>
            </div>
          ))}
        </div>
        <Note title="Кто с кем дуэлился — не показываем" meta="приватность">В итоге только точки и фракции.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Шифровальщики ---------- */
function CipherLobby() {
  return (
    <Window title="Шифровальщики" titleCn="密码员" meta="лобби"
      status={<StatusBar items={["Команды не собраны", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Две команды, поле слов на пять на пять. Капитан даёт одну подсказку.</p>
        <div className="spy-code-plate">
          <span className="spy-label">КОД КОМНАТЫ</span>
          <span className="spy-code">C4QE</span>
          <span className="spy-hint">Код называет вожатый</span>
        </div>
        <div className="cipher-teams">
          {[["Синие", "—"], ["Красные", "—"]].map(([name, score]) => (
            <div className="cipher-team" key={name}>
              <div className="cipher-team-head"><span>{name}</span><span>{score}</span></div>
              <ul className="cipher-team-list"><li className="zd-sub">состав придёт с сервера</li></ul>
            </div>
          ))}
        </div>
        <div className="spy-actions"><Button variant="primary">Начать раунд</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function CipherRound() {
  const words = [["海","hǎi"],["山","shān"],["书","shū"],["茶","chá"],["门","mén"],["水","shuǐ"],["天","tiān"],["火","huǒ"],["人","rén"],["月","yuè"]];
  return (
    <Window title="Шифровальщики" titleCn="密码员" meta="ход синих"
      status={<StatusBar items={["Пример в макете", "Подсказка дана"]} />}>
      <Body>
        <LcdPanel value="01:20" ghost="88:88" caption="НА ХОД" low />
        <div className="cipher-score">
          <span className="cipher-chip"><span>Синие</span><b>3</b></span>
          <span className="cipher-chip"><span>Красные</span><b>2</b></span>
        </div>
        {/* Подсказку капитан говорит вслух: свободный текст между детьми в
            приложении недопустим (решение от 2026-09-16). Приложение
            показывает только, что подсказка дана и на сколько слов. */}
        <p className="spy-banner">Капитан дал подсказку вслух · <b>два слова</b></p>
        <div className="cipher-board">
          {words.map(([zh, py], i) => (
            <span className={i === 3 ? "cipher-card is-armed" : "cipher-card"} key={zh}><b>{zh}</b><small>{py}</small></span>
          ))}
        </div>
        <p className="spy-progress">второе касание подтверждает выбор</p>
        <div className="spy-actions"><Button variant="secondary">Пропустить ход</Button></div>
      </Body>
    </Window>
  );
}

function CipherResult() {
  return (
    <Window title="Шифровальщики" titleCn="密码员" meta="итог раунда"
      status={<StatusBar items={["Пример в макете", "Счёт ушёл в REP"]} />}>
      <Body>
        <div className="spy-reveal">
          <span className="spy-verdict">СИНИЕ ОТКРЫЛИ ВСЁ</span>
          <h3>Последнее слово — 茶 chá, чай</h3>
          <ul className="spy-points"><li>+★ команде</li></ul>
        </div>
        <div className="cipher-score">
          <span className="cipher-chip"><span>Синие</span><b>5</b></span>
          <span className="cipher-chip"><span>Красные</span><b>3</b></span>
        </div>
        <Note title="Кто какое слово открыл — не показываем" meta="приватность">В итоге только счёт команд.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Сбой системы ---------- */
function OutageLobby() {
  return (
    <Window title="Сбой системы" titleCn="系统故障" meta="лобби"
      status={<StatusBar items={["Модули не собраны", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Один читает руководство вслух, другой жмёт. Три промаха — система падает.</p>
        <div className="outage-strikes">
          {[0, 1, 2].map((i) => <span className="outage-lamp" key={i}>{i + 1}</span>)}
        </div>
        <div className="spy-code-plate">
          <span className="spy-label">КОД КОМНАТЫ</span>
          <span className="spy-code">S9LT</span>
          <span className="spy-hint">Код называет вожатый</span>
        </div>
        <Note title="Руководство — бумажное, у вожатого" meta="правило игры">В приложении его нет: игра настольная, второй телефон эксперту не нужен.</Note>
        <div className="spy-actions"><Button variant="primary">Начать</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function OutageRound() {
  return (
    <Window title="Сбой системы" titleCn="系统故障" meta="модуль 2 из 3"
      status={<StatusBar items={["Пример в макете", "Промахов 1"]} />}>
      <Body>
        <LcdPanel value="02:05" ghost="88:88" caption="ДО ОТКЛЮЧЕНИЯ" />
        <div className="outage-strikes">
          <span className="outage-lamp is-on">1</span>
          <span className="outage-lamp">2</span>
          <span className="outage-lamp">3</span>
        </div>
        <div className="outage-modules">
          <div className="outage-module">
            <div className="outage-module-head"><span>Провода</span><span className="outage-wire-no">3 из 5</span></div>
            <div className="outage-wires">
              {[1, 2, 3].map((n) => (
                <div className={n === 2 ? "outage-wire is-cut" : "outage-wire"} key={n}>
                  <span className="outage-wire-no">{n}</span>
                  <span className="outage-wire-line" />
                  <Button variant="secondary">Резать</Button>
                </div>
              ))}
            </div>
          </div>
          <div className="outage-module">
            <div className="outage-module-head"><span>Клавиши</span><span className="outage-wire-no">порядок</span></div>
            <div className="outage-keypad">
              {["门","水","火","月"].map((k) => <button className="outage-key" type="button" key={k}>{k}</button>)}
            </div>
          </div>
        </div>
      </Body>
    </Window>
  );
}

function OutageResult() {
  return (
    <Window title="Сбой системы" titleCn="系统故障" meta="итог"
      status={<StatusBar items={["Пример в макете", "Система устояла"]} />}>
      <Body>
        <div className="royale-win"><b>СИСТЕМА УСТОЯЛА</b><p>Три модуля закрыты, один промах.</p></div>
        <span className="spy-label">ЧТО БЫЛО В МОДУЛЯХ</span>
        <div className="outage-summary">
          <span className="outage-chip">провода · 5</span>
          <span className="outage-chip">клавиши · 4</span>
          <span className="outage-chip">число · 门</span>
        </div>
        <span className="outage-number">门</span>
        <ul className="spy-points"><li>+★ паре</li></ul>
        <Note title="Кто ошибся — не показываем" meta="приватность">В итоге только модули и число промахов.</Note>
      </Body>
    </Window>
  );
}

Object.assign(window, {
  CaptureLobby, CaptureRound, CaptureResult,
  CipherLobby, CipherRound, CipherResult,
  OutageLobby, OutageRound, OutageResult
});
