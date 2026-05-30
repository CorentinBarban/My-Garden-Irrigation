"""Constantes pour l'intégration My Garden Irrigation."""

DOMAIN = "my_garden_irrigation"
PLATFORMS = ["sensor", "number", "select"]
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

# --- Flag interne : mise à jour d'un champ sans rechargement complet ---
OPTIONS_FIELD_UPDATE_FLAG = "_field_update"

# --- Services ---
SERVICE_RECALCULATE = "recalculate"

# --- Validation ---
MAX_REASONABLE_SURFACE_M2 = 10_000
