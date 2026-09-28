"use strict";

/* Метки на кампусе — клиент (сервер: zhidao_v4/beacons.py, V4_GAMES.md §3.7).

   У точки висит табличка с QR. Игра засчитывает ход у точки со сканом этой
   таблички и только рядом с ней: сервер сверяет код таблички и GPS. Здесь —
   только чтение кода и позиции, решает сервер.

   Как читается код:
   - в MAX — встроенным сканером WebApp.openCodeReader (без выбора из
     галереи: сканируют табличку, а не картинку);
   - вне MAX или если сканер не открылся — окно, куда вводят код, напечатанный
     под QR (две группы по пять знаков).

   Игры подключаются одной функцией: withScan(send) — сначала ход как раньше,
   а если сервер ответил 428 («отсканируйте метку»), открывается сканер и ход
   повторяется со сканом. Поэтому игре не нужно знать, где уже висят метки.

   Адрес с таблички, открытый обычной камерой телефона (…/app/#m=…), —
   это отметка у места: после входа приложение само отправляет её с GPS. */

(function () {
  const inMax = () => Boolean(window.WebApp && window.WebApp.initData && window.WebApp.openCodeReader);

  function position() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("GPS недоступен на этом устройстве. Метка засчитывается только вместе с геопозицией."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => reject(new Error(err.code === err.PERMISSION_DENIED
          ? "Доступ к геопозиции закрыт. Метка засчитывается только вместе с ней — разрешите геолокацию."
          : "Не удалось определить позицию. Выйдите под открытое небо и попробуйте ещё раз.")),
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
    });
  }

  function textOf(result) {
    if (typeof result === "string") return result;
    if (!result || typeof result !== "object") return "";
    return String(result.value ?? result.data ?? result.text ?? result.result ?? result.code ?? "");
  }

  // Ручной ввод кода с таблички — вне MAX и когда сканер не открылся.
  function askCode(pointName) {
    return new Promise((resolve, reject) => {
      const dialog = document.createElement("dialog");
      dialog.className = "case-dialog beacon-dialog";
      dialog.setAttribute("aria-labelledby", "beaconDialogTitle");
      const bar = document.createElement("div");
      bar.className = "case-titlebar";
      const title = document.createElement("h2");
      title.id = "beaconDialogTitle";
      title.textContent = "Метка";
      bar.append(title);
      const form = document.createElement("form");
      form.method = "dialog";
      form.className = "beacon-form";
      const lead = document.createElement("p");
      lead.textContent = pointName
        ? `Введите код с таблички у точки «${pointName}» — он под QR.`
        : "Введите код с таблички — он напечатан под QR.";
      const input = document.createElement("input");
      input.type = "text";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.maxLength = 13;
      input.placeholder = "XXXXX-XXXXX";
      input.setAttribute("aria-label", "Код метки");
      const row = document.createElement("div");
      row.className = "beacon-actions";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn btn-secondary";
      cancel.textContent = "Отмена";
      const ok = document.createElement("button");
      ok.type = "submit";
      ok.className = "btn btn-primary";
      ok.textContent = "Готово";
      row.append(cancel, ok);
      form.append(lead, input, row);
      dialog.append(bar, form);
      document.body.append(dialog);
      let done = false;
      const finish = (value) => {
        if (done) return;
        done = true;
        dialog.close();
        setTimeout(() => dialog.remove(), 400);
        if (value) resolve(value);
        else reject(Object.assign(new Error("Сканирование отменено."), { cancelled: true }));
      };
      cancel.addEventListener("click", () => finish(""));
      form.addEventListener("submit", (event) => { event.preventDefault(); finish(input.value.trim()); });
      dialog.addEventListener("cancel", () => finish(""));
      dialog.showModal();
      input.focus();
    });
  }

  async function read(pointName) {
    if (inMax()) {
      try {
        const text = textOf(await window.WebApp.openCodeReader(false));
        if (text) return text;
      } catch (error) {
        // Отмена сканера — это отмена; другая ошибка — даём ввести код руками.
        if (error && (error.error === "cancelled" || /cancel/i.test(String(error.error || error.message || "")))) {
          throw Object.assign(new Error("Сканирование отменено."), { cancelled: true });
        }
      }
    }
    return askCode(pointName);
  }

  // Ход с меткой: send(extra) шлёт запрос игры, добавив к телу extra.
  // known — точка уже известна как «с меткой»: сканер открывается сразу.
  async function withScan(send, { known = false, pointName = "" } = {}) {
    if (known) return send({ beacon: await read(pointName) });
    try {
      return await send({});
    } catch (error) {
      if (error.status !== 428) throw error;
      return send({ beacon: await read(pointName) });
    }
  }

  // --- отметка у места: кнопка на карте и адрес с таблички ----------------------

  function csrf() {
    const cookie = document.cookie.split("; ").find((v) => v.startsWith("zhidao_v4_csrf="));
    return cookie ? decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) : "";
  }

  async function checkIn(text) {
    const coords = await position();
    const response = await fetch("/api/v4/beacons/scan", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify({ text, lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Метка не засчитана.");
    window.ZhidaoCampus?.reload?.();   // скан открывает туман там, где стоят, — и сюжетные места рядом
    return body;
  }

  async function scanHere() {
    try {
      const result = await checkIn(await read(""));
      window.showToast?.(`Метка «${result.name_ru || result.point}» — вы на месте`);
      window.ZhidaoGameShell?.haptic?.("win");
    } catch (error) {
      if (!error.cancelled) window.showToast?.(error.message);
    }
  }

  let pendingHash = /(?:^|[#&])m=/.test(location.hash) ? location.hash.slice(1) : "";
  function takeHash() {
    if (!pendingHash) return;
    const text = pendingHash;
    pendingHash = "";
    history.replaceState(null, "", location.pathname + location.search);
    checkIn(text)
      .then((result) => window.showToast?.(`Метка «${result.name_ru || result.point}» — вы на месте`))
      .catch((error) => window.showToast?.(error.message));
  }
  window.addEventListener("zhidao:auth", (event) => {
    if (event.detail && event.detail.mode === "authenticated") takeHash();
  });
  // Вход мог завершиться раньше, чем загрузился этот файл.
  if (window.ZhidaoSession && window.ZhidaoSession.mode === "authenticated") takeHash();

  document.getElementById("campusBeaconScan")?.addEventListener("click", scanHere);

  window.ZhidaoBeacon = Object.freeze({ read, withScan, position, checkIn, scanHere });
})();
