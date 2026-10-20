# Validation des fonctions complémentaires — 2026-10-20

Implémentation sur le `main` local du fork. **123 tests automatisés passent**
avec transport simulé, réseau bloqué et sockets Unix autorisées pour asyncio.
Les vérifications Black, isort, flake8, JSON, cohérence de version/packaging et
`git diff --check` passent également.

L’extension couvre :

- annulation explicite du mode sélectionné, y compris Maximum, sans état optimiste ;
- profils reçus, noms et consignes ; abonnement explicite aux topics de lecture ;
- compteur total, types de filtres, intervalles, dates et échéances calendaires ;
- états et paramètres reçus du bypass et de la protection antigel ;
- création des zones 1–15 et sondes 1–31 à réception de mesures reconnues ;
- métadonnées de canaux et listes actives avec leurs deux dispositions de bits ;
- données absentes/non finies, bornes des canaux, refus des topics d’écriture ;
- restauration des identifiants après rechargement et nettoyage des callbacks ;
- dérogation restante calculée exclusivement à partir de l’horloge de la VMC ;
- conservation de la connexion de base si les abonnements facultatifs sont refusés ;
- diagnostics enrichis sans PSK ni noms personnalisés des sondes.

L’utilisateur a confirmé que les compteurs doivent rester en **lecture seule**.
Aucun reset, calibration, paramètre d’installation ou contrôle de firmware n’a
été ajouté. Aucune commande réelle, aucun déploiement HA, commit, push, tag ou
release n’a été effectué pour cette extension. Les nouveaux topics, leurs valeurs
sur ce firmware et les annulations doivent encore être validés sur l’appareil.

La présence d’un topic dans l’APK ne prouve pas sa publication par la VMC. Les
capteurs restent inconnus quand leurs données ne sont pas reçues. Les fonctions
et essais manuels sont décrits dans [ECONIQ_APK.md](ECONIQ_APK.md).

---

# Validation des sélecteurs et libellés — 2026-10-20

Travail actuel dans le `main` local du fork `dyland98/ventaxia_ha`.
Le retour utilisateur indique que l’intégration de base fonctionne et que Maximum
accélère physiquement les ventilateurs, même si l’app garde le mode précédent.
Les messages W-12/W-13 ont été corrélés avec le masque 6144 fourni précédemment.
Cela ne constitue pas une validation de la nouvelle version sur HA/VMC par l’agent.

**80 tests automatisés passent**, avec réseau bloqué et transport MQTT simulé,
sous Home Assistant 2026.10.0 / Python 3.14.4. Les tests exercent notamment :

- restauration des deux sélecteurs et absence de commande automatique ;
- sélection du mode/de la durée sans publication, puis application explicite ;
- six durées exactes et publication QoS 0 / retain false ;
- conservation du mode confirmé tant que la télémétrie n’a pas changé ;
- modes, régulation et qualité d’air traduits, codes inconnus conservés ;
- W-12/W-13 séparés, combinaison 6144, autres bits et données absentes ;
- débits L/s, compteur moteur secondes → heures, valeurs brutes préservées ;
- installation/décharge des plateformes HA et ancien backend Kinetic.

Commandes réussies :

```sh
.venv/bin/pytest --disable-socket --allow-unix-socket tests
.venv/bin/black --check custom_components scripts tests
.venv/bin/isort --check-only --profile black custom_components scripts tests
.venv/bin/flake8 custom_components scripts tests
.venv/bin/python scripts/check_release.py --tag v0.3.0
git diff --check
```

Les catalogues JSON se chargent correctement. Aucun nouveau commit, push, tag,
release ou déploiement HA n’est effectué pendant cette modification. Les fichiers
APK et sources décompilées sont restés hors Git. Les contrôles HACS/Hassfest sur
GitHub et les nouveaux contrôles sur la VMC ne sont pas validés par ce banc local.

Voir [les preuves APK, les instructions et l’inventaire restant](ECONIQ_APK.md).

---

# Validation initiale — historique du 2026-10-20

Working tree: `feat/econiq-hacs`; candidate version `0.3.0`.
Remote `origin`: `https://github.com/dyland98/ventaxia_ha.git`; no `upstream`.
No commit, push, tag, GitHub release, Home Assistant deployment or device command
was made. No second repository was cloned.

Environment: macOS, Python 3.14.4, OpenSSL 3.0.19, Home Assistant 2026.10.0,
aiomqtt 2.5.1, ventaxiaiot 0.1.12. Native `ssl.HAS_PSK` and
`SSLContext.set_psk_client_callback` are available **locally**. The installed
ventaxiaiot source was inspected: its Kinetic client encodes its Wi-Fi key as
UTF-8 and uses a separate message processor/command API. Econiq instead decodes
hex bytes and uses MQTT; the two transports are not shared.

Passed commands:

```sh
.venv/bin/pytest --disable-socket --allow-unix-socket tests
.venv/bin/black --check custom_components scripts tests
.venv/bin/isort --check-only --profile black custom_components scripts tests
.venv/bin/flake8 custom_components scripts tests
.venv/bin/python scripts/check_release.py --tag v0.3.0
git diff --check
```

Results: **29 tests passed**. JSON and GitHub YAML parsed successfully.
The release check rejected an intentionally mismatched `v9.9.9` tag.
Unix sockets are allowed only for asyncio's internal wakeup mechanism; network
sockets remain blocked and all MQTT clients in these tests are simulated.

Tests cover hexadecimal decoding, native TLS context settings, invalid keys and
prefixes, model selection, duplicate entries, configuration failures, metadata
validation, partial cache updates, malformed/nonfinite payloads, raw warning
values, exact Boost/cancel publications with QoS 0 and retain false, no optimistic
mode confirmation, disconnect availability, reconnect/stable client ID, shutdown,
HA entity registration, push updates, unload/listener cleanup, redacted diagnostics
and selection of the existing Kinetic backend for entries without `device_type`.

Limits: HACS/Hassfest actions are prepared but have not run on GitHub. GitHub
Actions/Issues settings and public accessibility of the fork were not verified
(the web reader could not retrieve the fork). The config-flow tests mock the
frontend dependency, and the platform integration test mocks global setup;
these tests do not validate the bundled Lovelace card or a full HA installation.
Kinetic hardware behavior has not been regression-tested. The actual Proxmox HA
runtime, physical Econiq telemetry, Boost/cancellation, reboot/reconnect behavior,
HACS installation and subsequent HACS update have **not** been tested.

Follow [the French installation and hardware-validation procedure](HACS_FR.md)
to complete those checks before claiming device or HACS validation.
