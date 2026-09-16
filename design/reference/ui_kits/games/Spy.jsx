const { Window, Card, Note, Button, StatusBar, LcdPanel } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* «Шпион» — настольная игра на один вечер: код комнаты, карта роли,
   обсуждение, голосование, вскрытие. Разметка из games.css. */

function SpyLobby() {
  return (
    <Window title="Шпион" titleCn="间谍" meta="лобби"
      status={<StatusBar items={["Комната открыта", "Пример в макете"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <p className="spy-lead">Все получают одно слово, шпион — другое. Найдите шпиона обсуждением.</p>
        <div className="spy-code-plate">
          <span className="spy-label">КОД КОМНАТЫ</span>
          <span className="spy-code">K7QX</span>
          <span className="spy-hint">Код называет вожатый</span>
        </div>
        <div className="spy-settings">
          <span className="spy-label">ШПИОНОВ</span>
          <div className="spy-segmented">
            <button className="btn btn-secondary" aria-pressed="true" type="button"><span>1</span></button>
            <button className="btn btn-secondary" aria-pressed="false" type="button"><span>2</span></button>
          </div>
        </div>
        <div className="spy-players">
          <span className="spy-label">В КОМНАТЕ · 6</span>
          {[["готов", true], ["готов", true], ["ждёт", false], ["готов", true], ["ждёт", false], ["готов", true]].map(([s, ok], i) => (
            <div className="spy-player" key={i}>
              <span className="spy-avatar"><i className={ok ? "spy-dot is-ready" : "spy-dot"} /></span>
              <span className="spy-player-name">Игрок {i + 1}<small>{s}</small></span>
              <span className="spy-score">—</span>
            </div>
          ))}
        </div>
        <Note title="Имён в списке не будет" meta="приватность">На месте примеров сервер пришлёт только тех, кто вошёл по коду.</Note>
        <div className="spy-actions">
          <Button variant="primary">Начать раунд</Button>
          <Button variant="secondary">Как играть?</Button>
        </div>
      </div>
    </Window>
  );
}

function SpyRound() {
  return (
    <Window title="Шпион" titleCn="间谍" meta="раунд 1"
      status={<StatusBar items={["Пример в макете", "Обсуждение"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <LcdPanel value="04:12" ghost="88:88" caption="ДО ГОЛОСОВАНИЯ" />
        <div className="spy-card is-open">
          <span className="spy-card-face">
            <span className="spy-label">ТВОЁ СЛОВО</span>
            <span className="spy-zh">海滩</span>
            <span className="spy-pinyin">hǎitān</span>
            <span className="spy-ru">пляж</span>
            <span className="spy-role zd-sub">Ты не шпион. Говори так, чтобы свои поняли, а шпион — нет.</span>
          </span>
        </div>
        <p className="spy-banner">Карту видишь только ты. Экран не показывают соседу.</p>
        <div className="spy-actions">
          <Button variant="action">Готов голосовать</Button>
          <Button variant="secondary">Как играть?</Button>
        </div>
        <div className="zd-chatlog">
          <p className="zd-chatline is-join"><time>20:14</time>участник вошёл</p>
          <p className="zd-chatline"><time>20:15</time>раунд начался</p>
          <p className="zd-chatline is-away"><time>20:18</time>участник отошёл</p>
        </div>
      </div>
    </Window>
  );
}

function SpyResult() {
  return (
    <Window title="Шпион" titleCn="间谍" meta="итог раунда"
      status={<StatusBar items={["Пример в макете", "Счёт ушёл в REP"]} />}>
      <div className="spy-body" style={{ padding: 0, gap: 10 }}>
        <div className="spy-reveal">
          <span className="spy-verdict">ШПИОН НАЙДЕН</span>
          <h3>Слово было 海滩 hǎitān — пляж</h3>
          <span className="spy-hint">Шпион знал «бассейн» 游泳池</span>
          {/* Числа наград не рисуем: в экономике «Шпиона» их пока нет
              (решение от 2026-09-16). Появятся настоящие — подставим. */}
          <ul className="spy-points">
            <li>+★ угадавшим</li>
          </ul>
        </div>
        <details className="spy-places">
          <summary>Слова этого вечера</summary>
          <div className="spy-place-grid">
            {[["海滩","пляж"],["食堂","столовая"],["图书馆","библиотека"],["操场","стадион"]].map(([zh, ru]) => (
              <span className="spy-place" key={zh}><b>{zh}</b><span>{ru}</span></span>
            ))}
          </div>
        </details>
        <Note title="Кто как голосовал — не показываем" meta="приватность">В итоге только слово, роль и награда.</Note>
        <div className="spy-actions">
          <Button variant="primary">Ещё раунд</Button>
          <Button variant="secondary">Выйти из комнаты</Button>
        </div>
      </div>
    </Window>
  );
}

Object.assign(window, { SpyLobby, SpyRound, SpyResult });
