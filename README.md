# Veille GTA 6 FR

Bot de veille : détecte les news GTA 6 sur 5 sources et les poste en français
sur un canal Telegram, plus un brief chaque soir avec les 3 meilleurs angles vidéo.

## Sources surveillées

| Source | Rôle |
|---|---|
| Rockstar (YouTube) | Trailers et annonces officielles — l'alerte la plus précieuse |
| Rockstar Mag' | Presse FR spécialisée Rockstar |
| GTAboom | Agrégateur EN le plus rapide |
| VGC | Presse EN générale (filtrée GTA/Rockstar) |
| Google News FR | Radar large FR (usage perso pour le brief) |

## Installation locale

```
py -3.12 -m pip install -r requirements.txt
py -3.12 veille.py --dry-run
```

Premier lancement : marque tout comme "vu" sans rien envoyer (pas de spam).
Les lancements suivants n'alertent que sur le nouveau (< 48 h).

## Mise en production (une fois, ~10 min)

1. **Créer le bot Telegram** : parler à [@BotFather](https://t.me/BotFather) →
   `/newbot` → récupérer le token.
2. **Créer le canal** public (ex. `@gta6veillefr`), y ajouter le bot comme admin.
3. **Créer un repo GitHub** (privé suffit), pousser ce dossier.
4. Dans le repo : Settings → Secrets and variables → Actions → ajouter
   `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` (= `@nomducanal`).
5. Le workflow tourne toutes les ~10 min + brief à 20h (Paris, heure d'été).
   Penser à passer le cron du brief à `0 19 * * *` à l'heure d'hiver.

## Notes

- Sans token configuré, le bot fonctionne en dry-run (affichage console).
- `seen.json` est l'état de déduplication, commité automatiquement par le workflow.
- Le flux Google News sert de radar privé pour le brief ; les alertes publiques
  pointent toujours vers l'article source, jamais vers Google News.
