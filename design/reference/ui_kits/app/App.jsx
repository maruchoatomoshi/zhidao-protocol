const { PhoneFrame, AppHeader, BottomNav, Window, Tabs, StatusBar, Switch, Select, Checkbox, Note, Card } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Оболочка мини-приложения. Оформление и тема переключаются в профиле —
   как в самом приложении, а не в отдельном меню макета. */

function Profile({ skin, setSkin, theme, setTheme, motion, setMotion, tab, setTab }) {
  const view = (
    <React.Fragment>
      <fieldset className="zd-fieldset"><legend>Вид</legend>
        <Select label="Оформление" value={skin} onChange={setSkin}
          options={[{ value: "aqua", label: "Аква" }, { value: "luna", label: "Луна-Аква" }]} />
        <Switch checked={theme === "dark"} onChange={(v) => setTheme(v ? "dark" : "light")}
          label="Ночная тема" labelCn="夜间" />
        <Switch checked={motion === "full"} onChange={(v) => setMotion(v ? "full" : "none")}
          label="Анимации" labelCn="动画" hint="Системное «уменьшить движение» тоже учитывается" />
        <Checkbox checked={false} disabled label="Вибрация (позже)" />
      </fieldset>
      <Note title="Настройки вида живут только здесь" meta="без дублей между экранами" />
    </React.Fragment>
  );
  const help = (
    <Card title="Помощь" titleCn="帮助">
      <p className="zd-sub">Вопросы по сезону — вожатому. Сюжет ведёт Архитектор.</p>
    </Card>
  );
  return (
    <Window title="Свойства: учётная запись" titleCn="我的" icon="../../assets/icons/desktop-person.svg"
      status={<StatusBar items={["Привязано к MAX", "Сезон не начался"]} />}>
      <Tabs value={tab} onChange={setTab}
        items={[{ id: "view", label: "Вид" }, { id: "help", label: "Помощь" }]}
        panel={tab === "view" ? view : help} />
    </Window>
  );
}

function App() {
  const [skin, setSkin] = React.useState("aqua");
  const [theme, setTheme] = React.useState("light");
  const [motion, setMotion] = React.useState("full");
  const [screen, setScreen] = React.useState("today");
  const [repTab, setRepTab] = React.useState("board");
  const [eventsTab, setEventsTab] = React.useState("now");
  const [shopTab, setShopTab] = React.useState("shelf");
  const [profileTab, setProfileTab] = React.useState("view");
  const [sel, setSel] = React.useState("wall");

  const body = {
    today: <Today />,
    rep: <Rep tab={repTab} setTab={setRepTab} />,
    events: <Events tab={eventsTab} setTab={setEventsTab} />,
    cases: <Cases />,
    more: <More onShop={() => setScreen("shop")} />,
    shop: <Shop tab={shopTab} setTab={setShopTab} selected={sel} setSelected={setSel} />,
    profile: <Profile skin={skin} setSkin={setSkin} theme={theme} setTheme={setTheme}
      motion={motion} setMotion={setMotion} tab={profileTab} setTab={setProfileTab} />
  }[screen];

  const navValue = screen === "shop" || screen === "profile" ? "more" : screen;

  return (
    <PhoneFrame skin={skin} theme={theme} motion={motion}
      label={screen + " — " + (skin === "luna" ? "Луна-Аква" : "Аква") + (theme === "dark" ? ", ночь" : "")}
      header={<AppHeader stars={212} onProfile={() => setScreen("profile")} logo="../../assets/zhidao-dragon-logo-256.png" />}
      nav={<BottomNav value={navValue} onChange={setScreen} items={window.ZHIDAOProtocolDesignSystem_ad77c0.NAV_ITEMS.map((i) => ({ ...i, icon: "../../" + i.icon }))} />}>
      {body}
    </PhoneFrame>
  );
}

Object.assign(window, { App, Profile });
