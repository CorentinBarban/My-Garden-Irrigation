"""Constantes pour l'intégration My Garden Irrigation."""

DOMAIN = "my_garden_irrigation"
PLATFORMS = ["sensor", "number", "select", "button", "switch", "time"]
ATTRIBUTION = "Données Kc : FAO Irrigation and Drainage Paper 56"

# --- Config / Options entry keys ---
CONF_NAME = "name"
CONF_CROPS = "crops"
CONF_CROP_ID = "crop_id"
CONF_CROP_NAME = "crop_name"
CONF_CROP_TYPE = "crop_type"
CONF_STAGE = "stage"
CONF_NB_PLANTS = "nb_plants"
CONF_DENSITY = "density"

# --- Stades de croissance FAO ---
STAGE_INI = "ini"
STAGE_MID = "mid"
STAGE_END = "end"
STAGES = [STAGE_INI, STAGE_MID, STAGE_END]

# --- Cultures supportées (clés JSON Kc) ---
SUPPORTED_CROPS = [
    "ail",
    "artichaut",
    "asperge",
    "aubergine",
    "basilic",
    "betterave",
    "brocoli",
    "carotte",
    "celeri",
    "chou",
    "chou_fleur",
    "concombre",
    "courgette",
    "epinard",
    "fraise",
    "haricot_vert",
    "laitue",
    "melon",
    "oignon",
    "persil",
    "petits_pois",
    "poireau",
    "poivron",
    "pomme_de_terre",
    "potiron",
    "radis",
    "tomate",
]

# --- Densités FAO par défaut (plants/m²), dupliquées ici pour le Config Flow ---
FAO_DEFAULT_DENSITIES: dict[str, float] = {
    "ail": 20.0,
    "artichaut": 1.0,
    "asperge": 3.0,
    "aubergine": 2.0,
    "basilic": 9.0,
    "betterave": 12.0,
    "brocoli": 4.0,
    "carotte": 60.0,
    "celeri": 6.0,
    "chou": 4.0,
    "chou_fleur": 4.0,
    "concombre": 2.0,
    "courgette": 1.0,
    "epinard": 16.0,
    "fraise": 7.0,
    "haricot_vert": 12.0,
    "laitue": 8.0,
    "melon": 1.0,
    "oignon": 25.0,
    "persil": 16.0,
    "petits_pois": 20.0,
    "poireau": 10.0,
    "poivron": 3.0,
    "pomme_de_terre": 5.0,
    "potiron": 1.0,
    "radis": 80.0,
    "tomate": 3.0,
}

# --- Vanne globale (ADR-009) ---
CONF_GLOBAL_VALVE_ENTITY_ID = "global_valve_entity_id"
CONF_GLOBAL_FLOW_RATE = "global_flow_rate"

# --- Fréquence et mode d'arrosage (ADR-010) ---
CONF_WATERING_FREQUENCY = "watering_frequency"
CONF_WATERING_INTERVAL_DAYS = "watering_interval_days"
CONF_WATERING_MODE = "watering_mode"

WATERING_FREQUENCY_DAILY = "daily"
WATERING_FREQUENCY_INTERVAL = "interval"
WATERING_FREQUENCIES = [WATERING_FREQUENCY_DAILY, WATERING_FREQUENCY_INTERVAL]

WATERING_MODE_CONTINUOUS = "continuous"
WATERING_MODE_FRACTIONED = "fractioned"
WATERING_MODES = [WATERING_MODE_CONTINUOUS, WATERING_MODE_FRACTIONED]

DEFAULT_CYCLES_COUNT = 3
DEFAULT_SOAK_DURATION_MINUTES = 15

CONF_CYCLES_COUNT = "cycles_count"
CONF_SOAK_DURATION = "soak_duration_minutes"

# --- Attributs des sensors ---
ATTR_CROP_TYPE = "crop_type"
ATTR_STAGE = "stage"
ATTR_NB_PLANTS = "nb_plants"
ATTR_DENSITY = "density_plants_per_m2"
ATTR_SURFACE_M2 = "surface_m2"
ATTR_KC = "kc"
ATTR_ETO_MM = "eto_mm"
ATTR_LITERS_PER_PLANT = "liters_per_plant"
ATTR_WEEKLY_PROJECTION_L = "weekly_projection_l"
ATTR_VIA_DEVICE = "via_device"
ATTR_PRECIPITATION_MM = "precipitation_mm"
ATTR_EFFECTIVE_RAINFALL_MM = "effective_rainfall_mm"
ATTR_ETC_LITERS = "etc_liters"
ATTR_NET_LITERS = "net_liters"
ATTR_WATERING_APPLIED_TODAY_LITERS = "watering_applied_today_liters"
ATTR_CUMULATIVE_NEED_LITERS = "cumulative_need_liters"
ATTR_RECOMMENDED_DURATION_MINUTES = "recommended_duration_minutes"
ATTR_IS_FRACTIONED = "is_fractioned"
ATTR_CYCLES_COUNT = "cycles_count"
ATTR_DURATION_PER_CYCLE_MINUTES = "duration_per_cycle_minutes"
ATTR_SOAK_DURATION_MINUTES = "soak_duration_minutes"

# --- Open-Meteo (ETo quotidien) ---
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT = 10  # secondes

# --- Données Kc distantes (ADR-001) ---
KC_REMOTE_URL = (
    "https://raw.githubusercontent.com/CorentinBarban/My-Garden-Irrigation"
    "/main/data/kc_fao56.json"
)
KC_FETCH_TIMEOUT = 10  # secondes
KC_CACHE_KEY = f"{DOMAIN}_kc_data"

# --- Arrosage automatique (planifié par la centrale) ---
CONF_IRRIGATION_TIME = "irrigation_time"
DEFAULT_IRRIGATION_TIME = "06:00:00"

# --- Storage (ADR-008) ---
STORAGE_VERSION = 1

# --- Services ---
SERVICE_RECALCULATE = "recalculate"

# --- Validation ---
MAX_REASONABLE_SURFACE_M2 = 10_000
