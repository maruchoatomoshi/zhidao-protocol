const { Window, Card, Note, Button, StatusBar, Chip } = window.ZHIDAOProtocolDesignSystem_ad77c0;

/* Решения от 2026-09-16:
   — «Встречи»: кусок появляется без указания, от кого. Пометка места и
     времени отклонена (почти называет человека), голый счётчик отклонён
     (без кусков теряется сам пазл).
   — «Карта»: туман мягкими пятнами вокруг посещённых точек. Плитка
     отклонена (выглядит точной границей, а точность GPS не подразумеваем),
     список без тумана отклонён (туман, открывающийся ногами, — заявленная
     механика продукта). */

const Body = ({ children }) => <div className="spy-body" style={{ padding: 0, gap: 10 }}>{children}</div>;

function MeetScreen() {
  return (
    <Window title="Встречи" titleCn="见面" meta="пазл встреч"
      status={<StatusBar items={["Сервер: 4 куска из 9", "Пример в макете"]} />}>
      <Body>
        <p className="spy-lead">Кусок картинки приходит только от другого человека. От кого именно — не показывается.</p>
        <div className="meet-grid" style={{ "--grid": 3 }}>
          {Array.from({ length: 9 }, (_, i) => (
            <span className={i < 4 ? (i === 3 ? "meet-tile is-new" : "meet-tile") : "meet-tile is-missing"} key={i}
              style={i < 4 ? { background: "linear-gradient(145deg,#d9f1fb,#8fcde6)" } : undefined}>
              {i < 4 ? "" : "?"}
            </span>
          ))}
        </div>
        <div className="meet-offer">
          <span className="zd-label">ТВОЙ КОД РУКОПОЖАТИЯ</span>
          <span className="meet-code">4821</span>
          <span className="spy-hint">Код называют друг другу при встрече</span>
        </div>
        <span className="zd-label">СОБРАННЫЕ КАРТИНКИ</span>
        <div className="meet-gallery">
          <span className="meet-thumb"><span /><b>Прилив</b><small className="zd-cn">潮水</small></span>
          <span className="meet-thumb"><span style={{ filter: "grayscale(1)", opacity: .5 }} /><b>Геккон</b><small className="zd-cn">壁虎</small><small className="zd-sub">не собрана</small></span>
        </div>
        <Note title="Кто дал кусок — не показывается" meta="приватность">Ни имени, ни места, ни времени: иначе встречу можно было бы угадать.</Note>
      </Body>
    </Window>
  );
}

function MapScreen() {
  return (
    <Window title="Карта кампуса" titleCn="校园地图" meta="туман"
      status={<StatusBar items={["Схема — подложка макета", "География от провайдера"]} />}>
      <Body>
        <p className="spy-lead">Туман расходится вокруг тех мест, где ты уже был. Открывается ногами.</p>
        <div className="map-plate">
          <div className="map-fog-soft" />
          <span className="map-plate-note">схема-подложка, не настоящая геометрия</span>
        </div>
        <p className="zd-sub">Граница нарочно размытая: приложение не обещает точность GPS.</p>
        <div className="campus-mark-card">
          <span className="campus-mark-label">МЕТКА</span>
          <span className="campus-mark-text">Осторожно: геккон</span>
          <span className="campus-mark-zh">壁虎</span>
          <span className="campus-mark-meta">метку поставил Архитектор</span>
          <div className="campus-mark-actions">
            <Button variant="secondary">Открыть место</Button>
          </div>
        </div>
        <Note title="Кто где ходил — не показывается" meta="приватность">Туман личный: он показывает твои места, а не чужие.</Note>
      </Body>
    </Window>
  );
}

Object.assign(window, { MeetScreen, MapScreen });
