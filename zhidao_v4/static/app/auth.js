"use strict";

/* Вход в личный контур участника.

   Три пути, и приложение само выбирает нужный:

   1. Сессия уже есть  -> сразу внутрь, ничего не спрашиваем.
   2. Открыто из MAX   -> молча логинимся по подписанным данным запуска.
      Если этот MAX-аккаунт ещё ни к кому не привязан, сервер отвечает 409 —
      это не отказ, а «покажи код сопряжения», и мы показываем форму кода.
   3. Открыто в обычном браузере -> логин и пароль (провайдер `local`,
      он остаётся источником истины по V4_AUTH.md).

   Предпросмотр публикует только mode=preview: личные модули очищают данные
   и не обращаются к защищённым API. Сервер независимо проверяет сессию. */

(function () {
  const API = {
    me: "/api/v4/auth/me",
    local: "/api/v4/auth/login",
    max: "/api/v4/auth/max",
  };

  const gate = document.querySelector("#authGate");
  if (!gate) return;

  const steps = Array.from(gate.querySelectorAll("[data-step]"));
  const errorBox = gate.querySelector("[data-auth-error]");
  const previewBtn = gate.querySelector("[data-auth-preview]");
  const shell = document.querySelector(".app-shell");

  /* Экран лежит поверх приложения, но «поверх» — это только про пиксели:
     нижняя навигация и кнопки под ним остаются в порядке обхода Tab и
     доступны скринридеру. Пока вход не пройден, приложение выключено
     целиком. */
  function setShellInert(inert) {
    if (!shell) return;
    shell.inert = inert;
    if (inert) shell.setAttribute("aria-hidden", "true");
    else shell.removeAttribute("aria-hidden");
  }
  setShellInert(true);

  let stepShown = false;

  function showStep(name) {
    steps.forEach((el) => { el.hidden = el.dataset.step !== name; });
    gate.dataset.state = name;
    // При смене шага фокус переносим на его первое поле — иначе он остаётся
    // на исчезнувшем элементе и с клавиатуры печатать некуда. На самом первом
    // показе не трогаем: на телефоне это открыло бы клавиатуру поверх экрана
    // раньше, чем человек успел его прочитать.
    const field = gate.querySelector(`[data-step="${name}"] input`);
    if (field && stepShown) field.focus();
    stepShown = true;
  }

  function showError(text) {
    if (!errorBox) return;
    errorBox.textContent = text;
    errorBox.hidden = !text;
  }

  function openApp(payload) {
    const account = payload && payload.account;
    gate.hidden = true;
    setShellInert(false);
    document.body.classList.add("is-signed-in");
    if (!account) return;
    // Имя берём то, что выдал оператор при заведении аккаунта, а не то, что
    // человек написал у себя в профиле MAX: в ростере значится первое.
    document.querySelectorAll("[data-account-name]").forEach((el) => {
      el.textContent = account.display_name;
    });
    window.ZhidaoSession = { mode: "authenticated", account, roles: payload.roles || [] };
    window.dispatchEvent(new CustomEvent("zhidao:auth", { detail: window.ZhidaoSession }));
  }

  async function call(url, body) {
    const options = {
      method: body ? "POST" : "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    };
    if (body) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      payload = null;   // 204 и пустые ответы — это норма, не ошибка
    }
    return { status: response.status, payload };
  }

  /* MAX отдаёт подписанную строку запуска. Отправляем её на сервер ровно как
     есть: подпись покрывает всю строку целиком, любая пересборка её ломает. */
  function maxLaunchParams() {
    const bridge = window.WebApp;
    if (!bridge) return null;
    const raw = bridge.initData;
    return typeof raw === "string" && raw.length ? raw : null;
  }

  async function signInWithMax(linkCode) {
    const launchParams = maxLaunchParams();
    if (!launchParams) return false;

    showStep("max");
    showError("");
    const body = { launch_params: launchParams };
    if (linkCode) body.link_code = linkCode;

    const { status, payload } = await call(API.max, body);

    if (status === 200) {
      openApp(payload);
      return true;
    }
    if (status === 409) {
      // Личность подтверждена, аккаунт не сопоставлен — просим код.
      showStep("pair");
      const detail = payload && payload.detail;
      if (detail && detail.reason === "account_already_linked") {
        // Отдельный случай: код верный, но аккаунту уже принадлежит другой
        // MAX. Раньше это падало в 500 и выглядело как «MAX не отвечает».
        showError(detail.message);
      } else if (linkCode) {
        showError("Код не подошёл: он неверный, уже использован или истёк.");
      }
      return true;
    }
    if (status === 503) {
      showStep("pair");
      showError("Вход через MAX на сервере пока не настроен. Сообщите вожатому.");
      return true;
    }
    showStep("pair");
    showError("Не удалось проверить данные MAX. Попробуйте открыть приложение заново.");
    return true;
  }

  async function boot() {
    showStep("checking");

    const session = await call(API.me);
    if (session.status === 200) {
      openApp(session.payload);
      return;
    }

    // Внутри MAX логинимся сами и не показываем форму логина/пароля вовсе:
    // у детей нет пароля, у них есть MAX и код от вожатого.
    if (maxLaunchParams()) {
      await signInWithMax(null);
      return;
    }

    showStep("local");
    if (previewBtn) previewBtn.hidden = false;
  }

  const pairForm = gate.querySelector('[data-step="pair"]');
  if (pairForm) {
    pairForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const field = pairForm.querySelector("[data-field='code']");
      // Код показывают и диктуют группами по четыре — «1543 6364». Оставляем
      // только цифры: человек не должен угадывать, с пробелом его набирать
      // или без.
      const code = ((field && field.value) || "").replace(/\D/g, "");
      if (code.length !== 8) {
        showError("Код состоит из восьми цифр.");
        return;
      }
      try { await signInWithMax(code); }
      catch (_) { showStep("pair"); showError("Нет связи. Повторите вход."); }
    });
  }

  const localForm = gate.querySelector('[data-step="local"]');
  if (localForm) {
    localForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      showError("");
      const username = (localForm.querySelector("[data-field='username']").value || "").trim();
      const password = localForm.querySelector("[data-field='password']").value || "";
      if (!username || !password) return;

      let result;
      try { result = await call(API.local, { username, password }); }
      catch (_) { showError("Нет связи. Повторите вход."); return; }
      const { status, payload } = result;
      if (status === 200) {
        openApp(payload);
        return;
      }
      if (status === 429) {
        showError("Слишком много попыток входа. Подождите минуту.");
        return;
      }
      showError("Неверный логин или пароль.");
    });
  }

  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      gate.hidden = true;
      setShellInert(false);
      document.body.classList.remove("is-signed-in");
      window.ZhidaoSession = { mode: "preview" };
      window.dispatchEvent(new CustomEvent("zhidao:auth", { detail: window.ZhidaoSession }));
    });
  }

  window.addEventListener("zhidao:session-expired", () => {
    window.ZhidaoSession = { mode: "preview" };
    window.dispatchEvent(new CustomEvent("zhidao:auth", { detail: window.ZhidaoSession }));
    document.body.classList.remove("is-signed-in");
    gate.hidden = false;
    setShellInert(true);
    showStep(maxLaunchParams() ? "pair" : "local");
    showError("Сессия завершилась. Войдите снова; результат сохранён на сервере.");
  });

  boot().catch(() => {
    // Сеть недоступна или сервер молчит. Показываем форму, а не пустой экран:
    // человек хотя бы поймёт, где он и что делать.
    showStep("local");
    showError("Сервер не отвечает. Проверьте связь и обновите страницу.");
    if (previewBtn) previewBtn.hidden = false;
  });
}());
