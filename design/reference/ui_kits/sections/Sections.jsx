const { Window, Card, Note, Button, StatusBar, Tabs, Chip, Gauge, EmptyState } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Разделы «Ещё»: Обмен, Мастерская, Антивирус. Разметка из trade.css,
   workshop.css, virus.css. Данные сервера нет — пустые состояния; всё
   числовое подписано как пример. */

const Body = ({ children }) => <div className="spy-body" style={{ padding: 0, gap: 10 }}>{children}</div>;

/* ---------- Обмен 交换 ---------- */
function TradeScreen() {
  const [mine, setMine] = React.useState("qilin");
  return (
    <Window title="Обмен" titleCn="交换" meta="по коду"
      status={<StatusBar items={["Сервер: обменов не было", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Обмен только дублями и только по коду: код называет тот, с кем меняешься.</p>
        <span className="zd-label">ТВОИ ДУБЛИ</span>
        <div className="trade-items">
          {[["qilin", "Цилинь", "gold", "麒麟"], ["panda", "Панда", "purple", "熊猫"]].map(([id, name, tier, cn]) => (
            <button className="trade-item" key={id} type="button" aria-pressed={mine === id} onClick={() => setMine(id)}>
              <span className={"trade-item-card is-" + tier}>
                <img src={"../../assets/implants/" + (id === "qilin" ? "qilin" : "panda") + ".webp"} alt="" />
                <b>{name}</b>
                <small className="zd-cn">{cn}</small>
                <small className="trade-tier">дубль</small>
              </span>
            </button>
          ))}
        </div>
        <div className="trade-swap">
          <div className="trade-side"><span className="zd-label">ОТДАЁШЬ</span><Chip tone="dupe">дубль · обмен</Chip></div>
          <span className="trade-arrow">⇄</span>
          <div className="trade-side"><span className="zd-label">ПОЛУЧАЕШЬ</span><span className="zd-sub">по коду напарника</span></div>
        </div>
        <input className="zd-codefield" placeholder="КОД" readOnly />
        <p className="trade-confirm">подтверждают оба · второе касание закрывает обмен</p>
        <div className="spy-actions">
          <Button variant="confirm" confirmLabel="Точно? отдать дубль">Обменять</Button>
        </div>
        <Note title="Имени напарника в ленте не будет" meta="приватность">Ни кто оценил, ни с кем был обмен, нигде не показывается.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Мастерская 工坊 ---------- */
function WorkshopScreen() {
  return (
    <Window title="Мастерская" titleCn="工坊" meta="четыре дубля → улучшение"
      status={<StatusBar items={["Сервер: дублей нет", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Четыре одинаковых импланта превращаются в один следующей ступени.</p>
        <div className="workshop-recipes">
          <div className="workshop-recipe" data-tier="purple">
            <span className="workshop-art"><img src="../../assets/implants/panda.webp" alt="" /></span>
            <span className="workshop-info">
              <b>Панда 熊猫</b>
              <small>дублей: 2 из 4 · пример</small>
              <span className="workshop-route">4 × фиолетовый → золотой</span>
            </span>
            <Button variant="secondary" disabled>Нужно ещё 2</Button>
          </div>
          <div className="workshop-recipe" data-tier="gold">
            <span className="workshop-art"><img src="../../assets/implants/qilin.webp" alt="" /></span>
            <span className="workshop-info">
              <b>Цилинь 麒麟</b>
              <small>дублей: 4 из 4 · пример</small>
              <span className="workshop-route">4 × золотой → улучшенный</span>
            </span>
            <Button variant="confirm" confirmLabel="Точно? сплавить 4 дубля">Переплавить</Button>
          </div>
        </div>
        <div className="workshop-forge">
          <div className="workshop-forge-items"><i /><i /><i /></div>
          <span className="workshop-forge-bar"><i style={{ width: "62%" }} /></span>
          <span>ПЕРЕПЛАВКА · пример состояния</span>
        </div>
        <div className="workshop-result" data-tier="upgraded">
          <span className="workshop-result-art"><img src="../../assets/implants/golden_nexus.webp" alt="" /></span>
          <h3>Золотой узел 金结</h3>
          <p className="zd-sub">Улучшенная ступень. Обратно не разбирается.</p>
        </div>
        <Note title="Цены и шансы не меняются" meta="правило экономики">Рецепт берётся как есть: четыре дубля одной ступени.</Note>
      </Body>
    </Window>
  );
}

/* ---------- Антивирус 杀毒 ---------- */
function VirusScreen() {
  const [tab, setTab] = React.useState("state");
  const state = (
    <React.Fragment>
      <div className="virus-status">
        <span className="virus-state is-infected">Заражение: шуточное</span>
        <span className="zd-sub">Значки дрожат, фон съезжает. Ничего не ломается и не прячется.</span>
        <span className="virus-firewall">firewall: on · протокол 60 не затронут</span>
      </div>
      <div className="virus-popup">
        <div className="virus-popup-bar"><span>Протокол: предупреждение</span><button type="button" aria-label="Закрыть">×</button></div>
        <div className="virus-popup-body">
          <span className="virus-popup-icon">!</span>
          <p>Обнаружен весёлый вирус. Пройди тест, чтобы вылечиться.</p>
        </div>
        <div className="virus-popup-actions"><Button variant="secondary">Позже</Button><Button variant="primary">Лечить</Button></div>
      </div>
      <Note title="Дрожание выключается вместе с анимациями" meta="правило движения">Системное «уменьшить движение» и флажок «Анимации» гасят его целиком.</Note>
    </React.Fragment>
  );
  const test = (
    <React.Fragment>
      <div className="virus-question">
        <span className="virus-zh">药</span>
        <small>yào · выбери перевод</small>
      </div>
      <div className="virus-options">
        <Button variant="secondary">лекарство</Button>
        <Button variant="secondary">вода</Button>
        <Button variant="secondary">хлеб</Button>
      </div>
      <Gauge value={2} segments={5} label="Вопросы теста" />
      <p className="spy-progress">2 из 5 · пример</p>
    </React.Fragment>
  );
  return (
    <Window title="Антивирус" titleCn="杀毒" meta="шуточное заражение"
      status={<StatusBar items={["Сервер: заражений нет", "Пример в макете"]} />}>
      <Body>
        <Tabs value={tab} onChange={setTab}
          items={[{ id: "state", label: "Состояние" }, { id: "test", label: "Тест" }]}
          panel={tab === "state" ? state : test} />
      </Body>
    </Window>
  );
}

Object.assign(window, { TradeScreen, WorkshopScreen, VirusScreen });
