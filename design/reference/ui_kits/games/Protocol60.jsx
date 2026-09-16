const { Window, Card, Note, Chip, Button, StatusBar, LcdPanel, Tabs, EmptyState } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* «Протокол 60» — игра-шоу на вопросах, идёт всю смену. Сцена
   фиолетово-золотая (royale.css), окно участника — обычное окно игры.
   Все числа ниже помечены как пример: сезон не начался. */

const Logo = () => (
  <span className="royale-logo"><b>ПРОТОКОЛ</b><span>60</span><i>协议</i></span>
);

const Marquee = ({ text }) => (
  <div className="royale-marquee"><span>{text}</span></div>
);

function P60Lobby() {
  return (
    <Window title="Протокол 60" titleCn="协议" meta="лобби"
      status={<StatusBar items={["Сервер: ждём старта", "Пример в макете"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <Logo />
        <Marquee text="ИГРА ИДЁТ ВСЮ СМЕНУ · ВЫБЫЛ — СМОТРИШЬ · ВОЗВРАТ ПО ОЖИВЛЕНИЮ" />
        <p className="spy-lead">Один вопрос в день. Ответил верно — остаёшься, ошибся — выбываешь до оживления.</p>
        <ul className="spy-facts">
          <li>вопрос раз в день</li>
          <li>ответ 20 секунд</li>
          <li>оживление один раз</li>
        </ul>
        <P60Progress alive={null} />
        <div className="spy-actions">
          <Button variant="primary" disabled>Ждём первый вопрос</Button>
          <Button variant="secondary">Как играть?</Button>
        </div>
      </div>
    </Window>
  );
}

function P60Round() {
  return (
    <Window title="Протокол 60" titleCn="协议" meta="вопрос 7"
      status={<StatusBar items={["Пример в макете", "Осталось 12 из 60"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <Logo />
        <LcdPanel value="00:14" ghost="88:88" caption="НА ОТВЕТ" low />
        <P60Progress alive={12} feed={P60_FEED} />
        <div className="royale-question">
          <span className="royale-hanzi">海</span>
          <p className="royale-pinyin">hǎi</p>
          <span className="royale-surprise">сюрприз: ответ иероглифом</span>
        </div>
        <div className="royale-options is-hanzi">
          <button className="royale-option" type="button">море</button>
          <button className="royale-option" type="button">гора</button>
          <button className="royale-option" type="button">небо</button>
          <button className="royale-option" type="button">город</button>
        </div>
        {/* Ход ответов — полоса без цифр (решение от 2026-09-16): видно, что
            отвечают не только ты, и нет давления «большинство уже решило».
            Точное число у вожатого в консоли, вместе с попытками и ★. */}
        <div className="gauge" aria-label="Ход ответов"><div className="gauge-fill" style={{ width: "68%" }} /></div>
        <p className="spy-progress">идёт приём ответов</p>
      </div>
    </Window>
  );
}

function P60Result() {
  return (
    <Window title="Протокол 60" titleCn="协议" meta="итог вопроса"
      status={<StatusBar items={["Пример в макете", "Следующий вопрос завтра"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <div className="royale-options">
          <span className="royale-option is-right">море</span>
          <span className="royale-option is-wrong">гора</span>
        </div>
        <p className="royale-explain">海 hǎi — море. Запомни по «Хайнань» 海南: «к югу от моря».</p>
        <div className="royale-out">
          <b>ТЫ ВЫБЫЛ</b>
          <p>Смотришь до оживления. Оживить может только вожатый из консоли.</p>
        </div>
        <P60Progress alive={12} feed={P60_FEED} />
        <div className="royale-grid">
          {Array.from({ length: 18 }, (_, i) => (
            <span key={i} className={"royale-avatar" + (i > 11 ? " is-out" : i < 4 ? " is-answered" : "")} />
          ))}
        </div>
        <Note title="Имён в сетке нет" meta="приватность">В сетке видно только, сколько живо и сколько ответило.</Note>
      </div>
    </Window>
  );
}

/* Индикатор хода игры (решение от 2026-09-16): одно честное число с
   сервера плюс лента последних трёх выбываний — тот же приём, что у
   «последних трёх сигналов» в Кейсах, без нового компонента. Имён в
   ленте нет: только вопрос, слово и сколько выбыло. */
function P60Progress({ alive, feed }) {
  return (
    <Card label="ХОД ИГРЫ" title="Живых" titleCn="在场">
      <span className="royale-count">{alive === null ? "—" : alive + " из 60"}</span>
      {feed ? (
        <React.Fragment>
          <span className="spy-label" style={{ marginTop: 8 }}>ПОСЛЕДНИЕ ВЫБЫВАНИЯ</span>
          <ol className="royale-results">
            {feed.map((row) => (
              <li key={row.q}><b>вопрос {row.q}</b> · {row.word} <span>выбыло {row.out}</span></li>
            ))}
          </ol>
        </React.Fragment>
      ) : (
        <p className="royale-meta">Выбывания появятся после первого вопроса.</p>
      )}
    </Card>
  );
}

const P60_FEED = [
  { q: 7, word: "海 hǎi", out: 3 },
  { q: 6, word: "山 shān", out: 5 },
  { q: 5, word: "天 tiān", out: 2 }
];

Object.assign(window, { P60Lobby, P60Round, P60Result, P60Progress });
