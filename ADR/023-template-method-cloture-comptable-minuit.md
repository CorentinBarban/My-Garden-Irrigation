# 023 — Template Method : Algorithme de clôture comptable de minuit

**Date** : 2026-06-03  
**Statut** : Proposé  
**Décideurs** : Équipe projet

---

## Contexte

La clôture de minuit est le point de synchronisation comptable le plus critique du système : c'est elle qui fait transiter le flux journalier (besoin du jour) vers le stock historique (bilan cumulé). La Règle 1 de la spécification impose un algorithme précis en quatre étapes séquentielles :

1. **Collecter** les besoins journaliers depuis les données météo (ou le dernier cache connu).
2. **Équilibrer** le bilan cumulé selon la formule `max(0, cumulé + journalier − arrosé_aujourd'hui)`.
3. **Persister** le nouvel état sur disque.
4. **Réinitialiser** le compteur d'arrosages du jour (`watering_applied_today`).

Aujourd'hui, cette séquence est codée de manière informelle dans `_on_midnight` de `coordinator.py` (L133-151), qui appelle `config.apply_midnight_transfer()` (L322-331 de `config_state.py`), puis `_persistence.async_save()`, puis `async_refresh()`. La formule d'équilibrage est déjà correcte dans `core/ledger.py::midnight_transfer` et l'étape 4 est atomique avec l'étape 2 dans `apply_midnight_transfer`.

Le risque résiduel est une **erreur d'ordre** lors d'une future refactorisation : un développeur qui déplacerait `_watering_applied_today = {}` avant le calcul de la balance, ou qui appelerait `async_refresh()` avant la persistance, corromprait silencieusement le grand livre hydrique sans lever d'exception. Le contrat algorithmique est implicite.

## Décision

Extraire une classe `MidnightClosureOrchestrator` dans `core/ledger.py` (ou un module `core/midnight.py`) qui encode le squelette algorithmique sous forme de Template Method. La méthode publique `execute()` appelle les étapes dans un ordre fixe et non substituable. Les détails de chaque étape (collecte météo, I/O, refresh HA) sont injectés sous forme de callables ou de sous-classes.

### Squelette algorithmique

```python
class MidnightClosureOrchestrator:
    """Encode l'ordre immuable des étapes de la clôture comptable de minuit."""

    def execute(
        self,
        cumulative_need: dict[str, float],
        daily_needs: dict[str, float],
        watering_applied_today: dict[str, float],
    ) -> dict[str, float]:
        """Retourne le nouveau bilan cumulé après équilibrage.

        L'appelant (coordinator) est responsable de la persistance et du refresh
        HA après avoir récupéré le résultat — l'orchestrateur reste pur Python.
        """
        # Étape 2 : équilibrage absolu (Règle 1)
        new_cumulative = midnight_transfer(
            cumulative_need, daily_needs, watering_applied_today
        )
        # Les étapes 3 (persistance) et 4 (reset) restent dans coordinator/_on_midnight
        # car elles dépendent de l'infrastructure HA.
        return new_cumulative
```

La réorganisation dans `coordinator.py::_on_midnight` devient :

```python
async def _on_midnight(self) -> None:
    daily_needs = self._resolve_daily_needs()      # étape 1 — collecte avec fallback
    self.config.apply_midnight_transfer(daily_needs)  # étapes 2+4 atomiques
    await self._persistence.async_save(            # étape 3 — persistance
        self.config.to_storage(dt_util.now().date().isoformat())
    )
    await self.async_refresh()                     # notification HA
```

La méthode auxiliaire `_resolve_daily_needs()` extrait le bloc `if self.data is not None / elif / else` des lignes L134-146 dans une fonction nommée, rendant l'ordre des étapes lisible sans avoir à parcourir le code de gestion des cas dégradés.

## Justification

- **Invariant algorithmique** : le pattern Template Method garantit que l'équilibrage (étape 2) précède toujours la persistance (étape 3), et que la réinitialisation du flux journalier (étape 4) est atomique avec l'équilibrage — propriété déjà assurée par `apply_midnight_transfer` mais rendue explicite.
- **Testabilité pure** : `MidnightClosureOrchestrator.execute()` est une fonction pure (dictionnaires en entrée, dictionnaire en sortie) testable avec `pytest` sans aucune infrastructure HA.
- **Lisibilité** : `_resolve_daily_needs()` isole la logique de fallback météo, rendant le squelette principal de `_on_midnight` linéaire et auditable en une lecture.

## Conséquences

- **Positives** : l'algorithme de clôture devient auto-documenté via ses noms de méthodes ; les tests de non-régression des Scénarios I et II de la spécification s'écrivent en appels directs à `midnight_transfer` sans mocks HA.
- **Négatives** : légère indirection supplémentaire — `_on_midnight` délègue à `_resolve_daily_needs` puis `apply_midnight_transfer` plutôt que d'avoir le code inline. Surcoût nul à l'exécution.
- **Relation** : formalise la Règle 1 de `spec.md` ; s'appuie sur `core/ledger.py::midnight_transfer` (déjà correct) ; protège l'invariant comptable introduit par ADR-019.
