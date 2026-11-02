Dans les résultats, choisissez les dates et un affichage par jour/mois/année. Les sommes mensuelles et annuelles couvrent les jours sélectionnés. Le tableau par couche suit les dates ; les totaux et le téléchargement couvrent toute la simulation.

### Modifier le profil

Cliquez sur une cellule du tableau pour sélectionner sa couche ; la ligne bleue est active. Déplacez, supprimez ou modifiez-la ci-dessous. Importez les précipitations en CSV/Excel ou collez du CSV, puis vérifiez les colonnes, les unités et l’aperçu.

« Méthodes de calcul et végétation » propose les modules optionnels CN, Penman modifié, drainage permanent et contact Giroud. Les descriptions anciennes ci-dessous concernent les modes compatibles d’origine. Voir `docs/V22_METHODS.md` pour le périmètre des formules.

Ajoutez une couche du type souhaité, puis sélectionnez-la pour la déplacer, la supprimer ou modifier ses paramètres. Chaque couche possède ses propres valeurs. Un changement de type réinitialise les paramètres de la couche. Cliquez sur « Enregistrer la couche » avant de lancer la simulation. Les paramètres généraux doivent également être enregistrés.

Le sélecteur « Langue » permet de changer de langue sans modifier le profil enregistré. Les lanceurs Start_UI_ZH.cmd, Start_UI_FR.cmd et Start_UI_EN.cmd choisissent la langue initiale.

L’ordre du tableau est celui des couches, du haut vers le bas. Le réordonnancement conserve les identifiants ; supprimer la cible de recirculation désactive cette fonction. L’importation et l’exportation JSON se trouvent dans la barre latérale. Les clés JSON et CSV restent identiques dans les trois langues pour faciliter la réutilisation des fichiers.

### Paramètres et unités

Épaisseur : mm. Conductivité : mm/j. Distance de drainage : m. Porosité, capacité au champ, point de flétrissement et teneur en eau initiale : fractions volumiques de 0 à 1. La condition est : point de flétrissement < capacité au champ < porosité. La membrane ne stocke pas d’eau ; ses paramètres de teneur en eau ne s’appliquent donc pas.

La météo CSV doit contenir date,precip_mm,temp_c,pet_mm, avec des dates quotidiennes consécutives. L’évapotranspiration potentielle est fournie par l’utilisateur. Les données synthétiques incluses servent uniquement à la démonstration.

### Lire les résultats

Les valeurs en mm représentent une lame d’eau sur toute la superficie du site. Sur 1 hectare, 1 mm correspond à 10 m³. Les identifiants permettent de distinguer le drainage de couverture, la collecte du lixiviat et la détection des fuites.

bottom_leakage est le débit franchissant la base du profil ; sans revêtement inférieur, il s’agit du drainage libre. liner_leakage est un autre nom du même résultat : ne pas les additionner. Les écoulements à travers une membrane intermédiaire sont des transferts internes, pas des sorties supplémentaires du système.

La recirculation est injectée le lendemain ; l’eau en attente reste comprise dans le stockage. L’excédent refusé par une couche pleine est compté comme sortie de surface. Le bilan journalier comprend les stocks poreux, la neige et l’eau en attente de recirculation.

### Méthodes et limites

Ce programme indépendant utilise des approximations : CN fixe, fonte par degrés-jours, évapotranspiration limitée par l’eau disponible, charge locale simplifiée, drainage de type Darcy et limitation empirique des fuites de membrane. Il ne reproduit pas toutes les équations d’EPA HELP et n’a pas été validé par rapport aux résultats officiels ou aux mesures de terrain. La fermeture du bilan ne prouve pas la précision des prévisions.

Le gel du sol, la croissance végétale, les défauts de membrane et le contact membrane-sol ne sont pas simulés. La disposition libre des couches ne garantit ni une conception physique appropriée ni la conformité aux règles d’EPA HELP. Les résultats dépendent également du nombre de sous-pas et du découpage des couches. Voir README_fr.md et TECHNICAL_NOTES.md pour les détails.
