"""Constantes pour l'intégration My Garden Irrigation."""

DOMAIN = "my_garden_irrigation"
PLATFORMS = ["sensor"]
ATTRIBUTION = "Données Kc : FAO Irrigation and Drainage Paper 56"

# --- Config / Options entry keys ---
CONF_NAME = "name"
CONF_ETO_ENTITY_ID = "eto_entity_id"
CONF_CROPS = "crops"
CONF_CROP_ID = "crop_id"
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
    "tomate",
    "carotte",
    "haricot",
    "poivron",
    "laitue",
    "courgette",
    "oignon",
]

# --- Densités FAO par défaut (plants/m²), dupliquées ici pour le Config Flow ---
FAO_DEFAULT_DENSITIES: dict[str, float] = {
    "tomate": 3.0,
    "carotte": 60.0,
    "haricot": 12.0,
    "poivron": 3.0,
    "laitue": 8.0,
    "courgette": 1.0,
    "oignon": 25.0,
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

# --- Données Kc distantes (ADR-001) ---
KC_REMOTE_URL = (
    "https://raw.githubusercontent.com/CorentinBarban/My-Garden-Irrigation"
    "/main/data/kc_fao56.json"
)
KC_FETCH_TIMEOUT = 10  # secondes
KC_CACHE_KEY = f"{DOMAIN}_kc_data"

# --- Services ---
SERVICE_RECALCULATE = "recalculate"

# --- Validation ---
MAX_REASONABLE_SURFACE_M2 = 10_000
