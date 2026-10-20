# 0.3.0.1

Cette version complète le support local de la Vent-Axia Sentinel Econiq 300 et conserve le backend Sentinel Kinetic Advance S.

- Choix du mode de dérogation et de sa durée, avec application explicite ; annulation du mode sélectionné.
- Modes Réduit, Normal, Boost, Purge et Maximum ; durées de 15 minutes à 8 heures.
- Libellés français/anglais lisibles pour les températures, moteurs, états et alertes W-12/W-13.
- Débits mesurés en L/s et durées moteur en heures.
- Lecture des profils, compteur total, types de filtres, intervalles, dates et prochaines échéances de maintenance.
- Diagnostics bypass été et protection antigel en lecture seule.
- Découverte des zones et sondes publiées, avec identifiants stables et prise en compte des listes actives.
- Durée restante basée sur l’horloge de la VMC ; aucune commande au démarrage ou à la reconnexion.

Le domaine reste `ventaxia_ha` : conserver l’entrée HA existante et redémarrer Home Assistant après la mise à jour. Ne pas installer simultanément l’intégration d’origine et le fork dans le même dossier.

Validation : 123 tests automatisés avec transport simulé. L’intégration de base fonctionne selon le retour utilisateur ; les nouveaux contrôles et topics restent à vérifier sur l’appareil. Une publication GitHub ne constitue pas une validation réelle de l’installation ou de la mise à jour HACS.

Les compteurs de filtres/entretien restent en lecture seule. Aucun reset, calibration ou contrôle de firmware n’est exposé.

Instructions : [guide HACS](doc/HACS_FR.md) et [fonctions Econiq](doc/ECONIQ_APK.md).
