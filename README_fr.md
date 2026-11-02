# HELP — Bilan hydrique des décharges

[English](README_en.md) · [Français](README_fr.md) · [Présentation bilingue](README.md)

### Présentation

Un modèle Python indépendant inspiré du fonctionnement de **HELP (Hydrologic Evaluation of Landfill Performance)**. Il simule quotidiennement le stockage et les transferts d’eau dans un profil de décharge configurable, avec une interface web locale en **anglais, français et chinois**.

### Téléchargement et démarrage

**[Télécharger l’application complète au format ZIP](HELP_Model_Python_v2_3_2.zip)**

1. Installez **Python 3.10 ou une version ultérieure**.
2. Téléchargez le ZIP ci-dessus et décompressez **tout** son contenu.
3. Sous Windows, double-cliquez sur `Start_Web.cmd` dans le dossier du projet décompressé.
4. L’interface web locale s’ouvre dans votre navigateur. La langue initiale est l’anglais ; le sélecteur **Langue** permet de choisir le français ou le chinois.

L’interface web fournie et le moteur de calcul utilisent la bibliothèque standard de Python ; Streamlit est facultatif. Sur les autres systèmes, exécutez cette commande depuis le dossier du projet décompressé :

```bash
python web_server.py --open
```

Utilisez le ZIP complet pour obtenir une installation exécutable. Il conserve les dossiers nécessaires `web/`, `examples/`, `docs/` et `tests/`. Les fichiers séparés actuellement visibles dans ce dépôt ont été téléversés sans cette arborescence. L’ouverture directe de `index.html` permet l’édition et les aperçus ; les calculs nécessitent le serveur Python local.

### Fonctionnalités

- Sélection d’une couche par un clic, puis ajout, modification, déplacement vers le haut/bas ou suppression.
- Configuration de couches de sol, de déchets, de drainage, de barrière en sol et de géomembrane, avec identifiants stables et champs adaptés à chaque type.
- Réglage de l’épaisseur, de la conductivité hydraulique et, selon le type, de la porosité, de la capacité au champ, du point de flétrissement, de l’humidité initiale et des paramètres de drainage.
- Importation/exportation de profils JSON ; importation météo CSV/TSV ou collage de précipitations. L’interface Streamlit facultative accepte aussi les fichiers Excel.
- Suivi du ruissellement, de l’évapotranspiration, du stockage par couche, des transferts verticaux, de la collecte indépendante des drainages, de la recirculation et de la sortie à la base.
- Choix des dates de début/fin et d’un affichage journalier, mensuel ou annuel, avec noms des axes et unités.
- Exportation des bilans, des résultats par couche, des données d’entrée et de la configuration.

### Données d’entrée et résultats

Les données météo quotidiennes utilisent `date,precip_mm,temp_c,pet_mm`, avec des dates ISO consécutives (`YYYY-MM-DD`). L’interface facilite la correspondance des colonnes et des unités. Des données limitées aux précipitations nécessitent des hypothèses explicites pour la température et l’évapotranspiration potentielle manquantes.

Les quantités d’eau sont exprimées en lame d’eau équivalente sur la superficie du site, en millimètres. Les flux journaliers sont affichés en **mm/jour** ; les cumuls mensuels et annuels sont en **mm**. Les vues mensuelles/annuelles additionnent les quantités des jours sélectionnés : leurs valeurs et leurs échelles verticales automatiques diffèrent donc de la vue journalière. Les périodes incomplètes comprennent uniquement les jours sélectionnés.

Conversion en volume : `m³ = mm × area_m2 / 1000`.

Le moteur vérifie le bilan quotidien du système et celui de chaque couche. L’eau en attente de recirculation le lendemain reste incluse dans le stockage.

### Méthodes et portée

Les options comprennent le ruissellement par Curve Number SCS, un CN ajusté à l’humidité, l’évapotranspiration potentielle de Penman modifiée, un écoulement non saturé simplifié, le drainage latéral et des formules de fuite par défauts de géomembrane. Les hypothèses et les données nécessaires figurent dans [les notes méthodologiques](V22_METHODS.md).

**Il s’agit d’une approximation indépendante, et non du logiciel officiel EPA HELP.** L’équivalence numérique complète à EPA HELP et la précision par rapport aux mesures de terrain n’ont pas été établies. Un bilan hydrique fermé vérifie la cohérence comptable, pas la précision prédictive. Les profils et les données météo d’exemple sont synthétiques et illustratifs.

### Documentation et vérifications

- [Guide de l’interface en français](UI_GUIDE_fr.md)
- [Guide de l’interface en anglais](UI_GUIDE_en.md)
- [Guide web](WEB_GUIDE.md) et [détails méthodologiques](V22_METHODS.md) — les notes détaillées sont en chinois.
- Le ZIP contient d’autres documents, des modèles JSON, des profils d’exemple et les tests.

Depuis le **dossier du projet décompressé**, exécutez :

```bash
python -m unittest discover -s tests -v
node --test tests/test_time_series.cjs
```

Node.js sert uniquement aux vérifications JavaScript. Les contrôles Python facultatifs de l’interface et du schéma nécessitent les dépendances correspondantes.
