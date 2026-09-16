/* Консоль вожатого на телефоне.

   Разделы и тексты — из admin.js, diary.js, cases_api.py и V4_AUTH.md §1b.
   Роли бывают глобальные и сезонные, и каждая панель отвечает за свой
   доступ отдельно: вожатому по умолчанию открываются «Участники», потому
   что «Сводка» ему всё равно ответит отказом.

   Решения от 2026-09-16:
   — Выдачи ★ отдельной командой не будет: единственный ручной плюс —
     бонус дневника, он уже существует и уже даёт ★. Серверная команда
     «выдать ★» отклонена как новая экономика и новый журнал.
   — Расписание дня вводится строками «время — что»: «Мой день» остаётся
     списком по времени. Каталог готовых блоков и один текст на день
     отклонены. Хранения на сервере ещё нет, поэтому сохранение выключено
     и подписано словами.
   — Вкладка «Сводка» видна всем с пометкой «нужна роль архитектора» до
     нажатия: состояние объясняется заранее, а не через клик-и-отказ. */

const { Window, Card, Note, Button, StatusBar, Tabs, Chip, DataTable, EmptyState, Select, Checkbox } = window.ZHIDAOProtocolDesignSystem_ad77c0;

const Body = ({ children }) => <div className="stf-body" style={{ padding: 10 }}>{children}</div>;

const Head = ({ role = "Оператор", roles = ["Оператор"], season = "сезон #1" }) => (
  <div className="stf-roles">
    <span className="stf-badge" data-role={role === "Системный администратор" ? "system_admin" : undefined}>{role}</span>
    {roles.map((r) => <span className="stf-badge" key={r}>{r}<i>{season}</i></span>)}
  </div>
);

/* --- Обзор: только архитектору и системному администратору ------------- */
function ConsoleOverview() {
  return (
    <Window title="Консоль" titleCn="值班台" meta="Сводка"
      status={<StatusBar items={["GET /admin/overview", "SCHEMA — пример"]} />}>
      <Body>
        <Head role="Архитектор" roles={[]} />
        <div className="stf-gauges">
          {[["Аккаунты", "64"], ["Сезоны", "1"], ["Черновики", "1"], ["Сессии", "7"], ["Журнал", "1 208"]].map(([k, v]) => (
            <div className="stf-gauge" key={k}><span>{k}</span><strong>{v}</strong></div>
          ))}
        </div>
        <Chip tone="example">числа на макете — пример, сервер считает сам</Chip>
        <span className="zd-label">ЖУРНАЛ · ПОСЛЕДНИЕ ЗАПИСИ</span>
        <div className="stf-log">
          {[["auth.login", "account #12 · сезон #1"], ["diary.rate", "account #31 · сезон #1"], ["case.grant", "account #08 · сезон #1"]].map(([a, e], i) => (
            <div className="stf-log-row" key={i}><b>{a}</b><span>{e}</span><small>вожатый · 2026-09-16 20:14 (пример)</small></div>
          ))}
        </div>
        <Note title="Сводка требует глобальной роли" meta="права">Вожатому она отвечает отказом, поэтому ему сразу открываются «Участники».</Note>
      </Body>
    </Window>
  );
}

function ConsoleDenied() {
  return (
    <Window title="Консоль" titleCn="值班台" meta="Сводка"
      status={<StatusBar items={["Сервер: 403", "Панель закрыта"]} />}>
      <Body>
        <Head />
        <EmptyState title="Недостаточно прав">Нужна роль: архитектор или системный администратор. Обновление страницы не поможет — роль выдаёт тот, у кого есть доступ к серверу.</EmptyState>
        <Note title="Спрятанная кнопка ничего не защищает" meta="V4_AUTH">Права проверяет сервер на каждом запросе; экран лишь не ведёт туда, где человек всё равно получит отказ.</Note>
      </Body>
    </Window>
  );
}

/* --- Участники и коды привязки MAX ------------------------------------- */
function ConsoleRoster({ armed, code }) {
  const [query, setQuery] = React.useState("");
  const people = [["Участник #12", "MAX привязан", "on"], ["Участник #31", "MAX не привязан", "off"], ["Участник #08", "MAX не привязан", "off"]];
  return (
    <Window title="Консоль" titleCn="值班台" meta="Участники"
      status={<StatusBar items={["GET /admin/accounts", "3 записи · пример"]} />}>
      <Body>
        <Head />
        <div className="stf-search">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="часть имени" aria-label="Поиск по ростеру" />
          <Button variant="secondary">Найти</Button>
        </div>
        {armed && <p className="stf-warn">Нажмите ещё раз, чтобы выдать код для «Участник #31». Прежний код этого участника перестанет работать.</p>}
        <div className="stf-rows">
          {people.map(([name, mark, tone], i) => (
            <div className="stf-row" key={name}>
              <span className="stf-row-copy">
                <b>{name}</b>
                <span className="stf-marks"><i className={"stf-mark is-" + tone}>{mark}</i></span>
                <small>#{[12, 31, 8][i]} · имя из ростера</small>
              </span>
              <Button variant={armed && i === 1 ? "secondary" : "secondary"} className={armed && i === 1 ? "is-armed" : ""}>
                {armed && i === 1 ? "Точно?" : "Код MAX"}
              </Button>
            </div>
          ))}
        </div>
        {code && (
          <div className="stf-code">
            <span className="stf-code-for">Участник #31 · #31</span>
            <span className="stf-code-value">1543 6364</span>
            <span className="zd-sub">Код показывается один раз: в базе остаётся только его отпечаток. Диктуйте с экрана.</span>
            <span className="stf-code-actions"><Button variant="secondary">Копировать</Button><Button variant="secondary">Скрыть</Button></span>
            <span className="stf-status">Буфер обмена недоступен — продиктуйте код с экрана.</span>
          </div>
        )}
        <Note title="Имя в ростере — то, что выдал оператор" meta="источник данных">Не то, что человек написал у себя в профиле MAX.</Note>
      </Body>
    </Window>
  );
}

/* --- Оценка дневников ------------------------------------------------- */
function ConsoleDiary({ conflict }) {
  const [rows, setRows] = React.useState([
    { id: 12, name: "Участник #12", stars: 2, bonus: false, rev: 1, note: "Сохранено: +2 REP · +1★." },
    { id: 31, name: "Участник #31", stars: 0, bonus: false, rev: 0, note: "" },
    { id: 8, name: "Участник #08", stars: 3, bonus: true, rev: 2, note: "Сохранено: +4 REP · +2★ · +1 попытка кейса." }
  ]);
  const rated = rows.filter((r) => r.rev > 0 && (r.stars || r.bonus)).length;
  const set = (id, patch) => setRows((list) => list.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  return (
    <Window title="Консоль" titleCn="值班台" meta="Дневники"
      status={<StatusBar items={["GET /diary/day", rated + " из " + rows.length + " оценено"]} />}>
      <Body>
        <div className="stf-date">
          <Button variant="secondary" aria-label="Предыдущий день">‹</Button>
          <input type="date" defaultValue="2026-09-16" aria-label="Дата записи" />
          <Button variant="secondary" aria-label="Следующий день" disabled>›</Button>
        </div>
        <p className="stf-rules">1★ — +1 REP и +1★ · 2★ — +2 и +1★ · 3★ — +4 и +2★, первый раз за день ещё попытка кейса · бонус — +1 и +1★ <b>(числа — пример: сервер берёт их из diary.json)</b></p>
        {conflict && <p className="gate-error">Оценку уже изменил другой вожатый. Лист перечитан — поставьте оценку заново.</p>}
        <span className="stf-group">Группа 1</span>
        <div className="stf-rows">
          {rows.map((r) => (
            <div className="stf-sheet-row" key={r.id}>
              <span className="stf-row-copy"><b>{r.name}</b><small>{r.rev ? "оценка от: вы" : "оценки нет"}</small></span>
              <span className="stf-controls" role="group" aria-label={"Оценка дневника: " + r.name}>
                {[0, 1, 2, 3].map((n) => (
                  <Button key={n} variant="secondary" aria-pressed={r.rev > 0 && r.stars === n}
                    onClick={() => set(r.id, { stars: n, rev: Math.max(1, r.rev), note: "Сохранено." })}>
                    {n === 0 ? "0" : n + "★"}
                  </Button>
                ))}
                <Button variant="secondary" aria-pressed={r.bonus}
                  onClick={() => set(r.id, { bonus: !r.bonus, rev: Math.max(1, r.rev), note: "Сохранено." })}>Бонус</Button>
              </span>
              {r.note && <small className="stf-row-note">{r.note}</small>}
            </div>
          ))}
        </div>
        <Note title="Бонус — единственный ручной плюс ★" meta="решено">Отдельной команды «выдать ★» у сервера нет и не будет: поощрение вне кейсов и игр идёт бонусом за запись этого дня.</Note>
        <Note title="Правка несёт ревизию" meta="конфликт вместо перезаписи">Если оценку уже поменял другой вожатый, сервер отвечает отказом, лист перечитывается, и чужая оценка не затирается. Повтор после обрыва связи идёт с тем же ключом — награда не начисляется дважды.</Note>
      </Body>
    </Window>
  );
}

/* --- Попытки кейсов ---------------------------------------------------- */
function ConsoleGrants() {
  const [amount, setAmount] = React.useState("1");
  const [group, setGroup] = React.useState("group");
  return (
    <Window title="Консоль" titleCn="值班台" meta="Попытки"
      status={<StatusBar items={["POST /cases/admin/grants", "1…7 за раз"]} />}>
      <Body>
        <Head />
        <p className="zd-sub">Выдача попыток сканера. Кому: группе целиком или отмеченным участникам.</p>
        <Select label="КОМУ" value={group} onChange={setGroup}
          options={[{ value: "group", label: "Группа 1 — целиком" }, { value: "picked", label: "Отмеченные участники" }]} />
        <Select label="СКОЛЬКО ПОПЫТОК" value={amount} onChange={setAmount}
          options={[1, 2, 3, 4, 5, 6, 7].map((n) => ({ value: String(n), label: String(n) }))} />
        <label className="zd-label" htmlFor="grantReason">ПРИЧИНА · ВИДНА В ЖУРНАЛЕ</label>
        <input id="grantReason" className="zd-codefield" style={{ font: "14px/1.4 var(--font-ui)", letterSpacing: 0, textAlign: "left" }} placeholder="за что выдаём" />
        <Button variant="confirm" confirmLabel="Точно? выдать попытки">Выдать</Button>
        <span className="zd-label">ПОСЛЕДНИЕ ВЫДАЧИ</span>
        <DataTable columns={[{ key: "who", label: "Кому", width: "46%" }, { key: "n", label: "Попыток" }, { key: "why", label: "Причина" }]}
          rows={[{ id: 1, who: "Группа 1", n: "+2", why: "вечерняя игра" }, { id: 2, who: "Участник #12", n: "+1", why: "дневник 3★" }]}
          selectedId={1} />
        <Chip tone="example">строки таблицы — пример</Chip>
        <Note title="Повтор не удваивает выдачу" meta="идемпотентность">Тот же ключ возвращает сохранённый ответ. Лимит одной выдачи — от 1 до 7 попыток, причина обязательна.</Note>
      </Body>
    </Window>
  );
}

/* --- Расписание дня: на сервере ещё нет -------------------------------- */
function ConsoleSchedule() {
  return (
    <Window title="Консоль" titleCn="值班台" meta="Расписание"
      status={<StatusBar items={["Сервер: команды нет", "Не изображаем рабочим"]} />}>
      <Body>
        <Head />
        <div className="stf-standby">
          <b>Расписание дня 日程</b>
          <span>Хранения расписания на сервере пока нет: в приложении участник видит «Маршрут ещё не активирован», а перекличка и запись на стирку подписаны как «подключится вместе с расписанием». Поэтому строки ниже — макет будущего ввода, а сохранение выключено.</span>
        </div>
        <span className="zd-label">СТРОКИ ДНЯ · ВРЕМЯ И ЧТО</span>
        <div className="stf-plan" aria-disabled="true">
          {[["08:30", "Завтрак"], ["10:00", "Занятие: китайский"], ["16:30", "Вечерняя игра"]].map(([t, what], i) => (
            <div className="stf-plan-row" key={i}>
              <input type="time" defaultValue={t} disabled aria-label={"Время строки " + (i + 1)} />
              <input defaultValue={what} disabled aria-label={"Что в строке " + (i + 1)} />
            </div>
          ))}
        </div>
        <Chip tone="example">три строки — пример раскладки, не расписание сезона</Chip>
        <span className="stf-plan-actions"><Button variant="secondary" disabled>Добавить строку</Button><Button disabled>Сохранить день</Button></span>
        <Note title="Строками «время — что»" meta="решено">Каталог готовых блоков отклонён (списка блоков ещё нет), один текст на день — тоже: «Мой день» остаётся списком по времени. Включится вместе с серверной командой.</Note>
      </Body>
    </Window>
  );
}

/* --- Собранная консоль с вкладками ------------------------------------- */
function ConsoleTabs({ start = "roster" }) {
  const [tab, setTab] = React.useState(start);
  const items = [
    { id: "roster", label: "Участники", cn: "名单" },
    { id: "diary", label: "Дневники", cn: "日记" },
    { id: "grants", label: "Попытки", cn: "机会" },
    { id: "overview", label: "Сводка", cn: "总览", hint: "нужна роль архитектора" }
  ];
  const panel = {
    roster: <ConsoleRoster armed code />,
    diary: <ConsoleDiary />,
    grants: <ConsoleGrants />,
    overview: <ConsoleDenied />
  }[tab];
  return (
    <div className="stf-body" style={{ padding: 10 }}>
      <Tabs items={items} value={tab} onChange={setTab} panel={panel} />
    </div>
  );
}

Object.assign(window, { ConsoleOverview, ConsoleDenied, ConsoleRoster, ConsoleDiary, ConsoleGrants, ConsoleSchedule, ConsoleTabs });
