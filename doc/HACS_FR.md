# Installation, publication et validation du fork

Dépôt à utiliser : **https://github.com/dyland98/ventaxia_ha**.
Original : https://github.com/JosyBan/ventaxia_ha (licence MIT conservée).
Remotes observés : `origin` = fork ; aucun `upstream`. Aucun clone supplémentaire.

## État de validation et prérequis

La version préparée est `0.3.1`. Le workflow ne publie que lorsqu’un tag `vX.Y.Z` ou `vX.Y.Z.N`
est poussé explicitement. Aucune publication n’est effectuée par une modification
locale, un commit de branche ou une pull request. L’ancien Release Drafter a été
retiré afin de ne pas proposer une version indépendante du manifeste.

Le minimum déclaré est HA **2026.10.0**, correspondant à la version du banc de
test automatisé, qui requiert Python ≥ 3.14.2. Le protocole Econiq exige les API
PSK natives introduites dans Python 3.13, mais ces API seules ne constituent pas
une validation des anciennes versions HA. Le script de test local ne vérifie pas
votre HA Proxmox, l’installation HACS ni la VMC.

Dans **le conteneur/runtime Home Assistant Core** (pas dans l’add-on Terminal),
si un shell y est accessible, vérifier :

```sh
python3 -c 'import sys, ssl; print(sys.version); print(ssl.OPENSSL_VERSION); print(getattr(ssl, "HAS_PSK", False)); print(hasattr(ssl.SSLContext, "set_psk_client_callback"))'
```

Les deux dernières lignes doivent être `True`. Le config flow et le chargement
font ce contrôle eux-mêmes. Si l’une vaut `False`, mettre à jour le runtime HA
avec un Python/OpenSSL prenant en charge PSK. Aucun repli vers un sous-processus
openssl, un courtier Mosquitto ou une clé par défaut n’est implémenté.

## 1. Publier une version (opérations à faire seulement sur demande)

Avant publication, terminer les essais HA/VMC ci-dessous. Une release publique
rend le code disponible ; elle ne certifie pas ces essais. Le fork doit être
accessible à HACS (de préférence public), et GitHub Actions activé dans son onglet
Actions. Vérifier aussi que les Issues sont activées dans les paramètres du fork.

Dans la branche de travail, vérifier les changements, puis exécuter :

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python scripts/check_release.py --tag v0.3.1
.venv/bin/pytest --disable-socket --allow-unix-socket tests
```

Le manifeste est la version de référence. Mettre à jour `RELEASE_NOTES.md` pour la
même version : le workflow publie ces notes avec la release. `custom_components/ventaxia_ha/pyproject.toml`
doit porter la même version et les mêmes dépendances. Pour la version suivante,
modifier ces deux fichiers et documenter les changements avant de créer le tag.
`hacs.json` ne porte pas la version : HACS lit les tags des releases GitHub.

**Commandes de publication à exécuter uniquement après approbation explicite** :

```sh
git add custom_components hacs.json README.md RELEASE_NOTES.md doc scripts tests setup.cfg requirements_test.txt .pre-commit-config.yaml .github
git commit -m "Add Econiq backend and prepare fork HACS releases"
git push origin main
```

Le travail se fait désormais sur **le `main` du fork dyland98** à la demande de
l’utilisateur. Vérifier `git branch --show-current` et `git remote -v` avant ces
commandes : `origin` doit rester `https://github.com/dyland98/ventaxia_ha.git`.
Ne pas créer de publication dans le dépôt JosyBan. Après le push de `main`, attendre
les tests et contrôles GitHub avant de créer et pousser le tag explicitement :

```sh
git switch main
git pull --ff-only origin main
.venv/bin/python scripts/check_release.py --tag v0.3.1
git tag v0.3.1
git push origin v0.3.1
```

Le push du tag lance `.github/workflows/release.yaml`, vérifie tag/manifeste,
exécute les tests simulés puis crée la release dans `${{ github.repository }}`,
donc le fork sur lequel l’action tourne. Pas de téléchargement depuis l’original.
Le workflow ne crée pas de tag. Une version stable utilise `v0.3.1` dans Git et
`0.3.1` dans le manifeste ; ne jamais déplacer un tag déjà publié.

Vérifier ensuite https://github.com/dyland98/ventaxia_ha/releases : release publiée,
non brouillon, marquée Latest, bon tag et bon commit. HACS télécharge les fichiers
de `custom_components/ventaxia_ha` à cette référence. Aucun ZIP spécifique n’est
nécessaire (`zip_release` et `content_in_root` restent absents/faux).
Les archives source générées par GitHub contiennent la racine du dépôt ; pour une
installation manuelle, extraire uniquement son dossier `custom_components/ventaxia_ha`.
Si l’action échoue, corriger le code et publier une nouvelle version si le tag a
déjà été rendu public ; ne pas publier une release malgré des tests échoués.

## 2. Remplacer une installation d’origine sans perdre sa configuration

Le domaine reste `ventaxia_ha`. Il est référencé par les imports, les services,
les traductions, les identifiants de registre et les entrées de configuration.
Les entrées Kinetic existantes, sans `device_type`, restent Kinetic ; aucun
changement de version du config flow ni migration des identifiants n’est requis.
Les entrées Econiq ont un identifiant distinct `econiq:<préfixe MQTT>`.

1. Faire une sauvegarde complète HA et copier le dossier actuel hors de
   `custom_components`. Garder aussi la version précédente pour un retour arrière.
2. Dans HACS, retirer le téléchargement/dépôt d’origine pour qu’il ne gère plus
   `ventaxia_ha`. **Ne pas supprimer l’entrée Vent Axia de Paramètres > Appareils
   et services.** Retirer un téléchargement HACS peut effacer les fichiers ; ne
   pas redémarrer HA entre ce retrait et l’installation du fork.
3. Ajouter et télécharger le fork selon la section suivante. Ne pas tenter de
   gérer simultanément le même domaine avec les deux dépôts.
4. Contrôler qu’il n’existe qu’un dossier `/config/custom_components/ventaxia_ha`,
   sans dossier imbriqué et sans copie renommée chargée comme autre intégration.
5. Redémarrer HA, vérifier que les entrées Kinetic et leurs entités sont conservées.
   Comparer leurs identifiants et les automatisations avec la sauvegarde.

En cas de conflit HACS « domaine déjà utilisé », vérifier d’abord que le
référencement original a bien été retiré. Ne pas supprimer une entrée HA pour
résoudre un conflit de dépôt HACS. Pour revenir en arrière : arrêter HA,
restaurer le dossier précédent et son référencement HACS, puis redémarrer.

## 3. Ajouter le fork et configurer Econiq

1. Ouvrir HACS > menu ⋮ > Dépôts personnalisés.
2. Saisir `https://github.com/dyland98/ventaxia_ha`.
3. Sélectionner le type **Intégration**, puis Ajouter.
4. Chercher **Vent Axia MVHR (dyland98 fork)**, ouvrir le résultat et Télécharger.
   Choisir la release publiée `v0.3.1` (la branche par défaut peut contenir du code
   non publié ; ne pas la confondre avec une version stable).
5. Vérifier `/config/custom_components/ventaxia_ha/manifest.json` : domaine
   `ventaxia_ha`, documentation `dyland98`, version `0.3.1`.
6. Redémarrer Home Assistant.
7. Paramètres > Appareils et services > Ajouter une intégration > **Vent Axia** >
   **Sentinel Econiq**. Pour une nouvelle installation Kinetic, choisir Kinetic.
8. Saisir l’hôte de la VMC, port `8883`, identité `zirconia`, PSK privée hexadécimale,
   préfixe MQTT explicitement observé. Il ne s’agit pas du SSID Wi-Fi.
   Aucune adresse, clé, numéro de série ou préfixe de votre appareil n’est imposé.
9. La validation établit TLS 1.2 / `PSK-AES128-CBC-SHA`, MQTT 3.1.1, s’abonne
  au préfixe et attend un topic de télémétrie reconnu. Les métadonnées modèle/
  numéro de série sont utilisées si la VMC les publie, mais ne sont pas requises.
   publication de commande n’est nécessaire. Une erreur peut provenir du réseau,
  de la PSK ou d’un refus d’abonnement. Si TLS et l’abonnement MQTT réussissent
  mais qu’aucune télémétrie reconnue n’arrive sous 30 s, vérifier le préfixe et
  les topics publiés par la VMC.
10. Vérifier le regroupement des capteurs et boutons sous un même appareil.

Installation manuelle équivalente : arrêter HA, copier **le dossier complet**
`custom_components/ventaxia_ha` dans `/config/custom_components/ventaxia_ha`, puis
redémarrer. Installer ensuite par HACS si l’on souhaite son suivi des mises à jour.

## 4. Validation réelle à effectuer

Les fonctions complémentaires (profils, compteurs, dates, bypass, antigel, zones,
sondes et annulation sélectionnée) sont détaillées dans [ECONIQ_APK.md](ECONIQ_APK.md).
Les compteurs restent en lecture seule, conformément au choix de l’utilisateur.


Les tests automatisés utilisent un transport simulé, sans accès à la VMC.
L’utilisateur rapporte désormais que l’intégration de base fonctionne sur son
appareil. Les nouveaux contrôles et conversions décrits dans `ECONIQ_APK.md`
restent à installer et tester. Cela ne constitue pas une validation HACS par l’agent.

- Fermer complètement l’application mobile. Observer T1–T4, ERH/IRH, RPM, puissance
  et RSSI pendant plusieurs minutes. Comparer les données à une lecture de référence.
- Vérifier qu’un message partiel n’efface pas les autres capteurs, que `nan`/`inf`
  deviennent inconnus et qu’aucune valeur absente n’est changée en zéro.
- Les mesures `fm` sont en L/s et les durées moteur `dr` sont affichées en heures,
  selon les conversions retrouvées dans l’APK. `fd`, `pa`, `lr` restent sans unité
  supposée. Les sondes T1–T4 ont les noms retrouvés dans l’APK. `trem` reste brut.
  Le masque `6144` correspond aux alertes W-12 et W-13 confirmées par l’utilisateur,
  jamais à un nombre d’avertissements.
- Choisir **Mode de la dérogation**, **Durée de la dérogation**, puis **Appliquer
  la dérogation**. Vérifier les messages `vent/caf`, `vent/cor` et les RPM.
  Les choix sont restaurés sans commande au redémarrage. Maximum peut réagir
  physiquement sans que le mode publié change : distinguer demande et état confirmé.
- Tester **Annuler la dérogation sélectionnée** et observer l’état et les ventilateurs.
  Le retrait de « à valider » du nom ne constitue pas un test matériel.
- Les six anciens boutons Boost/15 min sont supprimés automatiquement du registre
  en 0.3.1. Adapter les automatisations qui les utilisaient ; les sélecteurs et
  l’identifiant du bouton d’annulation sélectionnée sont conservés.
  Voir [le guide des commandes et les constats APK](ECONIQ_APK.md).
- Couper temporairement l’accès réseau VMC : les entités doivent devenir
  indisponibles après détection de la rupture MQTT (keepalive 60 s). Restaurer le
  réseau, vérifier la reconnexion avec temporisation et la réception de données.
- Redémarrer HA puis la VMC séparément. Vérifier la reprise sans app mobile, sans
  commande Boost automatique et avec les mêmes identifiants d’entités.
- Décharger/recharger l’entrée, vérifier l’absence de tâches MQTT restantes.
- Télécharger les diagnostics et vérifier l’absence de PSK ; ne pas publier les
  fichiers `.storage` ou les sauvegardes HA contenant la clé.
- Refaire un cycle HACS avec une **version ultérieure réellement publiée** pour
  valider le téléchargement, le redémarrage et la conservation des entrées.

## 5. Recevoir les prochaines mises à jour

Pour chaque version, incrémenter manifeste et pyproject, exécuter les contrôles,
pousser les changements validés vers le `main` du fork puis pousser explicitement
le tag correspondant. Une
modification locale ou un simple push de branche ne crée aucune release stable.
HACS doit conserver uniquement `dyland98/ventaxia_ha` pour ce domaine. Actualiser
les informations du dépôt dans HACS, installer la mise à jour proposée, puis
redémarrer HA et vérifier les états. Contrôler que la page ouverte dans HACS et
les liens de release pointent toujours vers `dyland98`.

Références : [structure d’intégration HACS](https://www.hacs.dev/docs/publish/integration/),
[métadonnées HACS](https://hacs.dev/docs/publish/start/),
[API TLS-PSK Python](https://docs.python.org/3.13/library/ssl.html#ssl.SSLContext.set_psk_client_callback),
[API aiomqtt](https://aiomqtt.bo3hm.com/developer-interface).
