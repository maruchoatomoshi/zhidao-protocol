"use strict";

/* Правила кейсов.

   Читаются из assets/cases/cases.json. Веса взяты из пекинского сервера
   (обработчик open_case), а проценты считаются здесь из этих весов — не
   записаны руками. Иначе таблица однажды разойдётся с правилами, и никто
   не заметит: цифры выглядят правдоподобно любыми.

   Показывается и шанс внутри кейса, и общий шанс за одно сканирование.
   Второе — то, что человека на самом деле интересует: «Терракота 50%»
   внутри легендарного кейса и «Терракота 0,1%» за попытку — это про разное,
   и путать их нечестно. */

(function () {
  const SOURCE = "/api/v4/cases/rules";

  let built = false;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  /* Проценты округляются по-разному в зависимости от величины: 0,2% нельзя
     показать как 0%, а 33,92% незачем показывать с сотыми. */
  function percent(value) {
    return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)}%`;
  }

  function buildTier(tier, tierShare) {
    const block = el("article", `case-tier is-${tier.code}`);

    const head = el("div", "case-tier-head");
    const title = el("div", "case-tier-title");
    title.append(el("strong", null, tier.name_ru));
    title.append(el("span", "case-tier-zh", tier.name_zh || ""));
    head.append(title);
    const share = el("span", "case-tier-share");
    share.append(el("b", null, percent(tierShare * 100)));
    share.append(el("small", null, "шанс кейса"));
    head.append(share);
    block.append(head);

    if (tier.note_ru) block.append(el("p", "case-tier-note", tier.note_ru));

    const total = tier.prizes.reduce((sum, prize) => sum + prize.weight, 0);
    const list = el("ul", "case-drops");
    tier.prizes.forEach((prize) => {
      const inTier = prize.weight / total;
      const item = el("li", "case-drop");

      const name = el("div", "case-drop-name");
      name.append(el("span", null, prize.name_ru));
      if (prize.note_ru) name.append(el("small", null, prize.note_ru));
      item.append(name);

      // Полоса — доля внутри кейса. Она же несёт число, чтобы значение
      // читалось и без цвета.
      const bar = el("div", "case-drop-bar");
      const fill = el("i");
      fill.style.width = `${(inTier * 100).toFixed(2)}%`;
      bar.append(fill);
      item.append(bar);

      const numbers = el("div", "case-drop-numbers");
      numbers.append(el("b", null, percent(inTier * 100)));
      numbers.append(el("small", null, `${percent(inTier * tierShare * 100)} за попытку`));
      item.append(numbers);

      list.append(item);
    });
    block.append(list);
    return block;
  }

  async function build() {
    if (built) return;
    const host = document.querySelector("#caseRules");
    if (!host) return;
    built = true;

    let data;
    try {
      const response = await fetch(SOURCE);
      if (!response.ok) throw new Error(String(response.status));
      data = await response.json();
    } catch (err) {
      built = false;
      host.innerHTML = "";
      host.append(el("p", "case-loading", "Правила не загрузились. Проверьте связь и откройте снова."));
      return;
    }

    host.innerHTML = "";

    const action = data.action || {};
    if (Array.isArray(action.how_to_get_ru) && action.how_to_get_ru.length) {
      const where = el("article", "glass-card case-attempts");
      where.append(el("h2", "case-block-title", "Откуда берутся попытки"));
      const list = el("ul", "case-attempt-list");
      action.how_to_get_ru.forEach((line) => list.append(el("li", null, line)));
      where.append(list);
      if (action.shop_note_ru) {
        where.append(el("p", "case-footnote", action.shop_note_ru));
      }
      host.append(where);
    }

    const totalWeight = (data.tiers || []).reduce((sum, tier) => sum + tier.weight, 0);
    host.append(el("h2", "case-block-title", "Что выпадает"));
    (data.tiers || []).forEach((tier) => {
      host.append(buildTier(tier, tier.weight / totalWeight));
    });

    if (Array.isArray(data.modifiers) && data.modifiers.length) {
      const mods = el("article", "glass-card case-modifiers");
      mods.append(el("h2", "case-block-title", "Что меняет исход"));
      data.modifiers.forEach((modifier) => {
        const row = el("div", "case-modifier");
        row.append(el("strong", null, modifier.name_ru));
        row.append(el("span", null, modifier.effect_ru));
        mods.append(row);
      });
      host.append(mods);
    }

    // То, чего в кейсах нет, важно назвать: иначе его будут искать.
    if (Array.isArray(data.not_in_pool) && data.not_in_pool.length) {
      const missing = el("article", "glass-card case-missing");
      missing.append(el("h2", "case-block-title", "Чего в кейсах нет"));
      data.not_in_pool.forEach((entry) => {
        const row = el("div", "case-modifier");
        row.append(el("strong", null, entry.name_ru));
        row.append(el("span", null, entry.why_ru));
        missing.append(row);
      });
      host.append(missing);
    }

    if (data.source_note) host.append(el("p", "case-footnote", data.source_note));
  }

  window.initCaseRules = build;
}());
