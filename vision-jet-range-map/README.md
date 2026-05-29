# Vision Jet — Carte de rayon d'action

Carte interactive du rayon d'action du **Cessna SF50 Vision Jet (G2/G2+)** depuis
n'importe quel point du monde, sélectionnable.

## Utilisation

Ouvrez simplement `index.html` dans un navigateur (aucune installation requise).

Ou servez le dossier localement :

```bash
cd vision-jet-range-map
python3 -m http.server 8000
# puis ouvrez http://localhost:8000
```

## Fonctionnalités

- **Point d'origine sélectionnable** : clic sur la carte, marqueur déplaçable,
  bouton « Ma position » (géolocalisation), ou recherche de ville (Nominatim).
- **Anneaux de rayon géodésiques** (grands cercles, exacts à longue distance) :
  - Conservateur — 950 NM (≈ 1 760 km)
  - Nominal — 1 100 NM (≈ 2 040 km)
  - Max — 1 275 NM (≈ 2 360 km)
- **Anneau réglable** via curseur (700 → 1 275 NM).
- **Endurance estimée** selon la vitesse de croisière choisie (240–311 kt).
- **Liste de destinations** avec distance grand cercle et statut
  (atteignable / limite / hors portée) recalculé en direct.

## Notes techniques

- Single-file, pur HTML/JS, carto via [Leaflet](https://leafletjs.com/) + tuiles
  OpenStreetMap (nécessite un accès réseau pour les tuiles et la recherche).
- Les anneaux sont des cercles **géodésiques** (formule de destination
  haversine), pas de simples cercles plans — donc corrects même aux latitudes
  élevées et sur de longues distances.

> ⚠️ Outil indicatif. Les valeurs de rayon « pratique » intègrent réserves IFR,
> vent et charge typiques, mais varient selon les conditions réelles.
> **Ne pas utiliser pour la planification de vol opérationnelle.**
