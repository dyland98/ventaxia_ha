# Econiq : commandes, libellés et examen de l’APK

Travail effectué dans le `main` local du fork `dyland98/ventaxia_ha`.
APK fourni : `uk-ventaxia-connect-6000172-68997366-fda03626c8c6183b297c144e16d7f3d9.apk`.
SHA-256 de l’APK : `f7dd67d0e83d7771c0669f1a6afa7145eab35ed78f9609266ddb05528c5f04b2`.
Analyse ciblée avec jadx 1.5.0 et extraction des ressources avec apktool. La
décompilation globale a signalé 142 erreurs dans l’APK ; ce n’est pas un audit
exhaustif de toutes les méthodes. Les classes ciblées de commandes et les sources
citées ci-dessous ont pu être examinées.

Les fichiers décompilés restent dans `/tmp`, hors du dépôt ; aucun binaire ni code
complet de l’application n’est ajouté à l’intégration.

## Utilisation dans Home Assistant

Après installation des fichiers modifiés et redémarrage HA, ouvrir l’appareil
**Vent Axia** dans Paramètres > Appareils et services :

1. Choisir **Mode de la dérogation** : Réduit, Normal, Boost, Purge ou Maximum.
2. Choisir **Durée de la dérogation** : 15 min, 30 min, 1 h, 2 h, 4 h ou 8 h.
3. Appuyer sur **Appliquer la dérogation**.
4. Vérifier **Mode de ventilation actuel**, **Origine de la dérogation** et les RPM.

Les deux listes préparent une demande locale. Seul le bouton Appliquer envoie la
commande. Les choix sont restaurés après redémarrage, sans réappliquer la commande.
Modifier uniquement la durée ne prolonge donc pas une dérogation déjà en cours.
Pour prolonger/réappliquer une dérogation, appuyer explicitement sur Appliquer.
La durée est demandée au contrôleur : aucun timer HA ne force ensuite un retour
au mode Normal, qui pourrait écraser la programmation ou une protection de la VMC.

Maximum est inclus car l’utilisateur confirme sa réaction physique. L’application
peut conserver le mode précédent dans ses informations : ce comportement ne
permet pas de confirmer `ps = 5`. Le sélecteur indique ce qu’on souhaite appliquer,
le capteur d’état indique exclusivement ce que la VMC publie. Une commande envoyée
ne remplace jamais les valeurs du cache de télémétrie.

Le raccourci Boost 15 minutes et les anciens boutons restent disponibles avec
leurs identifiants existants. Le raccourci Boost reste fixé à 15 minutes et ne
reprend pas la durée du sélecteur. Les anciens boutons de modes à durée fixe sont
conservés pour les automatisations existantes ; ils ne constituent pas le nouveau
parcours recommandé. Le bouton Annuler Boost reste une commande à vérifier si
l’utilisateur ne l’a pas encore testée.

Les listes sont des entités HA `select`, utilisables dans une carte Entités et
avec `select.select_option`. Le bouton s’utilise avec `button.press`. Cette
organisation reprend la séparation profil/durée des intégrations de ventilation
comme [Vallox](https://www.home-assistant.io/integrations/vallox/) et emploie les
[entités Select natives](https://developers.home-assistant.io/docs/core/entity/select/).

## Éléments effectivement lus dans l’APK

Les noms ci-dessous permettent de retrouver les preuves sans publier l’APK.

| Source | Constat | Conséquence |
| --- | --- | --- |
| `VentilationModeViewModel.setMode` / `getUserOverrideTime` | Low/Normal/Boost/Purge ; durées 15/30/60/120/240/480 minutes | Choix de modes et durées du nouveau parcours |
| `MQTTFactory.prepareUserOverrideMessage` | JSON `gtm` et `treq` | Commande sur `vent/uo`, QoS 0, retain false |
| `com.component.kinetic.model.FanMode` | SDK IDs 1/2/3/4/5 pour Low/Normal/Boost/Purge/Maximum | Maximum vérifié séparément par la réaction physique rapportée par l’utilisateur |
| `MQTTConstantsKt` et `FaultCode` / `WarningCode` | T1 admission extérieure, T2 insufflation, T3 extraction, T4 rejet | Noms compréhensibles ; identifiants existants conservés |
| `MQTTConstantsKt.AIRFLOW_SUPPLY_GENERAL_TOPIC` / `AIRFLOW_EXTRACT_GENERAL_TOPIC` | AFS = insufflation ; AFE = extraction | Noms moteurs en clair |
| `MQTTFactory.handleAirflowMessage` + `SystemParametersAdapter.prepareAirVolumeStrings` | `fm` est le débit mesuré ; conversion L/s → m³/h par ×3,6 | Débit mesuré en L/s ; `fm = -1` signifie mesure absente |
| `SupplyMotorRuntimeEvent` / `ExtractMotorRuntimeEvent` | `dr` est transmis en secondes | Affichage en heures, secondes brutes gardées en attribut |
| `ControlMode.getFromInt` | 0 = pourcentage fixe, 1 = débit constant, 2 = pression constante | État de régulation traduit, sans commande de réglage |
| `HomeFragmentViewModel.onChangeAirQualityEvent` | 1 bonne, 2 moyenne, 3 mauvaise | Qualité de l’air traduite ; code inconnu préservé |
| `OverrideType` | `ot = 9` : utilisateur ; `0` : aucune dérogation ; autres origines identifiées | Origine de la dérogation traduite |
| `HomeFragmentViewModel.onCurrentVentilationEvent` | Calcule une fin à partir de `timeStarted + timeRequested` | Durée restante calculée avec `trem`, `treq` et l’horloge `mdet/rtc` de la VMC, sans comparaison avec l’horloge HA |

Le nom des constantes d’humidité n’est pas cohérent partout : `EXTERNAL_RELATIVE_HUMIDITY`
utilise ERH tandis que `EXTRACT_RH_CONFIG_TOPIC` utilise aussi ERH. Les canaux
ERH/IRH restent nommés explicitement ; pas de permutation supposée intérieur/extérieur.

Les consignes `fd` peuvent dépendre du mode de régulation. Le code de l’app propose
un pourcentage en absence de débit mesuré. Les consignes ne sont donc pas toutes
étiquetées L/s. Les mesures de pression des filtres et la durée de vie `lr` restent
sans unité ajoutée faute de chaîne de conversion suffisamment établie.

## Avertissements 6144 : corrélation confirmée par l’utilisateur

Le 20 octobre 2026, l’utilisateur rapporte dans l’app :

- **W-12 : nettoyage/remplacement du filtre en retard** ;
- **W-13 : entretien en retard**.

La télémétrie fournie vaut `6144 = 2048 + 4096`, soit les bits 11 et 12. Les indices
`FILTER_CLEAN_OVERDUE(11)` et `SERVICE_OVERDUE(12)` de `WarningCode` correspondent à
ces deux avertissements. Ces deux correspondances sont utilisées pour les libellés
et les indicateurs individuels ; cela ne fait pas de 6144 un nombre d’avertissements.

L’APK contient une incohérence : certaines méthodes `Utils` font un ET binaire
direct sur les indices de l’enum, sans décalage. Les autres correspondances ne sont
donc pas généralisées sans observation supplémentaire. Un bit non identifié donne
un état « Autre avertissement présent », avec la valeur et les positions brutes en
attributs. L’absence de donnée reste inconnue ; elle n’est jamais « Aucun défaut ».

Les identifiants des capteurs restent inchangés. Les historiques des modes et
alertes deviennent textuels. Un nom personnalisé saisi dans HA reste prioritaire ;
la mise à jour d’une traduction ne renomme pas automatiquement un identifiant
`entity_id` déjà enregistré ni un nom personnalisé.

## Fonctions supplémentaires implémentées

Le backend lit maintenant les topics ci-dessous. Les abonnements explicites de
lecture complètent l’abonnement au préfixe ; aucune commande de réglage ne part
au démarrage ou à la reconnexion. Si ces abonnements supplémentaires échouent,
la connexion de base continue de recevoir ses données push.

Une fonction implémentée n’est pas nécessairement publiée par chaque firmware :
les données non reçues restent inconnues, sans valeur par défaut inventée.

| Fonction / topics | Comportement ajouté |
| --- | --- |
| Annulation `vent/uo` | **Annuler la dérogation sélectionnée (à valider)** utilise le mode choisi et `treq = 00:00:00`, y compris Maximum ; aucun changement d’état optimiste |
| Profils `vent/pf1` à `vent/pf4` | Noms et consignes reçus, quatre capteurs de profil ; noms également accessibles dans les attributs du sélecteur et du mode courant |
| `mdet/runt` | Durée totale en heures, valeur brute conservée |
| Filtres `vent/filtertmr/int`, `vent/filtertmr/last`, `vent/filter1/typ`, `vent/filter2/typ` | Intervalle en mois, date du dernier changement, prochaine échéance, types de filtres |
| Entretien `mdet/svctmr/int`, `mdet/svctmr/last` | Intervalle, date du dernier entretien et prochaine échéance |
| Bypass `vent/sbc`, `vent/sbs` | Mode configuré, seuils de température, mode de ventilation associé, mode actif, ouverture en % et position ; lecture seule |
| Antigel `vent/afstat`, `vent/afc` | État traduit et paramètres de préchauffage reçus ; puissance/utilisation conservées brutes si l’unité n’est pas confirmée ; lecture seule |
| `zone/<id>/...` | Découverte des mesures température, humidité, CO₂, COV pour les zones 1–15 |
| `sn/<id>/...` | Découverte des mesures, batterie, signal, état, position de clapet et contact publiés par les sondes 1–31 ; pas de supposition d’unité pour les canaux non confirmés |
| `zone/active`, `sn/active` | Prise en compte des listes actives avec les décalages distincts retrouvés dans `ZoneViewModel` et `DeviceViewModel` ; retrait → entités indisponibles sans suppression des identifiants |
| Dérogation `vent/cor`, `mdet/rtc` | Durée demandée et durée restante suivant l’horloge de la VMC |

Les échéances ajoutent des **mois calendaires** à la dernière date : le 31 janvier
+ un mois arrive au dernier jour de février. Un intervalle nul est désactivé : pas
de prochaine date inventée. Les dates attendues sont ISO `AAAA-MM-JJ`, comme dans
le chemin ESP récent de l’APK. Un format absent ou non reconnu reste inconnu.

Pour annuler, **choisir d’abord le mode de la dérogation concernée**, puis appuyer
sur Annuler la dérogation sélectionnée. Le bouton ne prétend pas deviner le mode
réel à partir de `ps`, qui peut rester inchangé lors de Maximum. L’activation et
l’annulation sont des demandes dont la réaction doit être observée sur la VMC.

La durée restante se met à jour à réception des messages, notamment de `mdet/rtc` ;
ce n’est pas un décompte HA autonome à la seconde. Sans horloge VMC ou sans début
valide, elle reste inconnue. Une date future par rapport à cette horloge ou des
fuseaux incompatibles ne donnent pas de durée supposée. Aucun minuteur ne publie
une commande à l’échéance.

Les zones/sondes sont créées lorsqu’un topic de mesure reconnu arrive, avec un
identifiant dérivé du préfixe, du numéro de canal et de la mesure, jamais du nom.
Le nom configuré et la zone associée sont disponibles en attributs lorsque les
métadonnées `/conf` et `/info` arrivent. Les anciens canaux fixes `zone/2/t`,
`zone/2/co2` et `sn/1/rh` conservent leurs identifiants et ne sont pas dupliqués.
L’abonnement existant au préfixe reçoit ces données sans demander de réappairage.

**Périmètre confirmé par l’utilisateur :** compteurs de filtres et d’entretien en
lecture seule. Aucun bouton de remise à zéro, écriture des consignes de profils,
calibration, réglage d’installation, reset usine ou mise à jour firmware n’est
exposé. Les listes de modes/durées et les boutons de dérogation restent les seules
commandes de cette extension. Il ne s’agit pas d’une copie de toute l’application.

## Vérifications à faire sur HA/VMC

Aucune commande n’a été envoyée à la VMC par l’agent. L’intégration de base fonctionne
selon le retour de l’utilisateur ; les nouveaux sélecteurs et conversions doivent
encore être installés et testés sur son HA.

- Vérifier les cinq modes et les durées, application mobile fermée. Comparer les
  RPM et les messages reçus ; noter que Maximum peut conserver le `ps` précédent.
- Modifier les deux listes, puis redémarrer HA avant Appliquer : aucune commande
  ne doit partir et les choix doivent être restaurés.
- Vérifier W-12 et W-13, sans réinitialiser les compteurs d’entretien pour le test.
- Comparer les débits mesurés avec l’écran de l’app configuré en L/s ; si l’app est
  en m³/h, comparer la valeur multipliée par 3,6.
- Pour lever les dernières ambiguïtés, relever les unités des consignes `fd`, les
  pressions filtres et la durée de vie restante dans l’app. Un export des diagnostics
  HA suffit pour les valeurs déjà supportées ; ne pas fournir la PSK ni `.storage`.

- Observer les profils, intervalles et dates reçus ; vérifier les types de filtres
  sans changer les compteurs. Une échéance inconnue indique une donnée manquante,
  un intervalle désactivé ou un format non reconnu.
- Observer le bypass et l’antigel lorsqu’ils sont actifs naturellement ; aucune
  commande de calibration ou de protection n’est nécessaire pour ces tests.
- Vérifier les sondes/zones réellement présentes et leurs noms reçus. Si une liste
  active est publiée, vérifier qu’un retrait rend les entités indisponibles.
- Pour une dérogation connue, sélectionner son mode puis tester Annuler ; vérifier
  les RPM, l’état et les attributs reçus, notamment avec Maximum.
- Vérifier les durées reçue/restante par rapport à l’app ; la durée restante dépend
  de la fréquence de publication de l’horloge VMC, pas de l’heure du serveur HA.

Après installation du code, redémarrer HA pour charger la nouvelle plateforme
Select/Sensor et les nouvelles traductions. Pas besoin de supprimer/recréer l’entrée
existante. Ne publier une nouvelle version HACS qu’après ces vérifications.
