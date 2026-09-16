const { Card, Note, Chip, Gauge, EmptyState, Button, Tabs, DataTable, Window, StatusBar, HubTile } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Экраны мини-приложения в MAX. Данные: сезон ещё не начался, поэтому
   почти всё — пустые состояния. Всё, что показано числом, помечено как
   пример; выдуманных людей и чисел здесь нет. */

function Today() {
  return (
    <React.Fragment>
      <h1 className="display-title">Сегодня</h1>
      <Card label="СЕЙЧАС" title="Мой день" titleCn="我的一天">
        <EmptyState title="Расписание ещё не введено">
          Вожатый вводит расписание дня в консоли — здесь появится оно, и ничего больше.
        </EmptyState>
      </Card>
      <Card title="Что нового" titleCn="新消息">
        <p className="zd-sub">С прошлого входа событий нет.</p>
      </Card>
      <Note title="Строка «Сейчас» появляется только при срочном" meta="правило экрана" />
    </React.Fragment>
  );
}

function Rep({ tab, setTab }) {
  const board = (
    <React.Fragment>
      <Card label="МОЁ МЕСТО" title="REP" titleCn="排名" action={<Chip tone="example">пример</Chip>}>
        <div className="zd-stat-row">
          <strong className="zd-stat-value">—</strong>
          <span className="zd-sub">Место появится после первой оценки дневника.</span>
        </div>
        <Gauge value={0} label="REP сезона" />
      </Card>
      <Card title="Тройка лидеров" titleCn="前三名">
        <EmptyState title="Сезон не начался">
          Полного рейтинга из шестидесяти нет: только тройка лидеров и соседи ±2 рядом с тобой.
        </EmptyState>
      </Card>
    </React.Fragment>
  );
  const diary = (
    <Card title="Дневник" titleCn="日记" action={<Button variant="primary">Написать</Button>}>
      <EmptyState title="Записей нет">
        Дневник оценивают вожатые. Имён тех, кто оценил, в ленте не бывает.
      </EmptyState>
    </Card>
  );
  return (
    <React.Fragment>
      <Tabs value={tab} onChange={setTab}
        items={[{ id: "board", label: "Рейтинг" }, { id: "diary", label: "Дневник" }]}
        panel={tab === "board" ? board : diary} />
    </React.Fragment>
  );
}

function Events({ tab, setTab }) {
  const now = (
    <EmptyState title="Сейчас ничего не идёт" action={<Button variant="secondary">По коду комнаты</Button>}>
      Вечерние и дневные игры откроются, когда вожатый запустит комнату.
    </EmptyState>
  );
  const later = (
    <Card title="Позже" titleCn="稍后">
      <p className="zd-sub">Расписание игр приходит вместе с расписанием дня.</p>
    </Card>
  );
  return (
    <React.Fragment>
      <h1 className="display-title">Ивенты</h1>
      <Tabs value={tab} onChange={setTab}
        items={[{ id: "now", label: "Идёт сейчас" }, { id: "later", label: "Позже" }]}
        panel={tab === "now" ? now : later} />
      <Window title="Окно игры" titleCn="活动" meta="макет"
        status={<StatusBar items={["Пример в макете", "Одно главное действие"]} />}>
        <p className="zd-sub">У окна игры одно главное действие и ссылка «Как играть?».</p>
        <div className="zd-actions">
          <Button variant="action">Сдать станцию</Button>
          <Button variant="secondary">Как играть?</Button>
        </div>
      </Window>
    </React.Fragment>
  );
}

function Cases() {
  return (
    <React.Fragment>
      <h1 className="display-title">Кейсы</h1>
      <Card label="СКАНЕР" title="Попытки" titleCn="扫描">
        <Gauge value={0} segments={5} label="Попытки" />
        <p className="zd-sub">Попытки выдаёт вожатый. Пока их нет.</p>
      </Card>
      <Card title="Последние сигналы" titleCn="信号">
        <EmptyState title="Сигналов ещё не было">Здесь будут последние три.</EmptyState>
      </Card>
      <Card title="Коллекция" titleCn="收藏">
        <EmptyState title="Коллекция пуста" action={<Button variant="secondary">В Мастерскую</Button>}>
          Плитки получают подсказки «дубль · обмен», когда имплант повторяется.
        </EmptyState>
      </Card>
    </React.Fragment>
  );
}

const SECTIONS = [
  ["Встречи", "见面"], ["Обмен", "交换"], ["Антивирус", "杀毒"],
  ["Мастерская", "工坊"], ["Архив", "档案"], ["Карта кампуса", "校园地图"],
  ["Магазин", "商店"], ["Дневник", "日记"]
];

function More({ onShop }) {
  return (
    <React.Fragment>
      <h1 className="display-title">Ещё</h1>
      <Card title="Разделы" titleCn="更多">
        <div className="hub-grid">
          {SECTIONS.map(([n, cn]) => (
            <HubTile key={n} name={n} nameCn={cn} onClick={n === "Магазин" ? onShop : undefined} />
          ))}
        </div>
      </Card>
      <Note title="Настройки вида и помощь — в профиле" meta="без дублей между экранами" />
    </React.Fragment>
  );
}

function Shop({ tab, setTab, selected, setSelected }) {
  const rows = [
    { id: "wall", name: "Обои «Прилив»", price: "120" },
    { id: "frame", name: "Рамка профиля", price: "90" },
    { id: "sound", name: "Звук открытия кейса", price: "60" }
  ];
  const shelf = (
    <React.Fragment>
      <Card label="КУПОН" title="+30 минут свободы" titleCn="自由时间"
        action={<Button variant="confirm" confirmLabel="Точно? −300★">300 ★</Button>}>
        <p className="zd-sub">Цены, награды и лимиты берутся как есть — экономика не меняется.</p>
      </Card>
      <Card title="Косметика" titleCn="装饰" action={<Chip tone="example">пример витрины</Chip>}>
        <DataTable columns={[{ key: "name", label: "Название" }, { key: "price", label: "★", width: 56 }]}
          rows={rows} selectedId={selected} onSelect={setSelected} />
      </Card>
    </React.Fragment>
  );
  const mine = <EmptyState title="Ничего не куплено">Купленное появится здесь.</EmptyState>;
  return (
    <React.Fragment>
      <h1 className="display-title">Магазин</h1>
      <Tabs value={tab} onChange={setTab}
        items={[{ id: "shelf", label: "Витрина" }, { id: "mine", label: "Моё" }]}
        panel={tab === "shelf" ? shelf : mine} />
    </React.Fragment>
  );
}

Object.assign(window, { Today, Rep, Events, Cases, More, Shop, SECTIONS });
