"use strict";

/* Каталог имплантов.

   Строится из assets/implants/implants.json при первом открытии экрана, а
   не на старте: девять картинок и разметка нужны только тому, кто до
   каталога дошёл.

   Важное про честность: это справочник, а не инвентарь. Эффекты записаны
   так, как они работали в пекинском сезоне, но экономики (★ и REP) в V4
   ещё нет и ни один эффект не включён. Карточка обязана это показывать —
   иначе человек прочитает «+20★ за перекличку» как обещание. */

(function () {
  const SOURCE = "./assets/implants/implants.json?v=e5d188d0aa";
  const ART_BASE = "./assets/implants/";

  let built = false;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function buildCard(implant, rarities) {
    const rarity = rarities[implant.rarity] || {};
    const card = el("article", `implant-card is-${implant.rarity}`);

    /* Шильдик наверху: класс редкости слева, глиф справа. Из этого же
       словаря берётся название кейса, из которого имплант выпадает. */
    const head = el("div", "implant-head");
    const badge = el("span", "implant-rarity");
    badge.append(el("i", null, rarity.label_ru || implant.rarity));
    badge.append(el("small", null, rarity.label_zh || ""));
    head.append(badge);
    head.append(el("span", "implant-glyph", implant.glyph || ""));
    card.append(head);

    // Витрина: предмет на подсвеченной плите. Само изображение с прозрачным
    // фоном, поэтому свечение живёт в подложке, а не в картинке.
    const stage = el("div", "implant-stage");
    const art = document.createElement("img");
    art.className = "implant-art";
    art.src = ART_BASE + implant.art;
    art.alt = `${implant.name_ru} ${implant.name_zh}`;
    // Каталог листают сверху вниз, и грузить все девять сразу незачем.
    art.loading = "lazy";
    art.decoding = "async";
    stage.append(art);
    card.append(stage);

    const body = el("div", "implant-body");
    const title = el("h2", "implant-name");
    title.append(el("span", "implant-name-ru", implant.name_ru));
    const zh = el("span", "implant-name-zh");
    zh.append(el("b", null, implant.name_zh));
    if (implant.pinyin) zh.append(el("i", null, implant.pinyin));
    title.append(zh);
    body.append(title);

    if (implant.protocol_ru) {
      body.append(el("p", "implant-protocol", implant.protocol_ru));
    }

    const effect = el("p", "implant-effect");
    effect.append(el("span", "implant-effect-label", "ЭФФЕКТ"));
    effect.append(el("span", "implant-effect-text", implant.effect_ru));
    body.append(effect);

    body.append(el("p", "implant-lore", implant.lore_ru));

    if (Array.isArray(implant.actions) && implant.actions.length) {
      const actions = el("ul", "implant-actions");
      implant.actions.forEach((action) => {
        const item = el("li");
        item.append(el("strong", null, action.label_ru));
        item.append(el("span", null, action.hint_ru));
        actions.append(item);
      });
      body.append(actions);
    }

    const footer = el("div", "implant-foot");
    footer.append(el("span", "implant-source", rarity.case_ru || ""));
    // Пробел в арте показывается, а не замазывается: так видно, что ещё
    // предстоит нарисовать.
    if (implant.art_season === "beijing") {
      footer.append(el("span", "implant-art-note", "арт пекинский"));
    }
    body.append(footer);

    card.append(body);
    return card;
  }

  async function build() {
    if (built) return;
    const host = document.querySelector("#implantList");
    if (!host) return;
    built = true;

    let data;
    try {
      const response = await fetch(SOURCE);
      if (!response.ok) throw new Error(String(response.status));
      data = await response.json();
    } catch (err) {
      built = false;   // дать следующему заходу попробовать снова
      host.innerHTML = "";
      host.append(el("p", "implant-loading", "Каталог не загрузился. Проверьте связь и откройте снова."));
      return;
    }

    host.innerHTML = "";
    const rarities = data.rarities || {};
    const order = ["legendary", "rare"];
    order.forEach((rarityKey) => {
      const group = (data.implants || []).filter((i) => i.rarity === rarityKey);
      if (!group.length) return;
      const heading = el("h2", "implant-group");
      heading.append(el("span", null, (rarities[rarityKey] || {}).case_ru || rarityKey));
      heading.append(el("small", null, `${group.length}`));
      host.append(heading);
      group.forEach((implant) => host.append(buildCard(implant, rarities)));
    });

    if (data.art_note) {
      host.append(el("p", "implant-footnote", data.art_note));
    }
  }

  window.initImplantCatalogue = build;
}());
