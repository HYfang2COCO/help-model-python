# HELP — Bilan hydrique multicouche, v2.3.1

Les graphiques proposent les dates de début et de fin, toute la période, les 30/90/365 derniers jours et un affichage par jour/mois/année. Les deux dates sont incluses ; les raccourcis se terminent au dernier jour simulé. Les totaux mensuels et annuels additionnent seulement les jours sélectionnés, sans extrapoler les périodes incomplètes. Le tableau quotidien suit la période ; les totaux et le ZIP conservent la simulation complète. Le choix est conservé au changement de langue et réinitialisé après une nouvelle simulation.

Le dossier contient maintenant une interface principale HTML complète : **`index.html`**. Elle permet de sélectionner les couches, les ajouter/supprimer/déplacer, modifier les paramètres, importer/exporter JSON, importer CSV/TSV ou coller la météo, simuler et télécharger les résultats.

**Décompressez tout le ZIP puis lancez `Start_Web.cmd`.** Python 3.10+ est nécessaire ; seule sa bibliothèque standard est utilisée, sans installation de Streamlit. Le navigateur s’ouvre automatiquement. La langue initiale est **English**, puis **Français**, puis **中文** dans le sélecteur ; les choix suivants sont mémorisés par l’interface web.

Ouvrir directement `index.html` permet l’édition hors ligne, l’aperçu météo et l’export JSON. Pour calculer, utilisez la page locale ouverte par `Start_Web.cmd`. Toutes les ressources sont fournies ; conservez le dossier `web/` à côté de `index.html`. Excel peut être enregistré en CSV ou importé via l’interface Streamlit conservée.

L’aide web est trilingue. Le workflow et les contrôles sont décrits dans `docs/WEB_GUIDE.md` (chinois) et `docs/WEB_TEST_REPORT.md`. L’interface Streamlit reste optionnelle et utilise le même moteur Python et les mêmes formules v2.2. Ses instructions suivent.

Cliquez sur une cellule pour sélectionner sa couche, puis déplacez, supprimez ou modifiez-la. L’importation accepte CSV/TSV/XLSX, le choix de feuille et de colonnes, les unités, un aperçu et du CSV collé. Les précipitations seules utilisent des constantes de température/ETP explicitement affichées. Penman modifié nécessite le rayonnement, l’humidité et le vent à 2 m.

Les méthodes optionnelles ajoutent le CN corrigé quotidiennement, l’ETP de Penman modifiée, les équations HELP de drainage permanent et les formules de défauts de Giroud pour bon/mauvais contact. La répartition de l’ET réelle selon un LAI saisonnier reste approximative. Ces modules ne constituent pas une reproduction complète d’EPA HELP. Conditions et sources : `docs/V22_METHODS.md` (chinois).

L’interface est disponible en chinois, français et anglais. Choisissez la langue dans la barre latérale ou utilisez `Start_UI_ZH.cmd`, `Start_UI_FR.cmd` ou `Start_UI_EN.cmd`. Le petit sous-titre et l’avis jaune placés auparavant sous le titre ont été retirés. Les méthodes restent décrites dans l’onglet d’aide et les documents techniques.

## Démarrage

Python 3.10 ou une version ultérieure est requis. Sous Windows, double-cliquez sur le lanceur de votre langue. Au premier démarrage, un environnement virtuel est créé dans le projet et Streamlit est installé depuis PyPI. Vous pouvez aussi exécuter :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-ui.txt
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

## Configuration et simulation

1. Chargez l’un des cinq profils d’exemple ou importez un fichier JSON.
2. Ajoutez des couches de sol, déchets, drainage, barrière en sol ou géomembrane. Sélectionnez une couche pour la modifier, la déplacer ou la supprimer.
3. Définissez l’épaisseur, la conductivité et les paramètres de stockage ou de drainage applicables. Enregistrez la couche.
4. Enregistrez les paramètres généraux et la cible de recirculation. Les identifiants restent stables lors du réordonnancement.
5. Importez une météo quotidienne consécutive (`date,precip_mm,temp_c,pet_mm`) ou utilisez les deux années synthétiques fournies.
6. Lancez la simulation et téléchargez les résultats ZIP.

Changer de langue conserve la configuration enregistrée et les résultats précédents. Enregistrez les modifications du formulaire avant de changer de langue. Les clés JSON/CSV, identifiants et noms saisis restent inchangés pour assurer la compatibilité des fichiers.

## Résultats

Le ZIP contient la configuration et la météo utilisées, les bilans quotidiens/mensuels/annuels, les flux et stocks par couche, ainsi qu’un résumé. Les quantités d’eau sont des lames d’eau sur la superficie du site. `m³ = mm × area_m2 / 1000`.

Chaque couche drainante contribue indépendamment à la collecte. Le flux à travers un revêtement intermédiaire est un transfert interne ; seul le flux franchissant la base est une sortie inférieure du système. `liner_leakage_mm` est un alias de `bottom_leakage_mm`, et non une sortie supplémentaire. L’eau en attente de recirculation reste dans le stockage.

Bilan journalier : stockage initial + précipitation = stockage final + ruissellement + ET + collecte nette + sortie à la base. Le bilan de chaque couche est également vérifié. Un résidu supérieur à 1e-7 mm arrête le calcul.

## Méthodes

Il s’agit d’un modèle de recherche approximatif indépendant, dérivé du MVP Python initial. Son équivalence à EPA HELP et sa précision par rapport aux mesures de terrain n’ont pas été validées. Il utilise un CN fixe, une fonte par degrés-jours, une ETP externe, des réservoirs de stockage, une charge locale simplifiée, un drainage de type Darcy et une limitation empirique des fuites de membrane. Un bilan fermé ne prouve pas la précision physique. Les défauts de membrane, le contact membrane-sol, le gel du sol et la croissance végétale ne sont pas résolus.

Consultez `docs/UI_GUIDE_fr.md`, `TECHNICAL_NOTES.md` et `docs/TEST_REPORT.md`. Les notes techniques détaillées et le rapport de tests sont en chinois. Le dossier `legacy/` conserve le code et les documents d’origine.

Les cinq profils illustrent le drainage sans revêtement, un revêtement composite inférieur, un double revêtement, des drainages de couverture et de base distincts et la recirculation. Les paramètres et la météo ne sont pas des mesures de site. `examples/config.schema.json` décrit le format JSON commun.

Les deux axes sont nommés. L’axe X indique la date, le mois ou l’année ; l’axe Y indique la variable et son unité : mm/day pour les valeurs quotidiennes, mm pour les totaux mensuels/annuels.
