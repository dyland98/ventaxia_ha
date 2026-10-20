# 0.3.1

Simplifie les commandes de la Sentinel Econiq.

- Supprime Boost 15 minutes, Cancel Boost et les quatre boutons de configuration Low/Normal/Purge/Maximum 15 min.
- Retire automatiquement leurs six entrées du registre Home Assistant, y compris les boutons désactivés.
- Renomme le bouton « Annuler la dérogation sélectionnée » sans « à valider », en conservant son identifiant.
- Conserve les listes de mode et de durée, le bouton Appliquer et l’unique abonnement MQTT corrigé en 0.3.0.2.

Mettre à jour depuis HACS puis redémarrer Home Assistant. Adapter les automatisations qui utilisaient les boutons supprimés. Aucune commande n’est envoyée au démarrage ; les compteurs restent en lecture seule.

Validation : 123 tests automatisés passent, ainsi que les contrôles locaux de style et de publication. L’installation HACS et l’annulation sur la VMC réelle ne sont pas validées par ces tests.
