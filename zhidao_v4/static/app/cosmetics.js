"use strict";

/* Косметика на экране: обои, рамка профиля и звуки.

   Что надето, знает сервер; магазин (shop.js) присылает событие
   «zhidao:cosmetics», а этот файл только применяет: ставит data-wallpaper на
   <html>, data-frame на аватары и выбирает набор звуков.

   Звуки синтезируются WebAudio — ни одной чужой записи. Без купленного
   набора приложение молчит; с набором звук можно выключить в «Ещё → Звуки»,
   выбор хранится на этом устройстве. */

(function () {
  const MUTE_KEY = "zhidao.v4.sounds.muted";
  const NAMES = { snd_modem: "Модем", snd_arcade: "Аркада", snd_crystal: "Кристалл" };

  // Каждое событие — короткая мелодия: [частота, длительность, форма волны].
  const PACKS = {
    snd_modem: {
      open: [[1180, 0.05, "square"], [1760, 0.05, "square"], [980, 0.09, "sawtooth"]],
      rare: [[880, 0.06, "square"], [1320, 0.06, "square"], [1760, 0.06, "square"], [2640, 0.14, "sawtooth"]],
      buy: [[2100, 0.04, "square"], [0, 0.03], [2100, 0.04, "square"]],
      win: [[660, 0.08, "sawtooth"], [990, 0.08, "sawtooth"], [1320, 0.16, "square"]],
    },
    snd_arcade: {
      open: [[523, 0.06, "square"], [659, 0.06, "square"], [784, 0.1, "square"]],
      rare: [[523, 0.05, "square"], [659, 0.05, "square"], [784, 0.05, "square"], [1047, 0.18, "square"]],
      buy: [[988, 0.05, "square"], [1319, 0.1, "square"]],
      win: [[784, 0.08, "square"], [784, 0.08, "square"], [1047, 0.2, "square"]],
    },
    snd_crystal: {
      open: [[1568, 0.12, "sine"], [2093, 0.2, "sine"]],
      rare: [[1319, 0.1, "sine"], [1760, 0.1, "sine"], [2349, 0.1, "sine"], [3136, 0.3, "sine"]],
      buy: [[2637, 0.14, "sine"]],
      win: [[1047, 0.12, "triangle"], [1568, 0.12, "triangle"], [2093, 0.28, "sine"]],
    },
  };

  let pack = null;
  let audio = null;
  let muted = false;
  try { muted = localStorage.getItem(MUTE_KEY) === "1"; } catch (_) { /* хранилище недоступно — звук включён */ }

  function melody(notes) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      let at = audio.currentTime + 0.01;
      for (const [frequency, duration, wave] of notes) {
        if (frequency > 0) {
          const osc = audio.createOscillator();
          const gain = audio.createGain();
          osc.type = wave || "sine";
          osc.frequency.value = frequency;
          gain.gain.setValueAtTime(0.0001, at);
          gain.gain.exponentialRampToValueAtTime(0.12, at + 0.01);
          gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
          osc.connect(gain).connect(audio.destination);
          osc.start(at);
          osc.stop(at + duration + 0.02);
        }
        at += duration;
      }
    } catch (_) {
      // В некоторых WebView звук запрещён до жеста пользователя — просто молчим.
    }
  }

  function drawSoundSetting() {
    document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
      const label = button.querySelector("[data-sound-value]");
      if (!pack) {
        label.textContent = "Нет набора";
        button.setAttribute("aria-pressed", "false");
      } else {
        label.textContent = muted ? `${NAMES[pack]} · выкл.` : NAMES[pack];
        button.setAttribute("aria-pressed", String(!muted));
      }
    });
  }

  window.ZhidaoSounds = {
    play(event) {
      if (muted || !pack || !PACKS[pack][event]) return;
      melody(PACKS[pack][event]);
    },
    preview(code, event = "rare") {
      if (PACKS[code] && PACKS[code][event]) melody(PACKS[code][event]);
    },
  };

  function apply(equipped) {
    const root = document.documentElement;
    if (equipped && equipped.wallpaper) root.dataset.wallpaper = equipped.wallpaper;
    else delete root.dataset.wallpaper;
    document.querySelectorAll(".profile-avatar").forEach((avatar) => {
      if (equipped && equipped.frame) avatar.dataset.frame = equipped.frame;
      else delete avatar.dataset.frame;
    });
    pack = equipped && equipped.sounds && PACKS[equipped.sounds] ? equipped.sounds : null;
    drawSoundSetting();
  }

  window.addEventListener("zhidao:cosmetics", (event) => apply(event.detail || {}));
  window.addEventListener("zhidao:auth", (event) => {
    if (!event.detail || event.detail.mode !== "authenticated") apply({});
  });

  document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!pack) {
        if (typeof window.showToast === "function") window.showToast("Наборы звуков продаются на витрине магазина.");
        return;
      }
      muted = !muted;
      try { localStorage.setItem(MUTE_KEY, muted ? "1" : "0"); } catch (_) { /* выбор живёт до перезагрузки */ }
      drawSoundSetting();
      if (!muted) window.ZhidaoSounds.play("buy");
    });
  });
  drawSoundSetting();
}());
