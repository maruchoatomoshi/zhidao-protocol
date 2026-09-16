const { Window, Card, Note, Button, StatusBar, LcdPanel, Chip, Tabs } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Контрабанда, Тайный агент, Зомби-протокол, Саботаж — по три состояния.
   Разметка из smuggle.css, agent.css, zombie.css, sabotage.css. Имён нет
   нигде, чисел экономики нет: сезон не начался. */

const Body = ({ children }) => <div className="spy-body" style={{ padding: 0, gap: 10 }}>{children}</div>;

/* ---------- Контрабанда 走私 ---------- */
function SmuggleLobby() {
  return (
    <Window title="Контрабанда" titleCn="走私" meta="лобби"
      status={<StatusBar items={["Комната открыта", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Провези товар через прилавок. Досмотрщик читает по лицу, а не по сумке.</p>
        <div className="spy-code-plate">
          <span className="spy-label">КОД КОМНАТЫ</span>
          <span className="spy-code">M3TP</span>
          <span className="spy-hint">Код называет вожатый</span>
        </div>
        <ul className="spy-facts"><li>раунд 8 минут</li><li>сумка на 3 карты</li><li>досмотрщик меняется</li></ul>
        <div className="smuggle-seat is-officer">
          <div className="smuggle-seat-head"><span className="sabotage-role">Досмотрщик</span><span className="smuggle-badge">по жребию</span></div>
          <p className="zd-sub">Роль назначит сервер после старта.</p>
        </div>
        <Note title="Состав покажет сервер" meta="приватность">В списке комнаты имён не будет.</Note>
        <div className="spy-actions"><Button variant="primary">Начать раунд</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

/* «Рынок контрабанды» — вкладка внутри «Контрабанды» (решение от
   2026-09-16), как «Витрина / Моё» в Магазине: один экран, не два окна.
   Разметка рынка из market.css. */
function MarketPanel() {
  return (
    <React.Fragment>
      <p className="market-news">Новость рынка: патруль у столовой до конца раунда.</p>
      <div className="market-card is-offer">
        <span className="spy-label">ОБМЕН ПО КОДУ</span>
        <div className="market-builder">
          <span className="market-head">отдаёшь</span><span className="market-head">товар</span><span className="market-head">берёшь</span>
          <span className="market-stepper"><button className="btn btn-secondary" type="button"><span>−</span></button><b>1</b><button className="btn btn-secondary" type="button"><span>+</span></button></span>
          <span className="market-name">茶 chá</span>
          <span className="market-stepper"><button className="btn btn-secondary" type="button"><span>−</span></button><b>2</b><button className="btn btn-secondary" type="button"><span>+</span></button></span>
          <span className="market-stepper"><button className="btn btn-secondary" type="button"><span>−</span></button><b>0</b><button className="btn btn-secondary" type="button"><span>+</span></button></span>
          <span className="market-name is-contraband">玉 yù</span>
          <span className="market-stepper"><button className="btn btn-secondary" type="button"><span>−</span></button><b>1</b><button className="btn btn-secondary" type="button"><span>+</span></button></span>
        </div>
      </div>
      <div className="market-form">
        <input className="market-input" placeholder="КОД" readOnly />
        <Button variant="primary">Принять</Button>
      </div>
      <div className="market-card is-patrol">
        <span className="spy-label">ПАТРУЛЬ</span>
        <p className="market-role">Досмотр у прилавка</p>
        <p className="market-meta">Кто в патруле — знает только сервер.</p>
      </div>
      <span className="spy-label">ЛАВКА</span>
      <div className="market-goods">
        <span className="market-chip">茶</span><span className="market-chip">米</span>
        <span className="market-chip is-contraband">玉</span><span className="market-chip is-empty">пусто</span>
      </div>
    </React.Fragment>
  );
}

function SmuggleRound() {
  const [tab, setTab] = React.useState("bag");
  const bag = (
    <React.Fragment>
      <div className="smuggle-event is-typhoon"><b>Тайфун 台风</b><span>Прилавки закрыты, цены на фрукты выросли.</span></div>
      <span className="spy-label">ТВОЯ СУМКА</span>
      <div className="smuggle-hand">
        <div className="smuggle-card is-legal"><b>茶</b><small>chá</small><span className="smuggle-ru">чай</span><span className="smuggle-price">законно</span></div>
        <div className="smuggle-card is-contraband is-picked"><b>玉</b><small>yù</small><span className="smuggle-ru">нефрит</span><span className="smuggle-price">контрабанда</span></div>
        <div className="smuggle-card is-legal"><b>米</b><small>mǐ</small><span className="smuggle-ru">рис</span><span className="smuggle-price">законно</span></div>
      </div>
      <p className="spy-banner">Карты видишь только ты. Экран не показывают соседу.</p>
      <div className="spy-actions"><Button variant="action">Пройти досмотр</Button><Button variant="secondary">Как играть?</Button></div>
    </React.Fragment>
  );
  return (
    <Window title="Контрабанда" titleCn="走私" meta="раунд 2"
      status={<StatusBar items={["Пример в макете", "Твоя сумка видна только тебе"]} />}>
      <Body>
        <LcdPanel value="03:40" ghost="88:88" caption="ДО ДОСМОТРА" />
        <Tabs value={tab} onChange={setTab}
          items={[{ id: "bag", label: "Прилавок" }, { id: "market", label: "Рынок" }]}
          panel={tab === "bag" ? bag : <MarketPanel />} />
      </Body>
    </Window>
  );
}

function SmuggleResult() {
  return (
    <Window title="Контрабанда" titleCn="走私" meta="итог раунда"
      status={<StatusBar items={["Пример в макете", "Счёт ушёл в REP"]} />}>
      <Body>
        <div className="spy-reveal">
          <span className="spy-verdict">ДОСМОТР ПРОЙДЕН</span>
          <h3>Нефрит 玉 yù прошёл</h3>
          <span className="spy-hint">Досмотрщик проверил чай</span>
          <ul className="spy-points"><li>+★ провёзшим</li></ul>
        </div>
        <span className="spy-label">ПРИЛАВОК</span>
        <div className="smuggle-stall">
          <span className="smuggle-chip">茶</span><span className="smuggle-chip">米</span>
          <span className="smuggle-chip is-hidden">скрыто</span><span className="smuggle-chip is-empty">пусто</span>
        </div>
        <Note title="Кто что вёз — не показываем" meta="приватность">В итоге только товар и результат досмотра.</Note>
        <div className="spy-actions"><Button variant="primary">Ещё раунд</Button><Button variant="secondary">Выйти из комнаты</Button></div>
      </Body>
    </Window>
  );
}

/* ---------- Тайный агент 特工 ---------- */
function AgentLobby() {
  return (
    <Window title="Тайный агент" titleCn="特工" meta="лобби"
      status={<StatusBar items={["Задания не разосланы", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Ты получаешь цель и задание. Выполни незаметно — и не дай выполнить своё другому.</p>
        <p className="agent-stats">заданий выполнено: —</p>
        <p className="agent-meta">Задание приходит от сервера один раз в день.</p>
        <div className="agent-card is-guess">
          <p className="agent-target">Цель ещё не назначена</p>
          <p className="agent-mission">Появится, когда вожатый откроет игру.</p>
        </div>
        <Note title="Кто чья цель — знает только сервер" meta="приватность" />
        <div className="spy-actions"><Button variant="primary" disabled>Ждём задание</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function AgentRound() {
  return (
    <Window title="Тайный агент" titleCn="特工" meta="задание дня"
      status={<StatusBar items={["Пример в макете", "Задание активно"]} />}>
      <Body>
        <p className="agent-news">Новость смены: у моря нашли ракушку с кодом.</p>
        <div className="agent-card is-incoming">
          <span className="spy-label">ТВОЁ ЗАДАНИЕ</span>
          <p className="agent-target">Спросить у цели про погоду 天气</p>
          <p className="agent-mission">Цель не должна понять, что это задание.</p>
        </div>
        <LcdPanel value="06:00" ghost="88:88" caption="ДО КОНЦА ДНЯ" />
        <div className="spy-actions"><Button variant="action">Задание выполнено</Button><Button variant="secondary">Как играть?</Button></div>
        <Note title="Имени цели в макете нет" meta="приватность">Сервер показывает имя только тебе и только на этом экране.</Note>
      </Body>
    </Window>
  );
}

function AgentResult() {
  return (
    <Window title="Тайный агент" titleCn="特工" meta="итог дня"
      status={<StatusBar items={["Пример в макете", "Счёт ушёл в REP"]} />}>
      <Body>
        <div className="spy-reveal">
          <span className="spy-verdict">ЗАДАНИЕ ЗАЧТЕНО</span>
          <h3>Погода 天气 tiānqì</h3>
          <ul className="spy-points"><li>+★ за выполнение</li></ul>
        </div>
        {/* Счёт «раскрыто» участнику не показываем (решение от 2026-09-16):
            живой счётчик подсказывал бы, на кого сейчас смотрят другие. Он
            живёт в консоли вожатого. */}
        <span className="spy-label">ЗАЧТЕНО ЗА ДЕНЬ</span>
        <ol className="agent-rating"><li><span>твоих заданий</span><b>—</b></li></ol>
        <p className="agent-meta is-ok">Число придёт с сервера: сезон не начался.</p>
        <Note title="Счёт раскрытий — только у вожатого" meta="приватность">Кто кого раскрыл, не показывается никому из участников.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Зомби-протокол 僵尸 ---------- */
function ZombieLobby() {
  return (
    <Window title="Зомби-протокол" titleCn="僵尸" meta="лобби"
      status={<StatusBar items={["Заражение не начато", "Пример в макете"]} />}>
      <Body>
        <p className="zombie-safety">Игра без бега и касаний: заражение — это ввод кода, а не погоня.</p>
        <p className="spy-lead">У человека есть личный код. Зомби получает его только добровольно.</p>
        <div className="zombie-card">
          <span className="spy-label">ТВОЙ КОД</span>
          <span className="zombie-code">— — — —</span>
          <p className="zombie-meta">Код выдаст сервер при старте.</p>
        </div>
        <p className="zombie-headline">Людей: — · Зомби: —</p>
        <div className="spy-actions"><Button variant="primary" disabled>Ждём старт</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function ZombieRound() {
  return (
    <Window title="Зомби-протокол" titleCn="僵尸" meta="идёт заражение"
      status={<StatusBar items={["Пример в макете", "Ты человек"]} />}>
      <Body>
        <p className="zombie-safety">Без бега и касаний. Код называют голосом.</p>
        <div className="zombie-card">
          <span className="spy-label">ТВОЙ КОД</span>
          <span className="zombie-code">7 4 1 9</span>
        </div>
        <span className="spy-label">СТАНЦИЯ-ВАКЦИНА</span>
        <div className="zombie-question">
          <span className="zombie-hanzi">药</span>
          <div className="royale-options is-hanzi">
            <button className="royale-option" type="button">лекарство</button>
            <button className="royale-option" type="button">вода</button>
          </div>
        </div>
        <div className="zombie-tag">
          {/* Код — четыре цифры (решение от 2026-09-16): набирается быстро
              и без ошибок на улице, иероглиф в поле — лишний риск. */}
          <input className="zombie-input" placeholder="0000" inputMode="numeric" maxLength={4} readOnly />
          <Button variant="action">Заразить</Button>
        </div>
        <p className="zombie-headline">Людей: 41 · Зомби: 19 <span className="zombie-left">пример</span></p>
      </Body>
    </Window>
  );
}

function ZombieResult() {
  return (
    <Window title="Зомби-протокол" titleCn="僵尸" meta="итог"
      status={<StatusBar items={["Пример в макете", "Игра закрыта"]} />}>
      <Body>
        <div className="royale-win"><b>ЛЮДИ ВЫСТОЯЛИ</b><p>Вакцина собрана на станции у столовой.</p></div>
        <p className="zombie-headline">Осталось людей: 12 из 60</p>
        <div className="zombie-grid">
          {Array.from({ length: 14 }, (_, i) => (
            <span className={i < 5 ? "zombie-chip" : "zombie-chip is-zombie"} key={i}>{i < 5 ? "человек" : "зомби"}</span>
          ))}
        </div>
        <Note title="Кто кого заразил — не показываем" meta="приватность">В итоге только счёт сторон.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Саботаж 破坏 ---------- */
function SabotageLobby() {
  return (
    <Window title="Саботаж" titleCn="破坏" meta="лобби"
      status={<StatusBar items={["Станции не открыты", "Пример в макете"]} />}>
      <Body>
        <p className="sabotage-safety">Станции по GPS: ходить шагом, к воде и дороге не подходить.</p>
        <p className="spy-lead">Экипаж закрывает задания у станций, саботажник тихо их ломает.</p>
        <div className="sabotage-card">
          <span className="spy-label">ТВОЯ РОЛЬ</span>
          <p className="sabotage-role">Роль ещё не назначена</p>
          <p className="sabotage-meta">Сервер назначит при старте.</p>
        </div>
        <span className="spy-label">ЗАДАНИЯ ЭКИПАЖА</span>
        <div className="sabotage-bar"><span style={{ width: "0%" }} /></div>
        <div className="spy-actions"><Button variant="primary" disabled>Ждём старт</Button><Button variant="secondary">Как играть?</Button></div>
      </Body>
    </Window>
  );
}

function SabotageRound() {
  return (
    <Window title="Саботаж" titleCn="破坏" meta="станции открыты"
      status={<StatusBar items={["Пример в макете", "Ты экипаж"]} />}>
      <Body>
        <p className="sabotage-safety">Ходить шагом. Станция считается сданной по GPS.</p>
        <div className="sabotage-card is-tasks">
          <span className="spy-label">СТАНЦИЯ У БИБЛИОТЕКИ</span>
          <div className="sabotage-question">
            <span className="sabotage-hanzi">图书馆</span>
            <div className="royale-options">
              <button className="royale-option" type="button">библиотека</button>
              <button className="royale-option" type="button">столовая</button>
            </div>
          </div>
        </div>
        <span className="spy-label">ЗАДАНИЯ ЭКИПАЖА</span>
        <div className="sabotage-bar"><span style={{ width: "45%" }} /></div>
        <p className="sabotage-done">сдано 4 из 9 · пример</p>
        {/* Сдача — кнопкой участника, не автоматикой по GPS: пока карта
            прототип, точность GPS не подразумеваем (решение от 2026-09-16). */}
        <div className="spy-actions"><Button variant="action">Сдать станцию</Button><Button variant="secondary">Как играть?</Button></div>
        <p className="zd-sub">Кнопка активна, когда ты у станции. Автоматически сдача не срабатывает.</p>
      </Body>
    </Window>
  );
}

function SabotageResult() {
  return (
    <Window title="Саботаж" titleCn="破坏" meta="собрание"
      status={<StatusBar items={["Пример в макете", "Голосование закрыто"]} />}>
      <Body>
        <div className="sabotage-card is-meeting">
          <span className="spy-label">СОБРАНИЕ</span>
          <p className="sabotage-role">Саботажник найден</p>
          <p className="sabotage-meta">Экипаж закрыл 9 из 9 заданий.</p>
        </div>
        <div className="sabotage-grid">
          <span className="sabotage-chip">экипаж</span><span className="sabotage-chip">экипаж</span>
          <span className="sabotage-chip is-saboteur">саботажник</span><span className="sabotage-chip is-out">выбыл</span>
        </div>
        <ul className="spy-points"><li>+★ экипажу</li></ul>
        <Note title="Кто как голосовал — не показываем" meta="приватность">В итоге только роли и результат собрания.</Note>
      </Body>
    </Window>
  );
}

Object.assign(window, {
  MarketPanel, SmuggleLobby, SmuggleRound, SmuggleResult,
  AgentLobby, AgentRound, AgentResult,
  ZombieLobby, ZombieRound, ZombieResult,
  SabotageLobby, SabotageRound, SabotageResult
});
