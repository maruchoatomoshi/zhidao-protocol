"use strict";

/* Фоновая музыка для участнического приложения.

   Три вещи, определяющие устройство этого файла:

   1. Браузер не даёт запустить звук до жеста пользователя. `audio.play()`
      отклоняется с NotAllowedError, и так во всех современных браузерах, а на
      мобильных — без исключений. Поэтому «включить при заходе» здесь означает
      «взвестись и стартовать на первом касании», а не «играть с загрузки».
   2. Пока звук заблокирован, экран не должен показывать, что музыка идёт.
      Врать про состояние хуже, чем молчать.
   3. Выбор «не хочу музыку» запоминается на устройстве и уважается до тех пор,
      пока человек сам не нажмёт play. */

(function () {
  const STORE_KEY = "zhidao.v4.audio";
  const PLAYLIST_URL = "./assets/audio/playlist.json";
  const DEFAULT_VOLUME = 0.5;

  const widget = document.querySelector("[data-player]");
  if (!widget) return;

  const audio = widget.querySelector("[data-player-audio]");
  const titleEl = widget.querySelector("[data-player-title]");
  const subEl = widget.querySelector("[data-player-sub]");
  const toggleBtn = widget.querySelector("[data-player-toggle]");
  const nextBtn = widget.querySelector("[data-player-next]");
  if (!audio || !toggleBtn) return;

  let tracks = [];
  let index = 0;
  let armed = false;      // ждём первого жеста, чтобы стартовать
  const failed = new Set();   // индексы треков, которые не открылись
  let dead = false;           // весь список обойдён, живых файлов нет

  /* Хранилище может бросать исключение: приватное окно, запрет на данные сайта,
     снятие превью. Ни одно из этих мест не повод ломать приложение. */
  function readPref() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function writePref(patch) {
    try {
      const next = Object.assign({ enabled: true, volume: DEFAULT_VOLUME }, readPref(), patch);
      localStorage.setItem(STORE_KEY, JSON.stringify(next));
    } catch (err) {
      /* Предпочтение не сохранилось — сеанс всё равно должен работать. */
    }
  }

  const pref = Object.assign({ enabled: true, volume: DEFAULT_VOLUME }, readPref());

  function lcd(title, sub) {
    if (titleEl) titleEl.textContent = title;
    if (subEl) subEl.textContent = sub;
  }

  function setPlayingUi(playing) {
    widget.classList.toggle("is-playing", playing);
    toggleBtn.setAttribute("aria-pressed", playing ? "true" : "false");
    toggleBtn.setAttribute("aria-label", playing ? "Выключить музыку" : "Включить музыку");
    toggleBtn.textContent = playing ? "▮▮" : "▶";
  }

  function currentTrack() {
    return tracks[index] || null;
  }

  function showTrack() {
    const t = currentTrack();
    if (!t) return;
    lcd(t.title || "БЕЗ НАЗВАНИЯ", [t.artist, `${index + 1}/${tracks.length}`].filter(Boolean).join(" · "));
    if ("mediaSession" in navigator && window.MediaMetadata) {
      try {
        navigator.mediaSession.metadata = new window.MediaMetadata({
          title: t.title || "",
          artist: t.artist || "",
          album: "ZHIDAO · Hainan",
        });
      } catch (err) {
        /* Метаданные — украшение, их отсутствие ничего не ломает. */
      }
    }
  }

  function load(i) {
    if (!tracks.length) return;
    index = ((i % tracks.length) + tracks.length) % tracks.length;
    audio.src = currentTrack().src;
    showTrack();
  }

  function play() {
    if (!tracks.length) return;
    if (!audio.src) load(index);
    const attempt = audio.play();
    if (!attempt || !attempt.catch) return;
    attempt.catch(() => {
      // Браузер не пустил (нет жеста) либо файл не открылся. В обоих случаях
      // состояние остаётся «не играет» — экран не должен показывать обратное.
      setPlayingUi(false);
      arm();
    });
  }

  function stop(remember) {
    audio.pause();
    setPlayingUi(false);
    if (remember) {
      pref.enabled = false;
      writePref({ enabled: false });
      lcd("МУЗЫКА ВЫКЛЮЧЕНА", "▶ — ВКЛЮЧИТЬ СНОВА");
    }
  }

  /* Взвод: первый же жест по документу снимает запрет браузера. Слушатели
     одноразовые, иначе они будут срабатывать до конца сеанса впустую. */
  function arm() {
    if (armed || !pref.enabled || !tracks.length) return;
    armed = true;
    const fire = () => {
      armed = false;
      document.removeEventListener("pointerdown", fire);
      document.removeEventListener("keydown", fire);
      if (pref.enabled) play();
    };
    document.addEventListener("pointerdown", fire, { once: true });
    document.addEventListener("keydown", fire, { once: true });
  }

  audio.addEventListener("playing", () => {
    failed.delete(index);
    setPlayingUi(true);
    showTrack();
  });
  audio.addEventListener("pause", () => setPlayingUi(false));
  audio.addEventListener("ended", () => { advance(); });

  /* Битый или отсутствующий файл — переходим к следующему живому. Считать
     неудачи подряд недостаточно: удачное воспроизведение обнуляло счётчик, и
     список мог гоняться по кругу, засыпая сервер запросами. Поэтому каждый
     непрочитанный трек помечается, и когда помечены все — плеер замолкает
     насовсем, до явного нажатия play. */
  audio.addEventListener("error", () => {
    setPlayingUi(false);
    if (dead || !tracks.length) return;
    failed.add(index);
    if (failed.size >= tracks.length) {
      dead = true;
      lcd("ЗВУК НЕДОСТУПЕН", "НИ ОДИН ФАЙЛ НЕ ОТКРЫЛСЯ");
      return;
    }
    advance();
  });

  /* Следующий трек, пропуская уже провалившиеся. */
  function advance() {
    if (dead || !tracks.length) return;
    for (let step = 1; step <= tracks.length; step += 1) {
      const candidate = (index + step) % tracks.length;
      if (!failed.has(candidate)) {
        load(candidate);
        if (pref.enabled) play();
        return;
      }
    }
    dead = true;
    lcd("ЗВУК НЕДОСТУПЕН", "НИ ОДИН ФАЙЛ НЕ ОТКРЫЛСЯ");
  }

  toggleBtn.addEventListener("click", () => {
    if (!tracks.length) return;
    if (audio.paused) {
      pref.enabled = true;
      writePref({ enabled: true });
      // Нажатие play — это осознанная повторная попытка: даём файлам,
      // не открывшимся раньше, ещё один шанс (сеть могла вернуться).
      failed.clear();
      dead = false;
      play();
    } else {
      stop(true);
    }
  });

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (!tracks.length) return;
      advance();
    });
  }

  audio.volume = typeof pref.volume === "number" ? pref.volume : DEFAULT_VOLUME;
  audio.preload = "none";   // не тянуть музыку, пока её не попросили

  fetch(PLAYLIST_URL, { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      const list = data && Array.isArray(data.tracks) ? data.tracks : [];
      tracks = list.filter((t) => t && typeof t.src === "string" && t.src);
      if (!tracks.length) return;   // плейлист пуст — виджет остаётся в STANDBY

      if (data.shuffle) {
        for (let i = tracks.length - 1; i > 0; i -= 1) {
          const j = Math.floor(Math.random() * (i + 1));
          [tracks[i], tracks[j]] = [tracks[j], tracks[i]];
        }
      }

      if (nextBtn) nextBtn.disabled = tracks.length < 2;
      toggleBtn.disabled = false;
      load(0);

      if (pref.enabled) {
        play();   // сработает сразу, если браузер уже доверяет странице
        arm();    // иначе стартуем на первом касании
      } else {
        lcd("МУЗЫКА ВЫКЛЮЧЕНА", "▶ — ВКЛЮЧИТЬ СНОВА");
      }
    })
    .catch(() => {
      /* Плейлиста нет — это нормальное состояние до заливки песен.
         Виджет молчит и продолжает показывать STANDBY. */
    });
}());
