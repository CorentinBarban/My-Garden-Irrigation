/**
 * My Garden Irrigation — Carte Lovelace personnalisée
 *
 * Carte d'aperçu et de pilotage du potager pour l'intégration
 * `my_garden_irrigation`. À charger comme ressource Lovelace (module JS).
 *
 * Centrée sur la CENTRALE (le potager) : besoin du jour, arrosage auto,
 * prochain arrosage, météo et réglages. Les cultures sont en second plan.
 *
 * Zéro configuration : la carte découvre la centrale (device modèle
 * « Garden Irrigation Hub ») et les cultures rattachées. Les rôles des
 * entités sont déduits de leurs attributs (device_class, unité, icône,
 * options) — aucune dépendance à unique_id.
 *
 *   type: custom:my-garden-irrigation-card
 *   title: Mon potager       # optionnel
 *   entry: Potager           # optionnel (titre/id si plusieurs instances)
 *   show_config: true        # optionnel — section Réglages (défaut: true)
 *   show_crops: true         # optionnel — section Cultures (défaut: true)
 *   show_actions: true       # optionnel — boutons (défaut: true)
 */

const DOMAIN = "my_garden_irrigation";
const HUB_MODEL = "Garden Irrigation Hub";

// Libellés FR pour les options de select (sinon valeur brute affichée).
const OPTION_LABELS = {
  daily: "Quotidien",
  interval: "Intervalle fixe",
  continuous: "Continu",
  fractioned: "Fractionné",
  ini: "Initial",
  mid: "Mi-saison",
  end: "Fin de saison",
};

// Icône par défaut selon le domaine d'un contrôle de réglage.
const CTRL_ICON = {
  number: "mdi:tune-variant",
  select: "mdi:format-list-bulleted",
  time: "mdi:clock-time-four-outline",
};

class MyGardenIrrigationCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      show_config: true,
      show_crops: true,
      show_actions: true,
      ...config,
    };
    this._signature = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig() {
    return { type: "custom:my-garden-irrigation-card" };
  }

  /* ================================================================== */
  /* Découverte                                                         */
  /* ================================================================== */

  _discover() {
    const hass = this._hass;
    if (!hass || !hass.entities || !hass.devices) return null;

    const ours = Object.values(hass.entities).filter(
      (e) => e.platform === DOMAIN
    );
    if (!ours.length) return null;

    // Restreindre à une instance (entrée de config).
    const byEntry = {};
    for (const e of ours)
      (byEntry[e.config_entry_id || "_"] ||= []).push(e);

    let entryId = Object.keys(byEntry)[0];
    if (this._config.entry) {
      const wanted = String(this._config.entry).toLowerCase();
      for (const id of Object.keys(byEntry)) {
        const ce = hass.entries ? hass.entries[id] : null;
        const title = ce && ce.title ? ce.title.toLowerCase() : "";
        if (id === this._config.entry || title === wanted) {
          entryId = id;
          break;
        }
      }
    }
    const list = byEntry[entryId] || [];

    // Regrouper par device.
    const byDevice = {};
    for (const e of list) {
      if (!e.device_id) continue;
      (byDevice[e.device_id] ||= []).push(e.entity_id);
    }

    // Identifier la centrale : modèle dédié, sinon device portant un switch.
    let hubDeviceId = null;
    for (const did of Object.keys(byDevice)) {
      const dev = hass.devices[did];
      if (dev && dev.model === HUB_MODEL) {
        hubDeviceId = did;
        break;
      }
    }
    if (!hubDeviceId) {
      for (const [did, ids] of Object.entries(byDevice)) {
        if (ids.some((id) => id.startsWith("switch."))) {
          hubDeviceId = did;
          break;
        }
      }
    }

    const hubDev = hubDeviceId ? hass.devices[hubDeviceId] : null;
    const hubName =
      (hubDev && (hubDev.name_by_user || hubDev.name)) ||
      (hass.entries && hass.entries[entryId] && hass.entries[entryId].title) ||
      "Potager";

    const hub = { name: hubName, controls: [] };
    const at = (id) => {
      const s = hass.states[id];
      return s ? s.attributes || {} : {};
    };
    const icon = (id) => (at(id).icon || "").toLowerCase();

    for (const id of byDevice[hubDeviceId] || []) {
      const dom = id.split(".")[0];
      const a = at(id);
      if (dom === "switch") {
        hub.auto = id;
      } else if (dom === "button") {
        if (icon(id).includes("play")) hub.start = id;
        else hub.reset = id;
      } else if (dom === "sensor") {
        if (a.device_class === "timestamp") hub.next = id;
        else if (a.unit_of_measurement === "mm") {
          if (icon(id).includes("rain") || icon(id).includes("weather"))
            hub.precipitation = id;
          else hub.eto = id;
        } else if (a.unit_of_measurement === "L") {
          if (icon(id).includes("plus") || a.state_class === "total")
            hub.totalCumulative = id;
          else hub.totalDaily = id;
        }
      } else if (dom === "number" || dom === "select" || dom === "time") {
        hub.controls.push(id);
      }
    }

    // Cultures = autres devices, avec leur capteur de besoin journalier (L).
    const crops = [];
    for (const [did, ids] of Object.entries(byDevice)) {
      if (did === hubDeviceId) continue;
      const dev = hass.devices[did];
      const daily = ids.find(
        (id) =>
          id.startsWith("sensor.") &&
          at(id).unit_of_measurement === "L" &&
          at(id).state_class === "measurement"
      );
      if (!daily) continue;
      crops.push({
        name: (dev && (dev.name_by_user || dev.name)) || at(daily).crop_type,
        daily,
        // Commutateur de paillage de la culture (atténuation ETc, ADR-029).
        mulch: ids.find((id) => id.startsWith("switch.")) || null,
      });
    }
    crops.sort((a, b) => (a.name || "").localeCompare(b.name || ""));

    return { hub, crops };
  }

  /* ================================================================== */
  /* Rendu                                                              */
  /* ================================================================== */

  _render() {
    const data = this._discover();
    if (!data) return this._renderEmpty();

    const sig = this._signatureOf(data);
    if (sig === this._signature && this.firstElementChild) return;
    this._signature = sig;

    this._data = data;
    const { hub, crops } = data;

    this.innerHTML = `
      <ha-card>
        <style>${MyGardenIrrigationCard.styles}</style>
        ${this._hero(hub, crops)}
        ${this._weather(hub)}
        ${this._actions(hub)}
        ${this._configSection(hub)}
        ${this._cropsSection(crops)}
      </ha-card>`;

    this._bind(hub);
  }

  _signatureOf(data) {
    const parts = [];
    const add = (id) => id && parts.push(id + "=" + this._st(id, "?"));
    const h = data.hub;
    [
      h.auto, h.next, h.totalDaily, h.totalCumulative, h.eto, h.precipitation,
    ].forEach(add);
    h.controls.forEach(add);
    data.crops.forEach((c) => {
      add(c.daily);
      add(c.mulch);
      const a = this._attr(c.daily);
      parts.push((a.watering_applied_today_liters ?? "") + "/" + (a.net_liters ?? ""));
    });
    return parts.join("|");
  }

  _renderEmpty() {
    this._signature = "__empty__";
    this.innerHTML = `
      <ha-card header="My Garden Irrigation">
        <div style="padding:16px;color:var(--secondary-text-color)">
          Aucune instance détectée. Vérifiez que l'intégration
          <b>My Garden Irrigation</b> est configurée, puis rechargez la page.
        </div>
      </ha-card>`;
  }

  /* ------------------------------ Hero ------------------------------ */

  _hero(hub, crops) {
    // Besoin du jour (total) et progression d'arrosage (appliqué / besoin).
    const needS = hub.totalDaily ? this._hass.states[hub.totalDaily] : null;
    const need = needS ? Number(needS.state) : null;

    let applied = 0;
    let target = 0;
    crops.forEach((c) => {
      const a = this._attr(c.daily);
      if (a.net_liters != null) target += Number(a.net_liters);
      if (a.watering_applied_today_liters != null)
        applied += Number(a.watering_applied_today_liters);
    });
    if (!target && need != null) target = need;
    const frac = target > 0 ? Math.min(1, applied / target) : 0;

    const cumul = hub.totalCumulative
      ? this._num(this._st(hub.totalCumulative), 0)
      : null;

    const autoOn = hub.auto && this._st(hub.auto) === "on";
    const nextTxt =
      hub.next && this._st(hub.next)
        ? this._relTime(this._st(hub.next))
        : "—";

    return `
      <div class="hero">
        <div class="hero-bg"></div>
        ${this._gauge(need, frac)}
        <div class="hero-info">
          <div class="hero-name">${hub.name}</div>
          <button class="auto ${autoOn ? "on" : ""}" data-auto>
            <ha-icon icon="mdi:${autoOn ? "robot" : "robot-off"}"></ha-icon>
            <span>Arrosage auto · ${autoOn ? "activé" : "coupé"}</span>
          </button>
          <div class="hero-next" data-next-row>
            <ha-icon icon="mdi:sprinkler-variant"></ha-icon>
            <span>Prochain arrosage<br><b>${nextTxt}</b></span>
          </div>
          ${
            cumul != null
              ? `<div class="hero-cumul" data-cumul>
                   <ha-icon icon="mdi:water-plus-outline"></ha-icon>
                   <span>Réserve à compenser <b>${cumul} L</b></span>
                 </div>`
              : ""
          }
        </div>
      </div>`;
  }

  _gauge(value, frac) {
    const r = 52;
    const c = 2 * Math.PI * r;
    const off = c * (1 - frac);
    const pct = Math.round(frac * 100);
    const display = value == null ? "—" : this._num(value, 0);
    return `
      <div class="gauge">
        <svg viewBox="0 0 130 130">
          <circle class="g-track" cx="65" cy="65" r="${r}"></circle>
          <circle class="g-val" cx="65" cy="65" r="${r}"
            stroke-dasharray="${c}" stroke-dashoffset="${off}"></circle>
        </svg>
        <div class="g-center">
          <div class="g-num">${display}<span>L</span></div>
          <div class="g-lbl">besoin du jour</div>
          <div class="g-pct">${pct}% arrosé</div>
        </div>
      </div>`;
  }

  /* ---------------------------- Météo ------------------------------- */

  _weather(hub) {
    const chips = [];
    if (hub.precipitation)
      chips.push(
        this._chip("mdi:weather-rainy", "Pluie", hub.precipitation, "mm", 1)
      );
    if (hub.eto)
      chips.push(
        this._chip("mdi:sun-thermometer-outline", "ETo", hub.eto, "mm", 2)
      );
    if (!chips.length) return "";
    return `<div class="chips">${chips.join("")}</div>`;
  }

  _chip(icon, label, entity, unit, precision) {
    return `
      <div class="chip" data-more="${entity}">
        <ha-icon icon="${icon}"></ha-icon>
        <div class="chip-txt">
          <span class="chip-lbl">${label}</span>
          <span class="chip-val">${this._num(this._st(entity), precision)} ${unit}</span>
        </div>
      </div>`;
  }

  /* --------------------------- Actions ------------------------------ */

  _actions(hub) {
    if (!this._config.show_actions || (!hub.start && !hub.reset)) return "";
    let h = "";
    if (hub.start)
      h += `<button class="btn primary" data-act="${hub.start}">
        <ha-icon icon="mdi:play-circle-outline"></ha-icon>Arroser maintenant</button>`;
    if (hub.reset)
      h += `<button class="btn" data-act="${hub.reset}">
        <ha-icon icon="mdi:restart"></ha-icon>Réinitialiser</button>`;
    return `<div class="actions">${h}</div>`;
  }

  /* -------------------------- Réglages ------------------------------ */

  _configSection(hub) {
    if (!this._config.show_config || !hub.controls.length) return "";
    const rows = hub.controls
      .map((id) => this._control(id, hub.name))
      .join("");
    return `
      <details class="section" open>
        <summary><ha-icon icon="mdi:cog-outline"></ha-icon>Réglages</summary>
        <div class="ctrl-list">${rows}</div>
      </details>`;
  }

  _control(id, hubName) {
    const dom = id.split(".")[0];
    const s = this._hass.states[id];
    if (!s) return "";
    const a = s.attributes || {};
    const icon = a.icon || CTRL_ICON[dom] || "mdi:tune";
    let label = a.friendly_name || id;
    if (hubName && label.startsWith(hubName))
      label = label.slice(hubName.length).trim() || label;

    let control = "";
    if (dom === "number") {
      const min = a.min ?? 0;
      const max = a.max ?? 100;
      const step = a.step ?? 1;
      const unit = a.unit_of_measurement || "";
      control = `
        <div class="num-ctrl">
          <input type="range" data-num="${id}"
            min="${min}" max="${max}" step="${step}" value="${s.state}">
          <span class="num-val" data-numval="${id}">${s.state} ${unit}</span>
        </div>`;
    } else if (dom === "select") {
      const opts = (a.options || [])
        .map(
          (o) =>
            `<option value="${o}" ${o === s.state ? "selected" : ""}>${
              OPTION_LABELS[o] || o
            }</option>`
        )
        .join("");
      control = `<select data-select="${id}">${opts}</select>`;
    } else if (dom === "time") {
      const v = (s.state || "00:00:00").slice(0, 5);
      control = `<input type="time" data-time="${id}" value="${v}">`;
    }

    return `
      <div class="ctrl">
        <ha-icon icon="${icon}"></ha-icon>
        <span class="ctrl-lbl">${label}</span>
        <div class="ctrl-input">${control}</div>
      </div>`;
  }

  /* --------------------------- Cultures ----------------------------- */

  _cropsSection(crops) {
    if (!this._config.show_crops || !crops.length) return "";
    const rows = crops.map((c) => this._cropRow(c)).join("");
    return `
      <details class="section">
        <summary><ha-icon icon="mdi:sprout-outline"></ha-icon>Cultures
          <span class="count">${crops.length}</span></summary>
        <div class="crop-list">${rows}</div>
      </details>`;
  }

  _cropRow(c) {
    const a = this._attr(c.daily);
    const need = this._num(this._st(c.daily), 1);
    const net = a.net_liters != null ? Number(a.net_liters) : Number(this._st(c.daily)) || 0;
    const applied = a.watering_applied_today_liters;
    let pct = 0;
    if (net > 0 && applied != null) pct = Math.min(100, (applied / net) * 100);
    const mulchOn = c.mulch && this._st(c.mulch) === "on";
    const mulchBadge = c.mulch
      ? `<button class="mulch ${mulchOn ? "on" : ""}" data-mulch="${c.mulch}"
           title="Paillage ${mulchOn ? "activé" : "désactivé"}">
           <ha-icon icon="mdi:grass"></ha-icon>
         </button>`
      : "";
    return `
      <div class="crop" data-more="${c.daily}">
        <ha-icon icon="mdi:sprout"></ha-icon>
        <div class="crop-main">
          <div class="crop-top">
            <span class="crop-name">${c.name || "Culture"}</span>
            ${mulchBadge}
            <span class="crop-need">${need} L</span>
          </div>
          <div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>
        </div>
        <ha-icon class="chev" icon="mdi:chevron-right"></ha-icon>
      </div>`;
  }

  /* ================================================================== */
  /* Interactions                                                       */
  /* ================================================================== */

  _bind(hub) {
    const autoBtn = this.querySelector("[data-auto]");
    if (autoBtn && hub.auto)
      autoBtn.addEventListener("click", () =>
        this._hass.callService("switch", "toggle", { entity_id: hub.auto })
      );

    const nextRow = this.querySelector("[data-next-row]");
    if (nextRow && hub.next)
      nextRow.addEventListener("click", () => this._moreInfo(hub.next));

    const cumulRow = this.querySelector("[data-cumul]");
    if (cumulRow && hub.totalCumulative)
      cumulRow.addEventListener("click", () =>
        this._moreInfo(hub.totalCumulative)
      );

    this.querySelectorAll("[data-more]").forEach((el) =>
      el.addEventListener("click", () =>
        this._moreInfo(el.getAttribute("data-more"))
      )
    );

    // Bascule du paillage — stoppe la propagation pour ne pas ouvrir le more-info.
    this.querySelectorAll("[data-mulch]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        this._hass.callService("switch", "toggle", {
          entity_id: b.getAttribute("data-mulch"),
        });
      })
    );

    this.querySelectorAll("[data-act]").forEach((b) =>
      b.addEventListener("click", () =>
        this._hass.callService("button", "press", {
          entity_id: b.getAttribute("data-act"),
        })
      )
    );

    // Contrôles de réglage
    this.querySelectorAll("[data-num]").forEach((inp) => {
      const id = inp.getAttribute("data-num");
      const unit = (this._attr(id).unit_of_measurement) || "";
      const label = this.querySelector(`[data-numval="${id}"]`);
      inp.addEventListener("input", () => {
        if (label) label.textContent = `${inp.value} ${unit}`;
      });
      inp.addEventListener("change", () =>
        this._hass.callService("number", "set_value", {
          entity_id: id,
          value: Number(inp.value),
        })
      );
    });

    this.querySelectorAll("[data-select]").forEach((sel) => {
      const id = sel.getAttribute("data-select");
      sel.addEventListener("change", () =>
        this._hass.callService("select", "select_option", {
          entity_id: id,
          option: sel.value,
        })
      );
    });

    this.querySelectorAll("[data-time]").forEach((inp) => {
      const id = inp.getAttribute("data-time");
      inp.addEventListener("change", () =>
        this._hass.callService("time", "set_value", {
          entity_id: id,
          time: inp.value.length === 5 ? inp.value + ":00" : inp.value,
        })
      );
    });
  }

  /* ============================ Utilitaires ========================= */

  _st(id, fb = null) {
    const s = this._hass.states[id];
    return s ? s.state : fb;
  }

  _attr(id) {
    const s = this._hass.states[id];
    return s ? s.attributes || {} : {};
  }

  _num(v, p = 0) {
    if (v == null || v === "unknown" || v === "unavailable" || v === "")
      return "—";
    const n = Number(v);
    return Number.isNaN(n) ? v : n.toFixed(p);
  }

  _relTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const diff = d.getTime() - Date.now();
    const h = Math.round(Math.abs(diff) / 3.6e6);
    const lang = this._hass.language || "fr";
    const day = d.toLocaleDateString(lang, { weekday: "short" });
    const time = d.toLocaleTimeString(lang, {
      hour: "2-digit",
      minute: "2-digit",
    });
    if (diff < 0) return `passé · ${day} ${time}`;
    if (h < 24) return `dans ${h} h · ${time}`;
    return `${day} ${time}`;
  }

  _moreInfo(entityId) {
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }
}

MyGardenIrrigationCard.styles = `
  ha-card { overflow: hidden; }

  /* ----- Hero ----- */
  .hero { position: relative; display:flex; gap:16px; align-items:center;
    padding:18px 16px; }
  .hero-bg { position:absolute; inset:0; z-index:0;
    background: linear-gradient(135deg,
      color-mix(in srgb, var(--primary-color) 22%, transparent),
      transparent 70%); }
  .gauge, .hero-info { position:relative; z-index:1; }

  .gauge { position:relative; width:130px; height:130px; flex:none; }
  .gauge svg { width:130px; height:130px; transform: rotate(-90deg); }
  .g-track { fill:none; stroke: var(--divider-color); stroke-width:10; }
  .g-val { fill:none; stroke: var(--primary-color); stroke-width:10;
    stroke-linecap:round; transition: stroke-dashoffset .6s ease; }
  .g-center { position:absolute; inset:0; display:flex; flex-direction:column;
    align-items:center; justify-content:center; text-align:center; }
  .g-num { font-size:1.9rem; font-weight:700; line-height:1; }
  .g-num span { font-size:.8rem; font-weight:500;
    color:var(--secondary-text-color); margin-left:2px; }
  .g-lbl { font-size:.66rem; text-transform:uppercase; letter-spacing:.5px;
    color:var(--secondary-text-color); margin-top:3px; }
  .g-pct { font-size:.7rem; color:var(--primary-color); margin-top:4px;
    font-weight:600; }

  .hero-info { flex:1; min-width:0; display:flex; flex-direction:column; gap:8px; }
  .hero-name { font-size:1.3rem; font-weight:700; line-height:1.15;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  .auto { display:inline-flex; align-items:center; gap:8px; align-self:flex-start;
    border:none; cursor:pointer; padding:7px 12px; border-radius:20px;
    font-size:.85rem; font-weight:600;
    background: var(--secondary-background-color);
    color: var(--secondary-text-color); }
  .auto ha-icon { --mdc-icon-size:20px; }
  .auto.on { background: var(--primary-color); color: var(--text-primary-color,#fff); }

  .hero-next, .hero-cumul { display:flex; align-items:center; gap:8px;
    cursor:pointer; font-size:.85rem; color: var(--primary-text-color); }
  .hero-next ha-icon, .hero-cumul ha-icon { --mdc-icon-size:20px; flex:none;
    color: var(--primary-color); }
  .hero-next b, .hero-cumul b { font-weight:600; }

  /* ----- Chips météo ----- */
  .chips { display:flex; gap:8px; padding:0 16px 4px; margin-top:12px; }
  .chip { flex:1; display:flex; align-items:center; gap:10px; cursor:pointer;
    background: var(--secondary-background-color); border-radius:14px;
    padding:10px 12px; }
  .chip ha-icon { --mdc-icon-size:24px; color: var(--primary-color); flex:none; }
  .chip-txt { display:flex; flex-direction:column; line-height:1.2; min-width:0; }
  .chip-lbl { font-size:.7rem; color: var(--secondary-text-color); }
  .chip-val { font-size:1.05rem; font-weight:600; }

  /* ----- Actions ----- */
  .actions { display:flex; gap:8px; padding:12px 16px 4px; }
  .btn { flex:1; display:inline-flex; align-items:center; justify-content:center;
    gap:6px; padding:11px 12px; border:none; border-radius:12px; cursor:pointer;
    font-size:.9rem; font-weight:600;
    background: var(--secondary-background-color); color: var(--primary-text-color); }
  .btn ha-icon { --mdc-icon-size:20px; }
  .btn.primary { background: var(--primary-color); color: var(--text-primary-color,#fff); }
  .btn:active { transform: scale(.98); }

  /* ----- Sections repliables ----- */
  .section { border-top: 1px solid var(--divider-color); margin-top:12px; }
  .section summary { display:flex; align-items:center; gap:10px; cursor:pointer;
    padding:14px 16px; font-weight:600; list-style:none; user-select:none; }
  .section summary::-webkit-details-marker { display:none; }
  .section summary ha-icon { --mdc-icon-size:20px; color: var(--primary-color); }
  .section summary .count { margin-left:auto; font-weight:600; font-size:.8rem;
    background: var(--secondary-background-color); border-radius:10px;
    padding:1px 9px; color: var(--secondary-text-color); }

  /* ----- Contrôles de réglage ----- */
  .ctrl-list { padding:0 16px 14px; display:flex; flex-direction:column; gap:12px; }
  .ctrl { display:flex; align-items:center; gap:12px; }
  .ctrl > ha-icon { --mdc-icon-size:22px; color: var(--secondary-text-color); flex:none; }
  .ctrl-lbl { flex:1; font-size:.9rem; min-width:0; }
  .ctrl-input { flex:none; display:flex; align-items:center; }
  .num-ctrl { display:flex; align-items:center; gap:10px; }
  .num-ctrl input[type=range] { width:120px; accent-color: var(--primary-color); }
  .num-val { font-size:.85rem; font-weight:600; min-width:56px; text-align:right;
    font-variant-numeric: tabular-nums; }
  .ctrl-input select, .ctrl-input input[type=time] {
    font: inherit; padding:6px 8px; border-radius:8px;
    border:1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color); }

  /* ----- Cultures ----- */
  .crop-list { padding:0 16px 14px; display:flex; flex-direction:column; gap:2px; }
  .crop { display:flex; align-items:center; gap:12px; padding:8px 4px;
    border-radius:10px; cursor:pointer; }
  .crop:hover { background: var(--secondary-background-color); }
  .crop > ha-icon { --mdc-icon-size:24px; color: #43a047; flex:none; }
  .crop-main { flex:1; min-width:0; }
  .crop-top { display:flex; justify-content:space-between; gap:8px; }
  .crop-name { font-size:.9rem; font-weight:500; overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; }
  .mulch { flex:none; display:inline-flex; align-items:center; justify-content:center;
    margin-left:auto; border:none; cursor:pointer; padding:2px; border-radius:50%;
    background:transparent; color: var(--disabled-text-color); }
  .mulch ha-icon { --mdc-icon-size:18px; }
  .mulch.on { color: #43a047; }
  .crop-need { font-variant-numeric: tabular-nums; flex:none; font-size:.9rem;
    margin-left:8px; }
  .bar { height:5px; border-radius:5px; margin-top:6px;
    background: var(--divider-color); overflow:hidden; }
  .bar-fill { height:100%; background: var(--primary-color); border-radius:5px;
    transition: width .4s ease; }
  .chev { --mdc-icon-size:20px; color: var(--secondary-text-color); flex:none; }
`;

customElements.define("my-garden-irrigation-card", MyGardenIrrigationCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "my-garden-irrigation-card",
  name: "My Garden Irrigation",
  description:
    "Pilotage du potager : besoin du jour, arrosage auto, météo, réglages et cultures.",
  preview: true,
  documentationURL: "https://github.com/Corentin/My-Garden-Irrigation",
});

console.info(
  "%c MY-GARDEN-IRRIGATION-CARD %c v3 ",
  "background:#43a047;color:#fff;border-radius:4px 0 0 4px;padding:2px 4px",
  "background:#1b5e20;color:#fff;border-radius:0 4px 4px 0;padding:2px 4px"
);
