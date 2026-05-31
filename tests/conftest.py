"""Configuration pytest — rend custom_components importable sans HA."""
import sys
from pathlib import Path

# Ajoute la racine du projet au PYTHONPATH pour que les imports relatifs
# de custom_components.my_garden_irrigation.* fonctionnent sans HA installé.
sys.path.insert(0, str(Path(__file__).parent.parent))
