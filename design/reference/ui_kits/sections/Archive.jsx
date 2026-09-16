const { Window, Card, Note, Button, StatusBar } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Архив скрытых файлов 档案: сюжет Архитектора по местам кампуса.
   Разметка из story.css — окно фрагмента в духе нулевых, архив строками,
   послание словами, финал. Поверхность фрагмента задаётся data-surface. */

const Body = ({ children }) => <div className="spy-body" style={{ padding: 0, gap: 10 }}>{children}</div>;

function ArchiveScreen() {
  return (
    <Window title="Архив скрытых файлов" titleCn="档案" meta="сюжет Архитектора"
      status={<StatusBar items={["Сервер: 3 фрагмента из 9", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Фрагменты открываются по местам кампуса. Каждый добавляет слово в послание.</p>
        <span className="zd-label">ПОСЛАНИЕ</span>
        <p className="story-message">
          <span className="story-word is-found">Море</span>
          <span className="story-word is-found">помнит</span>
          <span className="story-word">·····</span>
          <span className="story-word is-found">кто</span>
          <span className="story-word">·····</span>
          <span className="story-word">·····</span>
        </p>
        <div className="story-list">
          <div className="story-row">
            <span className="story-row-info"><b>Фрагмент 1 · Стадион</b><small>открыт · 操场</small></span>
            <Button variant="secondary">Читать</Button>
          </div>
          <div className="story-row">
            <span className="story-row-info"><b>Фрагмент 2 · Библиотека</b><small>открыт · 图书馆</small></span>
            <Button variant="secondary">Читать</Button>
          </div>
          <div className="story-row is-locked_place">
            <span className="story-row-info"><b>Фрагмент 4 · Столовая</b><small>нужно прийти на место · 食堂</small></span>
            <Button variant="secondary" disabled>Закрыт</Button>
          </div>
          <div className="story-row is-locked_previous">
            <span className="story-row-info"><b>Фрагмент 5</b><small>сначала предыдущий</small></span>
            <Button variant="secondary" disabled>Закрыт</Button>
          </div>
        </div>
        <Note title="Кто ещё открыл фрагмент — не показывается" meta="приватность">Архив личный: чужого прогресса в нём нет.</Note>
      </Body>
    </Window>
  );
}

function ArchiveFragment() {
  return (
    <Window title="Архив скрытых файлов" titleCn="档案" meta="фрагмент"
      status={<StatusBar items={["Пример в макете", "Поверхность: место"]} />}>
      <Body>
        <div className="story-dialog" data-surface="place">
          <div className="story-titlebar">
            <h2>Фрагмент 3 — у моря</h2>
            <button type="button" aria-label="Закрыть">×</button>
          </div>
          <div className="story-dialog-body">
            <p className="story-line"><span className="story-sender">Архитектор:</span> то, что ты ищешь, лежит там, где вода касается дороги.</p>
            <p className="story-question">Какое слово написано на камне? 石头</p>
            <div className="story-form">
              <input placeholder="Слово" readOnly />
              <Button variant="primary">Ответить</Button>
            </div>
            <details className="story-hint"><summary>Подсказка</summary><p className="story-line">Прочитай вслух по слогам.</p></details>
          </div>
        </div>
        <div className="story-place-card">
          <span className="story-place-label">СИГНАЛ НА КАРТЕ</span>
          <p>Фрагмент привязан к месту: он откроется, когда ты будешь рядом.</p>
          <Button variant="secondary">Открыть карту кампуса</Button>
        </div>
      </Body>
    </Window>
  );
}

function ArchiveFinale() {
  return (
    <Window title="Архив скрытых файлов" titleCn="档案" meta="финал"
      status={<StatusBar items={["Пример в макете", "Послание собрано"]} />}>
      <Body>
        <div id="storyFinale">
          <img className="story-architect" src="../../assets/implants/jade_warden.webp" alt="" />
          <p className="story-epilogue">Море помнит тех, кто пришёл сюда учиться, а не побеждать.</p>
          <p className="story-signature">Архитектор 建筑师</p>
          <p className="story-reward">Награда за собранное послание — по решению вожатого</p>
        </div>
        <Note title="Числа награды не рисуем" meta="правило экономики">Награда за финал сюжета в экономике пока не назначена.</Note>
      </Body>
    </Window>
  );
}

Object.assign(window, { ArchiveScreen, ArchiveFragment, ArchiveFinale });
