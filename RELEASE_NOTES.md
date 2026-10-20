# 0.3.0.2

Corrige la séquence de reconnexions MQTT observée avec la Sentinel Econiq après la mise à jour 0.3.0.1.

- Rétablit l’unique abonnement `<préfixe>/#`, validé précédemment sur l’appareil.
- Supprime le paquet d’abonnement supplémentaire à plusieurs topics : ses erreurs étaient suivies d’une déconnexion que le repli ne pouvait pas réparer.
- Conserve les nouvelles entités, les contrôles et les parseurs pour les données effectivement publiées par la VMC. Les topics non publiés restent inconnus.
- Ajoute le type d’erreur et le code MQTT, lorsqu’il est disponible, aux journaux de reconnexion sans exposer la PSK.

Validation : 123 tests automatisés passent, dont un scénario simulant un serveur qui ferme la session lors d’un abonnement supplémentaire. Le correctif reste à confirmer sur la VMC réelle ; l’installation HACS n’est pas validée par ces tests.

Installer la mise à jour du fork dans HACS puis redémarrer Home Assistant. Conserver l’entrée d’intégration et sa configuration existantes. Aucune commande de ventilation ni remise à zéro n’est envoyée au démarrage.

La release 0.3.0.1 reste disponible ; son tag n’a pas été modifié.
