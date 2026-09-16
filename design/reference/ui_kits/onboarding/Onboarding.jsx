/* Вход и привязка MAX + пустые, ошибочные и офлайн-состояния.

   Сценарий и все тексты взяты из auth.js, index.html (блок #authGate),
   V4_AUTH.md §1b и diary.js. Ничего сверх этого: третьего отказа у сервера
   нет, команды отвязки нет, поэтому кнопки «снять привязку» нет и в макете. */

const { Window, Card, Note, Button, StatusBar, Chip, EmptyState, CodeField } = window.ZHIDAOProtocolDesignSystem_ad77c0;

const Brand = () => (
  <div className="gate-brand">
    <img src="../../assets/zhidao-dragon-logo-256.png" alt="" />
    <strong>Вход</strong>
    <small>ZHIDAO PROTOCOL · HAINAN</small>
  </div>
);

/* --- 1. Первый вход: проверка сессии, затем вход через MAX ------------- */
function GateChecking() {
  return (
    <Window title="Вход" titleCn="登录" meta="MAX"
      status={<StatusBar items={["Сервер: проверка сессии", "GET /auth/me"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <div className="gate-wait"><i /><span>Проверяем сессию…</span></div>
        </div>
        <Note title="Пароля у участника нет" meta="V4_AUTH §1b">У него есть MAX и код от вожатого. Форма логина в мини-приложении не показывается вовсе.</Note>
      </div>
    </Window>
  );
}

function GateMax() {
  return (
    <Window title="Вход" titleCn="登录" meta="MAX"
      status={<StatusBar items={["Сервер: вход через MAX", "POST /auth/max"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <div className="gate-wait"><i /><span>Входим через MAX…</span></div>
        </div>
      </div>
    </Window>
  );
}

/* --- 2. Ввод кода привязки (409 · link_required) ----------------------- */
function GatePair({ error }) {
  const [code, setCode] = React.useState("");
  return (
    <Window title="Вход" titleCn="登录" meta="код привязки"
      status={<StatusBar items={["Сервер: 409 · link_required", "Код — сервер"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <p className="zd-sub">MAX вас узнал, но пока не знает, чей это аккаунт в поездке. Введите код, который выдал вожатый.</p>
          <CodeField label="Код сопряжения" labelCn="配对码 pèi duì mǎ" length={12} value={code} onChange={setCode}
            inputMode="numeric" placeholder="1543 6364"
            hint="Восемь цифр, двумя группами по четыре. Пробел не мешает: лишние символы отбрасывает и приложение, и сервер." />
          {error && <p className="gate-error">{error}</p>}
          <Button variant="primary">Связать аккаунт</Button>
        </div>
        <Note title="Код диктуют вслух" meta="правило выдачи">Поэтому он показан группами по четыре и там, и здесь. Новая выдача у вожатого отменяет прежний код.</Note>
      </div>
    </Window>
  );
}

/* --- 3. Аккаунт уже привязан к другому MAX (409 · account_already_linked) */
function GateLinked() {
  return (
    <Window title="Вход" titleCn="登录" meta="привязка занята"
      status={<StatusBar items={["Сервер: 409 · account_already_linked", "Действий нет"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <p className="gate-error">Этот аккаунт уже привязан к другому MAX. Новый код не поможет — нужно снять прежнюю привязку.</p>
          <div className="stf-standby">
            <b>Обратитесь к вожатому</b>
            <span>Команды отвязки сейчас нет, поэтому кнопки здесь тоже нет: снять привязку может только тот, у кого есть доступ к серверу.</span>
          </div>
        </div>
        <Note title="Это конечное состояние, а не сбой" meta="схема данных">Аккаунту разрешена ровно одна привязка на провайдера — UNIQUE(account_id, provider_code).</Note>
      </div>
    </Window>
  );
}

/* --- 4. Обычный браузер: логин и пароль ------------------------------- */
function GateLocal({ error }) {
  return (
    <Window title="Вход" titleCn="登录" meta="браузер"
      status={<StatusBar items={["Сервер: провайдер local", "POST /auth/login"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <p className="zd-sub">Вне MAX вход по логину и паролю. У участников таких пар нет — это путь служебных учётных записей.</p>
          <div className="gate-fields">
            <label className="zd-label is-plain" htmlFor="gateLogin">Логин</label>
            <input id="gateLogin" type="text" autoComplete="username" />
            <label className="zd-label is-plain" htmlFor="gatePass">Пароль</label>
            <input id="gatePass" type="password" autoComplete="current-password" />
          </div>
          {error && <p className="gate-error">{error}</p>}
          <Button variant="primary">Войти</Button>
          <button type="button" className="gate-link">Посмотреть оформление без входа</button>
        </div>
        <Note title="Просмотр оформления не показывает личных данных" meta="режим preview">Личные API в нём не вызываются, играть и покупать нельзя.</Note>
      </div>
    </Window>
  );
}

/* --- 5. Пустые, ошибочные и офлайн-состояния -------------------------- */
function StateToday() {
  return (
    <Window title="Сегодня" titleCn="今天" meta="нет связи"
      status={<StatusBar items={["Сервер не ответил", "Данных на экране нет"]} />}>
      <div className="stf-body" style={{ padding: 12 }}>
        <EmptyState title="Сервер не отвечает">Проверьте связь и обновите страницу. Прошлые данные не показываем: устаревшее число хуже пустого места.</EmptyState>
        <Note title="Офлайн — это не отмена" meta="правило честных данных">Пустой экран не значит, что мероприятия отменили.</Note>
      </div>
    </Window>
  );
}

function StateSeason() {
  return (
    <Window title="Сегодня" titleCn="今天" meta="сезон не начался"
      status={<StatusBar items={["Сервер: сезон в черновике", "Маршрут не активирован"]} />}>
      <div className="stf-body" style={{ padding: 12 }}>
        <EmptyState title="Маршрут ещё не активирован">Расписание ещё не подключено. Уточните у вожатого: это не отмена мероприятий.</EmptyState>
        <div className="stf-standby">
          <b>Мой день 我的一天</b>
          <span>Планы появятся после активации сезона. Кнопка «Все планы» до этого момента ничего не открывает и так и подписана.</span>
        </div>
        <EmptyState title="Вас ещё не включили в сезон">Оценки и рейтинг появятся после старта поездки.</EmptyState>
      </div>
    </Window>
  );
}

function StateCollection() {
  return (
    <Window title="Коллекция" titleCn="收藏" meta="пусто"
      status={<StatusBar items={["Сервер: имплантов нет", "Попыток: 0"]} />}>
      <div className="stf-body" style={{ padding: 12 }}>
        <EmptyState title="Коллекция пуста">Импланты приходят из кейсов. Попытку даёт третья звезда за дневник и игры.</EmptyState>
        <div className="stf-rows">
          <div className="stf-row"><span className="stf-row-copy"><b>Магазин · Моё 我的</b><small>ничего не куплено</small></span></div>
        </div>
        <EmptyState title="Покупок нет">Купленное появится здесь. Витрина обновляется в 07:00 по времени сезона.</EmptyState>
        <EmptyState title="Оценок пока нет">Их ставит вожатый по бумажному дневнику.</EmptyState>
      </div>
    </Window>
  );
}

function StateExpired() {
  return (
    <Window title="Вход" titleCn="登录" meta="сессия"
      status={<StatusBar items={["Сервер: 401", "Результат сохранён"]} />}>
      <div className="gate">
        <Brand />
        <div className="gate-step">
          <p className="gate-error">Сессия завершилась. Войдите снова; результат сохранён на сервере.</p>
          <Button variant="primary">Войти через MAX</Button>
        </div>
        <Note title="Пока вход не пройден, приложение выключено целиком" meta="доступность">Экран входа лежит поверх, но нижняя панель и кнопки под ним выключены по-настоящему, а не только визуально.</Note>
        <div className="stf-body"><Chip tone="example">пример состояния</Chip></div>
      </div>
    </Window>
  );
}

Object.assign(window, { GateChecking, GateMax, GatePair, GateLinked, GateLocal, StateToday, StateSeason, StateCollection, StateExpired });
