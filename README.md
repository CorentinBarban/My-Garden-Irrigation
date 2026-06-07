# 🌿 My Garden Irrigation — Home Assistant Integration

> 🌐 **Language:** English · [Français](README.fr.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![quality_scale](https://img.shields.io/badge/Quality%20Scale-Silver-lightgrey.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
![GitHub Tag](https://img.shields.io/github/v/tag/corentinBarban/My-Garden-Irrigation)

**My Garden Irrigation** (`my_garden_irrigation`) is a custom Home Assistant integration that computes the water needs of vegetable garden crops and drives their watering. It relies on the evapotranspiration method from the **FAO Irrigation and Drainage Paper 56**.

The integration fetches the daily reference evapotranspiration (ETo) and rainfall through the **Open-Meteo** API, and downloads crop coefficients (Kc) from a remote repository. Its operating mode is based on the _cloud polling_ principle.

---

## 📐 Calculation principle

### Daily gross need

The estimate relies on the standard agronomy formula:

```
ETc = Kc × ETo
```

- **ETo**: daily reference evapotranspiration (mm/day), provided by Open-Meteo.
- **Kc**: crop coefficient specific to each plant, indexed by its growth stage.
- **ETc**: gross water need, converted to liters according to the occupied area.

A plot's area is automatically derived from the **number of plants** and the **planting density** (plants per m²).

### 🍂 Mulch (dynamic, phased attenuation)

When a plot is mulched, the soil's direct evaporation drops — but **not by a fixed amount**: the effect depends on the crop's phenological stage (FAO-56). The integration therefore applies a **dynamic, stage-phased attenuation factor** to the ETc, *before* deducting effective rainfall (mulch reduces the evaporative demand, not the rainfall received):

| Stage | Factor | Effect | Why |
|-------|--------|--------|-----|
| `ini` — Initial | **0.55** | −45 % | Bare soil: direct evaporation dominates, mulch blocks most of it. |
| `mid` — Mid-season | **0.90** | −10 % | Full canopy: leaf transpiration dominates, mulch effect is marginal. |
| `end` — End of season | **0.85** | −15 % | Onset of senescence: the canopy opens, soil evaporation rises slightly. |

- Mulch is a **per-plot flag**: enable it once via the **Mulch** switch, and the factor follows the stage changes automatically across the season — no further intervention.
- An unknown stage falls back to a **neutral factor of 1.0** (no attenuation): safe behavior, never amplification.
- A non-mulched plot keeps exactly the standard `ETc = Kc × ETo` calculation.

This avoids both **over-watering early in the cycle** (where mulch blocks far more than a flat factor) and **under-watering in mid-season** (the critical fruiting period).

### Signed water balance and rainfall reserve

The integration keeps a **signed water accounting** of the soil, which records both the deficit and the surplus:

```
Daily balance = ETc − effective rainfall
Cumulative need += daily balance        (at midnight)
Cumulative need −= volume actually watered
```

- The **cumulative need** can be **positive** (debt: the soil is thirsty) or **negative** (reserve: rainfall surplus carried over to the following days).
- A **negative cumulative need** is the **rain reserve**: when rainfall exceeds the day's ETc, the surplus is *not discarded* — it is stored as a negative balance. As long as this reserve lasts, the integration automatically **spaces out or skips** the following waterings, and only resumes once the reserve is depleted and the balance climbs back above zero.
- Rainfall is retained only up to its **actual efficiency** (0.8 factor on gross rainfall).
- The volume actually delivered is charged to the balance **only once**, ensuring reliable accounting.

> The need displayed to the user stays capped at 0 (`max(0, balance)`) so a reserve never shows as a "negative volume", while the signed balance internally keeps the negative reserve and drives the decision whether to water or not.

---

## 📊 Generated entities

### 🔍 Sensors (`sensor`)

**Per crop plot:**

- **Irrigation**: required volume of the day (liters), with a list of detailed attributes:
  - `crop_type`, `stage`: crop type and current stage.
  - `nb_plants`, `density_plants_per_m2`, `surface_m2`: plot geometry.
  - `kc`, `eto_mm`: agronomic values of the day.
  - `mulch_active`: whether the stage-phased mulch attenuation is applied to this plot.
  - `precipitation_mm`, `effective_rainfall_mm`: gross rainfall and retained effective rainfall.
  - `etc_liters`, `net_liters`: gross need and net balance of the day.
  - `watering_applied_today_liters`: volume already delivered today.
  - `cumulative_need_liters`: cumulative water need (signed).
  - `recommended_duration_minutes`: recommended watering duration based on the configured flow rate.
  - `liters_per_plant`, `weekly_projection_l`: tracking indicators.
  - **Fractioned mode** (if enabled): `is_fractioned`, `cycles_count`, `duration_per_cycle_minutes`, `soak_duration_minutes`.
- **Kc** and **ETo**: agronomic values exposed individually.
- **Cumulative need**: signed balance specific to the plot.

**At the garden level (central unit):**

- **Daily need**: sum of the day's needs across all plots.
- **Cumulative need**: global signed water balance.
- **Daily precipitation**: rainfall of the day (mm).
- **Next watering**: date/time of the next scheduled watering.

### ⚙️ Numeric controls (`number`)

`Number of plants` · `Density (plants/m²)` · `Installation flow rate` · `Interval between waterings` · `Number of cycles` · `Rest between cycles`.

### 🎛️ Selectors (`select`)

`Growth stage` · `Watering frequency` · `Watering mode`.

### 🔘 Buttons (`button`)

- **Water now**: immediately triggers a watering.
- **Reset irrigation**: resets the cumulative water balance to zero.

### 🔀 Switches (`switch`) and 🕒 Time (`time`)

- **Automatic watering**: enables/disables the automatic emission of the watering event.
- **Mulch** (per plot): enables the stage-phased ETc attenuation for a mulched plot.
- **Watering time**: daily automatic trigger time.

All these entities can be adjusted dynamically from your Lovelace dashboards.

---

## 🥕 Supported crops

The integration natively includes default planting densities (plants/m²) for **27 crops** from the FAO repository:

Garlic · Artichoke · Asparagus · Eggplant · Basil · Beetroot · Broccoli · Carrot · Celery · Cabbage · Cauliflower · Cucumber · Zucchini · Spinach · Strawberry · Green bean · Lettuce · Melon · Onion · Parsley · Peas · Leek · Bell pepper · Potato · Pumpkin · Radish · Tomato.

### 🔄 Growth stages

For each plot, you choose the development stage:

- `ini` — **Initial** (sowing / regrowth)
- `mid` — **Mid-season** (full development)
- `end` — **End of season** (maturation)

---

## 🛠️ Configuration

Setup is performed entirely through the Home Assistant graphical interface (**Config Flow**). The options menu gathers:

- **Add / Remove a crop**: plot name, type, stage, number of plants and density (pre-filled according to the FAO repository).
- **Global valve**: link to a valve or switch entity (`global_valve_entity_id`) and entry of the installation's total flow rate (`global_flow_rate`, in L/h) to estimate the watering duration. Leave empty to disable automatic tracking.
- **Watering frequency and mode**:
  - **Frequency**: `daily` or `interval` (fixed interval of X days).
  - **Mode**:
    - **Continuous** (`continuous`).
    - **Fractioned** (`fractioned`): sequences the watering into several cycles (3 by default) interspersed with pauses (15 min by default) to avoid runoff and promote infiltration.
- **Automatic watering**: daily trigger time of the watering event.

---

## 🤖 Automatic watering and valve control

The integration does not drive your hardware directly: it **emits an event** that you link to your physical valve through a blueprint. This separation guarantees shut-off safety and remains agnostic of your installation.

1. Configure the **global valve** and enable the **"Automatic watering"** switch.
2. At the configured time (or according to the interval), the central unit emits the `my_garden_irrigation_irrigation_requested` event **only if a watering is actually needed** (the schedule re-anchors on the effective watering, not on the mere elapse of the interval).
3. Import the **provided blueprint** ([`watering_blueprint.yaml`](blueprints/automation/my_garden_irrigation/watering_blueprint.yaml)) to link this event to your valve. The blueprint relies on Home Assistant's native engine: **if HA restarts during a watering, the valve is automatically shut off on resume**.

---

## 🚀 Exposed service

- **`my_garden_irrigation.recalculate`**: forces the immediate recalculation of all water needs, without waiting for the automatic scheduling. Useful after a manual ETo update or to test an automation.

---

## 📥 Installation

### 🛒 Via HACS (recommended)

1. Open **HACS** in your Home Assistant instance.
2. Menu (three dots, top right) → **Custom repositories**.
3. Enter the URL of this repository, category **Integration**, then **Add**.
4. Search for `My Garden Irrigation` and click **Download**.
5. Restart Home Assistant.

### ⚙️ Initial configuration

1. **Settings** → **Devices & services**.
2. **Add integration** → search for `My Garden Irrigation`.
3. Follow the guided forms to add your crops and link your valve.

---

## 📋 Requirements

- Home Assistant 2024.1 or later.
- A working HACS.
- Geographic coordinates set in Home Assistant (for the Open-Meteo retrieval).
- An active Internet connection (Open-Meteo requests and Kc repository — _cloud polling_).
