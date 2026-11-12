# Loc_ToolBox

La chaîne de production des localisations : récupérer les pointés d'un
serveur SeisComP, localiser avec **NonLinLoc (NLL)** sur son propre
ordinateur, installer un profil dans SeisComP et préparer la double
différence (scrtdd). L'analyse des résultats est dans un dépôt à part
(LocQuality_ToolBox, ci-dessous). Quatre usages :

1. **Créer un profil NLL pour une nouvelle région** à partir d'un modèle de
   vitesse 1D ou du modèle 3D (`creer_profil.py`).
2. **Localiser une période** avec un profil : pointés récupérés sur le
   serveur, grilles de temps calculées, NLLoc lancé en parallèle
   (`nll_run.py`).
3. **Préparer une relocalisation en double différence** avec scrtdd sur le
   serveur (`scrtdd_inputs.py`, `telecharger_formes_onde.py`).
4. **Installer un profil dans SeisComP** (scolv avec le plugin NonLinLoc,
   et scrtdd), avec les grilles calculées en local (`profil_vers_seiscomp.py`).

La qualité des localisations s'analyse ensuite avec le dépôt
[LocQuality_ToolBox](https://github.com/LuDesmeuzes/LocQuality_ToolBox), qui
lit directement les dossiers produits ici.

```
  modèle de vitesse ──► creer_profil.py ──► profil NLL ─┐
                                                        ├─► nll_run.py ──► run (.hyp, csv)
  serveur SeisComP ───► pointés (fdsnws) ───────────────┘        │
                                                                  ├─► LocQuality_ToolBox
                                                                  └─► scrtdd_inputs.py ──► scrtdd (serveur)
  profil NLL + runs ──► profil_vers_seiscomp.py ──► dossier à copier ──► scolv (SeisComP)
```

## Par où commencer

1. **Installer** les outils et NonLinLoc, puis faire le **premier essai sur
   le Jura** (sections [Installation](#installation) et
   [Premier essai](#premier-essai--le-jura-en-10-minutes), une dizaine de
   minutes).
2. **Comprendre ce que font les outils** : le PDF *Mise en place NLL sur
   SeisComP* (`docs/`) explique les concepts, les paramètres ligne par ligne
   et l'installation sur OAR. Les commandes, elles, sont dans ce README.
3. **Votre région** : choisir la zone, créer le profil, lancer un run
   ([Créer un profil](#créer-un-profil-pour-une-nouvelle-région),
   [Lancer un run](#lancer-un-run--nll_runpy)).
4. **Analyser la qualité** des localisations avec
   [LocQuality_ToolBox](https://github.com/LuDesmeuzes/LocQuality_ToolBox).
5. **Installer le profil sur OAR**, puis préparer **scrtdd**
   ([Installer un profil dans SeisComP](#installer-un-profil-dans-seiscomp--profil_vers_seiscomppy),
   [Relocaliser avec scrtdd](#relocaliser-avec-scrtdd-sur-le-serveur)).

## Prérequis

- macOS ou Linux, Python 3.9 ou plus récent, `git`, un compilateur C et
  `cmake` (pour NonLinLoc).
- Un accès au service web **fdsnws** du serveur SeisComP de la région
  (ex. `http://ist-scjura-sig.u-ga.fr:8080/fdsnws` pour le Jura). Les
  serveurs de l'ISTerre se consultent depuis le réseau de l'université ;
  ailleurs, passer par le VPN.
- Un accès à internet pour la topographie (données SRTM, téléchargées une
  fois).
- Pour le modèle 3D seulement : le fichier du modèle de Jean Virieux et
  Nouibat Ahmed (voir [Modèle 3D](#modèle-3d--découper-une-tuile)).

## Installation

### 1. Loc_ToolBox

```bash
git clone https://github.com/LuDesmeuzes/Loc_ToolBox.git
cd Loc_ToolBox
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/
```

`source .venv/bin/activate` est à refaire dans chaque nouveau terminal.
`pytest` vérifie l'installation : tous les tests doivent passer.

Le dépôt peut être placé n'importe où. Le travail (profils, runs, pointés)
va dans un **dossier de travail** à part, `racine`. Par défaut, c'est
`NonLinLoc_travail/` **à côté** du dépôt, créé au besoin. Il survit donc à
un nouveau clone du dépôt.

### 2. NonLinLoc

NonLinLoc (Anthony Lomax) se compile une fois, avec le script fourni :

```bash
python installer_nll.py
```

Il télécharge NonLinLoc, le compile (quelques minutes) et copie ses
programmes dans `<racine>/bin/`, où les scripts les trouvent sans rien
configurer. S'il manque un outil de compilation, il donne la commande pour
l'installer : `xcode-select --install` et `brew install cmake` sur Mac,
`sudo apt install build-essential cmake` sous Linux.

NonLinLoc déjà compilé ailleurs ? Les scripts cherchent `NLLoc`,
`Vel2Grid` et `Grid2Time`, qui doivent être **dans un même dossier**, dans
l'ordre suivant : `nll_bin` de `config.yaml`, `<racine>/bin/`,
`<racine>/outils/bin/`, puis le PATH.

### 3. Configuration (facultative)

Sans `config.yaml`, les scripts prennent `config.example.yaml`, et tout
fonctionne avec le dossier de travail par défaut. Pour le changer, ou pour
un autre réglage :

```bash
cp config.example.yaml config.yaml
```

puis modifier dans `config.yaml` :

| Clé | Contenu |
| --- | --- |
| `racine` | Dossier de travail (défaut : `NonLinLoc_travail/` à côté du dépôt) |
| `nll_bin` | Dossier des programmes NonLinLoc, s'ils ne sont ni dans `<racine>/bin/` ni dans le PATH |
| `paths.model_file` | Modèle 3D global (pour `--modele-3d` seulement) |

Les autres chemins (`run.profils_dir`, `run.runs_dir`, `fetch.cache_dir`…)
sont relatifs à `racine` et ont des valeurs par défaut : il n'y a pas à y
toucher. Un chemin absolu (`/…` ou `~/…`) est pris tel quel.
`config.example.yaml` documente chaque clé. `config.yaml` est propre à
chaque machine et n'est pas versionné.

Contenu du dossier de travail :

```
<racine>/
├── bin/                   NLLoc, Grid2Time, Vel2Grid (installer_nll.py)
├── donnees/pointes/       pointés téléchargés (cache)
├── profils/               un dossier par profil NLL
├── profils_travail/       une configuration par région
└── runs/                  un dossier par run
```

## Premier essai : le Jura en 10 minutes

L'exemple crée un profil 1D pour le Jura, puis localise les 25 séismes de
mars 2024. Il faut l'accès au serveur fdsnws du Jura. Depuis le dossier
`Loc_ToolBox`, environnement activé :

1. Créer le profil et la configuration de la région (≈ 15 s, topographie
   comprise) :

```bash
python creer_profil.py --region exemple_jura --nom exemple_jura_1D \
    --modele modeles_vitesse/jura.nd --lat 46.95 47.55 --lon 5.45 7.55 \
    --prof-max 50 --cellule 4 \
    --fdsnws http://ist-scjura-sig.u-ga.fr:8080/fdsnws
```

2. Localiser mars 2024 (≈ 1 min : 31 jours de pointés, 23 stations,
   NLLoc). Le plus simple est de copier la commande que l'étape 1 affiche
   sous « Étape suivante », avec le vrai chemin, en remplaçant les
   `AAAA-MM-JJ` par les dates. Écrite à la main, `<racine>` est le dossier
   de travail (par défaut `NonLinLoc_travail/`, à côté du dépôt) :

```bash
python nll_run.py --config <racine>/profils_travail/exemple_jura/config_exemple_jura.yaml \
    --profil exemple_jura_1D --debut 2024-03-01 --fin 2024-03-31 --grilles
```

À la fin, le run doit annoncer
« 25 localisés, 0 rejetés ». Les résultats sont dans
`<racine>/runs/exemple_jura_1D_20240301_20240331/` :

- `exemple_jura_1D_20240301_20240331.hyp` : les localisations au format
  NLLoc ;
- `evenements.csv` : un événement par ligne, avec l'origine du serveur pour
  comparer ;
- `phases.csv` : les résidus de chaque phase ;
- `run.yaml` : profil, période, paramètres et comptes.

Pour regarder ces résultats (carte, coupes, comparaison au serveur), passer
à LocQuality_ToolBox (`paths.nll_runs`).

## Créer un profil pour une nouvelle région

Un profil est un dossier de `profils/` qui contient tout ce dont NLL a
besoin pour une région : modèle de vitesse, grilles de temps, paramètres de
la recherche. Il porte le nom d'un profil NLL de SeisComP quand il en est
la copie.

### Choisir la zone sur une carte : `choisir_zone.html`

Le plus simple pour une nouvelle région est d'ouvrir `choisir_zone.html`
dans un navigateur (double-clic, ou `open choisir_zone.html` sur Mac,
`xdg-open choisir_zone.html` sous Linux ; internet nécessaire pour le fond
de carte). On y dessine un rectangle autour des séismes à localiser. On
choisit ensuite le modèle 1D ou 3D, le pas des grilles, la topographie, la
région et le serveur. La page affiche alors la commande `creer_profil.py`
complète, avec un nom de profil construit sur le modèle
`<pas>_<région>_<1D|3D>[_topo]`, et un bouton pour la copier.

La carte montre aussi la grille de recherche NLL qui sera créée (en
tirets : la zone et la marge, arrondies à 5 km). En 3D, elle montre la
tuile du modèle (en pointillés, à vérifier : elle doit couvrir les
stations) et estime la place disque des grilles de temps. La page ne
lance rien elle-même : c'est la commande copiée qui crée le profil.

### Avec un modèle 1D : `creer_profil.py`

```bash
python creer_profil.py --region <région> --nom <profil> --modele <fichier> \
    --lat <min> <max> --lon <min> <max> --fdsnws <adresse …/fdsnws>
```

Les options obligatoires :

| Option | Ce que c'est | Exemple |
| --- | --- | --- |
| `--region` | Nom court de la région. Il nomme la configuration de la région (`<regions_dir>/<région>/config_<région>.yaml`) et le cache des pointés (`par_jour_<région>`). Plusieurs profils peuvent partager une région : un 1D puis un 3D, ou deux modèles à comparer. La configuration existante est alors gardée, à condition que le serveur, la zone et les types d'événements soient les mêmes. | `jura` |
| `--nom` | Nom du profil. Il nomme le dossier `<profils_dir>/<profil>/`, c'est lui qu'on donne à `nll_run.py --profil`, et il apparaît dans le nom des runs (`<profil>_<début>_<fin>`). Quand le profil est la copie d'un profil NLL de SeisComP, reprendre le même nom. Sinon, l'usage est `<n°>_<région>_<1D ou 3D>[_topo]`. | `1_jura_1D_topo` |
| `--modele` | Modèle de vitesse 1D (formats ci-dessous). Pour un modèle 3D, voir `--modele-3d` plus bas. | `modeles_vitesse/jura.nd` |
| `--lat`, `--lon` | Zone des séismes à localiser, en degrés : latitudes min et max, longitudes min et max (est positif). Les pointés sont récupérés dans cette zone, et la grille de recherche la couvre, plus `--marge`. Les stations peuvent être en dehors. | `--lat 46.95 47.55 --lon 5.45 7.55` |
| `--fdsnws` | Adresse fdsnws du serveur SeisComP de la région, jusqu'à `/fdsnws` : le script y ajoute `/event/1/query` et `/station/1/query`. | `http://ist-scjura-sig.u-ga.fr:8080/fdsnws` |

Les noms de région et de profil sont limités aux lettres sans accent, aux chiffres, à `_` et à `-`, parce qu'ils servent de noms de dossiers et de fichiers. Toutes les options, avec leur valeur par défaut, s'affichent avec `python creer_profil.py --help`.

Modèles acceptés :

- **`.nd`** (format TauP) : « profondeur Vp Vs densité » par ligne ; une
  discontinuité = deux lignes à la même profondeur ; les lignes de texte
  (`mantle`…) sont ignorées. Entre deux profondeurs, la vitesse varie
  linéairement. Exemple : `modeles_vitesse/jura.nd`.
- **texte en couches** : « toit Vp Vs [densité] » par ligne, en km et km/s,
  vitesses constantes dans chaque couche, commentaires après `#`.
  Exemples : `modeles_vitesse/alpes_labo.txt`, `modeles_vitesse/alpes_paul2001.txt`,
  `modeles_vitesse/auvergne_40km.txt`.

Profondeurs en km sous le niveau de la mer. La première couche est
prolongée jusqu'à −5 km pour couvrir le relief.

Le script choisit lui-même les paramètres, en suivant les profils de
l'Ubaye, du Mont-Blanc, d'Ambert et du Jura :

| Paramètre NLL | Choix | Option |
| --- | --- | --- |
| `TRANS` (centre de la projection) | milieu de la zone | — |
| `LOCGRID` (grille de recherche, pas de 1 km) | la zone + 10 km de chaque côté, arrondie à 5 km ; de −5 km à 30 km | `--marge`, `--prof-max` |
| `LOCSEARCH OCT` (recherche octree) | cellules initiales d'environ 3 km ; nœuds = 5 × cellules initiales, au moins 50 000 | `--cellule` |
| `VGGRID` (grilles de temps 2D) | pas de 1 km, sur 400 km, de −5 à max(60, prof. max + 10) km | `--pas`, `--distance-max` |
| `LOCTOPO_SURFACE` (topographie) | relief SRTM sur l'emprise de la recherche | `--sans-topo` |
| Types d'événements récupérés | `earthquake` (sans les tirs de carrière) | `--types` |

Deux réglages sont à choisir selon la région :

- **`--prof-max`** : profondeur maximale de la recherche. La prendre un peu
  au-delà des séismes les plus profonds du catalogue de la région (le Jura
  en a jusqu'à 54 km : `--prof-max 50` aurait pu être 60).
- **`--cellule`** : taille des cellules de départ de la recherche. NLL ne
  teste pas toutes les positions : il découpe le volume de recherche en
  cellules de `--cellule` km, calcule la probabilité au centre de chacune,
  puis coupe en 8 la plus probable, et recommence jusqu'à épuiser son budget
  de nœuds (5e nombre de `LOCSEARCH OCT`). Des cellules trop grandes
  balayent grossièrement et peuvent rater la bonne zone ; trop petites, elles
  consomment le budget au départ, et il en reste moins pour affiner (le
  script fixe le budget à 5 fois le nombre de cellules de départ : des
  cellules plus petites rendent donc chaque localisation plus lente).
  Garder 3 km ; passer à 4 ou 5 km si la zone dépasse 100 km de côté. Jura
  (180 × 90 × 55 km) : 34 200 cellules de départ à 3 km, 14 490 à 4 km,
  soit un budget de 171 000 au lieu de 75 000 nœuds (calcul environ 2,3 fois
  plus long à 3 km, estimé d'après le nombre de nœuds).

Le script écrit :

- **`<profils_dir>/<profil>/`** : `NLL.<profil>.conf` (paramètres de
  localisation), `nll_<profil>.in` (grilles de temps, lu par
  `nll_run.py --grilles`), `vel2grid_P.in` et `vel2grid_S.in`, `model/`
  (modèle NLL, calculé par Vel2Grid), `topo.asc`, un `README.txt` qui
  résume les choix, et `time/` (vide : les grilles de temps sont calculées
  au premier run, pour les seules stations pointées) ;
- **`<regions_dir>/<région>/config_<région>.yaml`** : la configuration de la
  région (serveur fdsnws, zone, dossiers des pointés), à passer en
  `--config` à `fetch_picks.py`, `nll_run.py` et `scrtdd_inputs.py`.

Il refuse d'écraser un profil existant, ou une région existante d'un autre serveur ou d'une autre zone (`--force` pour le
faire). Vérification : recréé avec ce script, le profil `1_jura_1D_topo`
fait à la main donne exactement les mêmes localisations.

### Avec le modèle 3D : `creer_profil.py --modele-3d`

Le même script crée un profil 3D à partir du modèle de Jean Virieux et
Nouibat Ahmed (voir [Modèle 3D](#modèle-3d--découper-une-tuile) pour se le
procurer). `--modele-3d` sans valeur prend `paths.model_file` de
`config.yaml` :

```bash
python creer_profil.py --region montblanc --nom 1_montblanc_3D_topo --modele-3d \
    --lat 45.72 45.95 --lon 6.70 7.03 --pas 1 \
    --fdsnws http://ist-sc3-sig.u-ga.fr:8080/fdsnws
```

Le script découpe une **tuile** du modèle autour de la zone, la convertit au
format NLL avec `segment_from_zones.py` et `nll_pipeline.py` (réglages des
sections `segment` et `pipeline` de `config.yaml`), génère la topographie
sur la tuile et écrit le profil (grilles de temps en `GRID3D`). Le centre de
la projection est celui de la tuile. Trois points diffèrent du 1D :

- **La tuile doit couvrir les stations**, pas seulement les séismes : une
  station hors du modèle n'a pas de grille de temps, et ses phases sont
  perdues. Par défaut, la tuile déborde de 80 km autour de la zone
  (`--marge-tuile`) ; `--tuile-lat` / `--tuile-lon` l'imposent. Au
  Mont-Blanc, avec une tuile de ±99 km, 71 stations restaient hors du
  modèle (1 010 phases sur 155 219).
- **La place disque** : une grille 3D complète par station et par phase. Le
  script affiche l'estimation : sur une tuile de 200 km, ≈ 20 Mo par
  station et par phase au pas de 1 km, ≈ 157 Mo au pas de 0,5 km
  (Mont-Blanc : `time/` = 5 Go au pas de 1 km, 40 Go au pas de 0,5 km).
  Commencer au pas de 1 km.
- **Le modèle ne couvre qu'une région** : le script s'arrête si la tuile en
  sort, ou si la grille de recherche dépasse le modèle obtenu.

Vérification : recréé avec ce script (`--tuile-lat 44.94 46.73 --tuile-lon
5.59 8.14 --pas 0.5 --marge 37 --cellule 3.34`), le profil
`05_montblanc_3D_topo` fait à la main donne le même modèle NLL.

Pour un profil écrit à la main (autre modèle 3D, réglages particuliers),
prendre exemple sur un profil existant : `nll_<profil>.in` (`TRANS`,
`GTFILES <modèle> <grilles> P`, `GTMODE GRID3D`, `GT_PLFD` ; `${NLLROOT}` =
`run.profils_dir` ; deux profils peuvent partager les mêmes grilles en
pointant `GTFILES` vers le même dossier) et `NLL.<profil>.conf` (même
`TRANS`, `LOCGRID`, `LOCSEARCH`, `LOCMETH`…, `LOCTOPO_SURFACE`).

## Lancer un run : `nll_run.py`

`nll_run.py` localise avec NLL en ligne de commande les événements d'une
période, avec un profil, sans passer par le serveur :

```bash
python nll_run.py --config <config de la région> --profil <profil> \
    --debut 2024-11-01 --fin 2024-11-30 --grilles
python nll_run.py --config <config> --profil <profil> --debut … --fin … \
    --nom <profil>_oct15 --locsearch "OCT 15 15 15 0.001 50000 5000 0 1"
```

1. Les pointés de la période sont récupérés par `fetch_picks.py`
   (ci-dessous), avec un cache par jour.
2. Le fichier de contrôle reprend `<profils_dir>/<profil>/NLL.<profil>.conf`
   (`TRANS`, `LOCGRID`, `LOCSEARCH`, `LOCMETH`, `LOCTOPO_SURFACE`…), avec les
   grilles de temps de `<profil>/time/`. `${NLLROOT}` est remplacé par
   `run.profils_dir`. `--locsearch` remplace `LOCSEARCH` pour un test.
3. **`--grilles`** calcule d'abord les grilles de temps manquantes
   (Grid2Time), pour les seules stations pointées sur la période, en P et en
   S même si une seule des deux phases y est pointée (scrtdd peut avoir
   besoin de l'autre). Les lignes `TRANS`, `GTFILES`, `GTMODE` et `GT_PLFD`
   sont lues dans `<profil>/nll_<profil>.in`. Les positions des stations
   viennent de l'inventaire du serveur (`fetch.fdsnws_station_url`), valides
   sur la période. Compter environ 2 s par station et par phase pour une
   grille 3D au pas de 0,5 km (157 Mo par grille, angles compris), moins
   d'une seconde en 1D.
4. `NLLoc` tourne en parallèle sur `--jobs` morceaux de la période (par
   défaut, nombre de cœurs − 1) : environ 2 minutes pour 3000 événements.
5. Le run est écrit dans `<runs_dir>/<nom>/` (par défaut
   `<profil>_<début>_<fin>`) : `<nom>.hyp`, `evenements.csv`, `phases.csv`
   et `run.yaml`. LocQuality_ToolBox lit ce dossier directement
   (`paths.nll_runs`).

Les stations pointées sans grille de temps sont signalées : NLLoc ignore
leurs phases. Avec `--grilles`, ce sont les stations absentes de
l'inventaire du serveur, ou hors de la tuile en 3D
(`--exclure-hors-modele <profil>` retire leurs phases pour comparer des
profils sur les mêmes données).

Pour qu'un run local reproduise SeisComP, `NLL.<profil>.conf` doit être à
jour avec la configuration du profil sur le serveur : c'est ce que garantit
`profil_vers_seiscomp.py`, qui installe le profil local tel quel (voir
[Installer un profil dans SeisComP](#installer-un-profil-dans-seiscomp--profil_vers_seiscomppy)).

## Pointés SeisComP : `fetch_picks.py`

`fetch_picks.py` récupère sur le serveur SeisComP (service web
fdsnws-event) les événements d'une période et de `fetch.zone`, avec leur
origine préférée (le manuel), ses arrivées et ses pointés, et les convertit
au format `NLLOC_OBS`. `nll_run.py` l'appelle tout seul ; on peut aussi le
lancer à part :

```bash
python fetch_picks.py --config <config de la région> --debut 2024-11-01 --fin 2024-11-30
```

Une requête par jour ; chaque journée est gardée dans `fetch.cache_dir` et
n'est plus redemandée ensuite (`--refresh` pour retélécharger, par exemple
après une révision des pointés). Le service ne renvoie que l'origine
préférée de chaque événement : les origines NLL du serveur ne sont pas
récupérables par ce biais.

Seules les arrivées utilisées (`timeUsed`) sont gardées. Les pointés sans
incertitude (presque tous) reçoivent `phases.default_error_s`, la valeur de
`NonLinLoc.defaultPickError` de SeisComP (0,02 s). Chaque événement est
précédé de `PUBLIC_ID <Event ID>`, que NLLoc recopie dans ses `.hyp`.

`seiscomp_xml_to_obs.py` fait la même conversion sur des dossiers de XML
déjà téléchargés (`phases.xml_dirs`, un ou plusieurs événements par
fichier) : `python seiscomp_xml_to_obs.py`.

## Installer un profil dans SeisComP : `profil_vers_seiscomp.py`

`profil_vers_seiscomp.py` prépare un profil local pour SeisComP, sur
l'instance OAR de chacun :
- pour le localisateur NonLinLoc (plugin `locnll`, dans scolv) ;
- pour scrtdd : les grilles sont déclarées comme table de temps de trajet
  SeisComP (plugin `tttnll`, fourni avec scrtdd, interface `NLLGrid`), au
  nom du profil. Les profils scrtdd qui s'en servent viennent de chaque
  essai (`scrtdd_inputs.py`, voir [Relocaliser avec scrtdd](#relocaliser-avec-scrtdd-sur-le-serveur)).

NLL et scrtdd lisent ainsi les mêmes grilles, celles calculées en local.
Le dossier permet aussi de relocaliser avec screloc toute la période des
runs du profil, à partir des mêmes origines et des mêmes pointés que
`nll_run.py`, pour comparer le serveur au local. Le script ne se connecte à rien et n'écrit rien en base : il
remplit un dossier, et `INSTALLER.txt` donne les commandes à copier.

```bash
python profil_vers_seiscomp.py --config <config de la région> --profil 05_ubaye_1D_topo
```

La configuration de la région (celle passée à `nll_run.py`) donne le cache
des XML journaliers des pointés ; sans elle, ce sont ceux de `config.yaml`.

| Option | Ce que c'est | Défaut |
| --- | --- | --- |
| `--profil` | Profil à installer (dossier de `<profils_dir>`) | obligatoire |
| `--run` | Run dont prendre les stations, répétable | tous les runs du profil |
| `--utilisateur` | Identifiant sur la machine SeisComP | celui de l'ordinateur |
| `--hote` | Machine SeisComP | `ist-oar` |
| `--nllroot` | Dossier des profils sur la machine SeisComP | `/home/<utilisateur>/.seiscomp/nll` |

Seules les grilles des stations pointées dans les runs du profil sont
copiées : lancer d'abord `nll_run.py --grilles` sur la période voulue. Le
dossier `<racine>/export_seiscomp/<profil>/` contient :

| Fichier | Contenu |
| --- | --- |
| `NLL.<profil>.conf` | Fichier de contrôle, avec les chemins de la machine SeisComP (`${NLLROOT}` remplacé) |
| `topo.asc` | Topographie, copiée même si elle vient d'un autre profil |
| `time/` | Grilles de temps (P et S) des stations des runs, et grilles du modèle (`.mod`, exigées par `tttnll`) |
| `scolv-NLL.cfg` | Configuration du plugin pour une première installation : `plugins`, `NLLROOT`, `NonLinLoc.profiles` et les lignes du profil |
| `locnll_<profil>.cfg` | Les seules lignes du profil (`earthModelID`, `tablePath`, `controlFile`, `stationNameFormat`, `region`), à ajouter à un `scolv-NLL.cfg` existant |
| `scrtdd-NLL.cfg` | Pour scrtdd, première installation : plugin `tttnll`, `ttt.NLLGrid.tables` et la table du profil |
| `scrtdd_<profil>.cfg` | La table seule (`ttt.NLLGrid.<profil>.tablePath`), à ajouter à une configuration scrtdd qui a déjà `tttnll` |
| `screloc.cfg` | Configuration de screloc : plugin et profil, `reloc.locator = NonLinLoc`, `reloc.allowManualOrigins = true` (les origines de départ sont les LOCSAT manuelles) |
| `screloc/entree/` | XML journaliers des périodes des runs, copiés du cache de `fetch_picks.py` |
| `INSTALLER.txt` | Commandes à copier, dans l'ordre |

La configuration va dans `~/.seiscomp/scolv-NLL.cfg`, une copie de
`scolv-PROD.cfg` : la configuration habituelle de scolv reste intacte, et
on lance `./LaunchScolv.bash NLL` pour localiser avec NonLinLoc. `region`
est le rectangle de la grille de recherche (`LOCGRID`).

`NonLinLoc.defaultPickError` y vaut `phases.default_error_s` (0,02 s,
comme en local ; le plugin prend 0,5 s par défaut). screloc se lance par
`seiscomp exec screloc … --ep <jour>.xml`, sans quoi le plugin `locnll`
peut être introuvable ; il n'écrit rien en base, seulement du XML, qui
contient les origines de départ et les relocalisées (suffixe `.nll`).
screloc utilise aussi les arrivées désactivées par l'analyste
(`timeUsed = false`), que `nll_run.py` écarte : c'est la principale cause
d'écart entre les deux (validé sur novembre 2024, profil 1D de l'Ubaye :
98 % des positions identiques à 10 m près à phases égales).

Côté scrtdd, les lignes vont dans `~/.seiscomp/scrtdd.cfg` ; les profils
scrtdd viennent des essais. Le plugin `tttnll` retrouve la grille d'une
station par sa position et non par son nom : une station déplacée de plus
de 10 m (`maxSearchDistance`) depuis le calcul des grilles n'a plus de
temps de trajet.

Le script s'arrête si le `TRANS` du fichier de contrôle n'est pas celui des
grilles. Il signale aussi les stations des runs qui n'ont pas de grille :
NLL ignore leurs phases, sur le serveur comme en local.

## Relocaliser avec scrtdd sur le serveur

`scrtdd_inputs.py` prépare un **essai** scrtdd (double différence) à partir
d'un run NLL local : les entrées de scrtdd, le profil scrtdd de l'essai et
les commandes pour le lancer sur la machine SeisComP. scrtdd lit les
positions de départ dans ces fichiers plutôt que dans la base : on
relocalise sur le serveur des localisations qui n'existent qu'en local, avec
les mêmes grilles de temps que NLL (plugin `tttnll`).

Prérequis, une fois par profil NLL : le profil installé avec
`profil_vers_seiscomp.py` (étape 5 de son `INSTALLER.txt` : plugin `tttnll`
et table de temps du profil dans `~/.seiscomp/scrtdd.cfg`).

```bash
python scrtdd_inputs.py --config <config de la région> --run 05_ubaye_1D_topo_20230514_20250630 --essai ubaye_dec24 --debut 2024-12-01 --fin 2025-02-28
python scrtdd_inputs.py --config <config> --run <run> --essai jura_v5 --modele region
python scrtdd_inputs.py --config <config> --run <run> --essai ubaye_dec24_amorti --set solver.dampingFactor=0.05 --set entrees.rms_max=0.3
```

### Réglages : modèles d'essai et `--set`

Les réglages viennent d'un **modèle d'essai** (`modeles_scrtdd/`), un
fichier YAML commenté en deux sections :

- `entrees` : tri des événements du run avant scrtdd — `rms_max` (RMS NLL
  maximal, s) et `phases_min` (nombre minimal de phases ; 8 par défaut,
  comme `minNumPhases` : en dessous, un événement ne peut former aucun
  couple) ;
- `profil` : les paramètres du profil scrtdd, sous leur nom de scrtdd 2.x
  (sans le préfixe `profile.<essai>.`). La table de temps (NLLGrid, grilles
  du profil NLL du run) et la région (grille de recherche LOCGRID) sont
  ajoutées par le script.

| Modèle | Pour | Différence |
|---|---|---|
| `essaim` (défaut) | un essaim de quelques km (Ubaye, Ambert) | valeurs par défaut de scrtdd, corrélation croisée |
| `region` | une région étendue (Jura, ~160 km) | inversion plus contrainte : `dampingFactor` 0,1, `absoluteLocationConstraint` 1,0 (Jura v4, à confirmer) |

Pour changer une valeur le temps d'un essai : `--set <nom>=<valeur>`
(répétable), par exemple `--set crossCorrelation.enable=false` ou
`--set solver.downWeightingByResidual=[8,4]`. Le nom doit exister dans le
modèle (une faute de frappe est refusée, scrtdd l'ignorerait en silence).
Pour un jeu de réglages durable, ou un paramètre absent du modèle : copier
le modèle et passer `--modele <chemin de la copie>`.

### Le dossier de l'essai

Dans `<run>/scrtdd/<essai>/` (`--sortie` pour un autre dossier ; `--force`
remplace un essai existant, sorties rapatriées comprises) :

| Fichier | Contenu |
|---|---|
| `event.csv` | les localisations gardées du run, `id` scrtdd = 1, 2, … dans l'ordre chronologique |
| `phase.csv` | les pointés de l'origine de référence, relus dans les XML du cache de `fetch_picks.py`, sans les stations exclues du run ni celles absentes de l'inventaire (scrtdd refuserait tout le catalogue) |
| `station.csv` | positions de l'inventaire SeisComP, valides sur la période |
| `eventlist_<run>.csv` | `origin,event` dans l'ordre des `id` : LocQuality relie ainsi les `id` scrtdd aux Event ID |
| `scrtdd_<essai>.cfg` | le profil scrtdd de l'essai (`profile.<essai>.*`), à ajouter à `~/.seiscomp/scrtdd.cfg` |
| `essai.yaml` | run, période, modèle, modifications (`--set`), valeurs effectives, comptes (événements écartés par le tri), machine et dossiers |
| `LANCER.txt` | **les commandes à copier, dans l'ordre** : copie, profil, formes d'onde, scrtdd, vérifications, rapatriement |
| `formes_onde_NN.post` | formes d'onde utiles à la corrélation croisée, au format POST des services FDSN : une fenêtre par événement et par station pointée, de 20 s avant le premier pointé à 40 s après le dernier (`--marge-avant`, `--marge-apres`) |
| `telecharger_formes_onde.py` | copie du script du dépôt, à lancer sur le serveur si son archive n'a pas toutes les stations |

Le nom de l'essai est aussi celui du profil scrtdd : lettres, chiffres et
`_`. Par défaut, l'essai est copié dans `/home/<utilisateur>/scrtdd/<run>/<essai>/`
d'`ist-oar` (`--utilisateur`, `--hote`, `--dossier-distant`), et les formes
d'onde rassemblées dans `/home/<utilisateur>/sds/<run>/`, commun aux essais
du run (`--archive`).

Avec `--origines reference`, les positions de départ sont celles de
l'origine de référence du run (`evenements.csv`, en général le LOCSAT
manuel) : mêmes événements, mêmes phases et mêmes stations que le jeu NLL,
pour comparer les deux points de départ de la double différence.

Les pointés dont le réseau diffère de l'inventaire (ex. `XX.GREVE` pour
`9W.GREVE`) sont rattachés au réseau de l'inventaire. La magnitude vaut 0
quand l'export fdsnws n'en donne pas.

### À savoir

- **Version** : les noms de paramètres sont ceux de scrtdd 2.x ; beaucoup ont
  changé depuis la 1.8. `LANCER.txt` fait vérifier dans le log que les
  valeurs d'`essai.yaml` ont été prises.
- **Grilles** : avec `tttnll`, il faut des grilles P **et** S pour toutes les
  stations de `station.csv`, y compris celles où une seule phase est pointée
  (`nll_run.py --grilles` les calcule, `profil_vers_seiscomp.py` les copie).
- **Inventaire** : la corrélation des S demande l'orientation des
  composantes, donc les stations dans l'inventaire de la base que lit scrtdd
  (Jura sur une base de test : 100 % d'échec en S à 8 stations). Sur une
  base de test, importer leur StationXML avec
  `seiscomp exec import_inv fdsnxml <fichier>`, vérifier avec
  `seiscomp exec scinv check`, puis `seiscomp update-config inventory`.
  Ne rien importer dans une base de production.
- **Formes d'onde** : si celles de la région ne sont pas dans le recordstream
  de la machine (« not available » dans le log), `telecharger_formes_onde.py`
  les rassemble dans une archive SDS dédiée, puis scrtdd la lit avec
  `-I sdsarchive://<archive>` (les deux commandes sont dans `LANCER.txt`).
  Le script attribue chaque fenêtre à son centre de données public par le
  routage EIDA (CH → ETH, FR et 6F → RESIF…) ; celles des réseaux qu'aucun
  centre public ne sert (ex. 5C) sont extraites de l'archive de la machine
  (`--archive-serveur`). Tout est rangé avec `scart`, sans toucher à
  l'archive de la machine ; `bilan_formes_onde.txt` résume ce qui vient
  d'où. Les formes d'onde restent en cache : une relance sur les mêmes
  événements est bien plus rapide (Ambert : 7 min → 17 s de corrélation).

Une fois les sorties rapatriées (`reloc-event.csv`, `reloc-phase.csv`,
dossier de diagnostics), les scripts `dd_*` de LocQuality_ToolBox lisent
directement le dossier de l'essai : l'ajouter à `compare.scrtdd_runs`.

## Modèle 3D : découper une tuile

Le modèle 3D de Jean Virieux et Nouibat Ahmed (VP/VS en fonction de la
longitude, de la latitude et de la profondeur) s'obtient auprès de
ludovic.desmeuzes@univ-grenoble-alpes.fr ou
mickael.langlais@univ-grenoble-alpes.fr ; renseigner son chemin dans
`paths.model_file`. Deux scripts en tirent les fichiers NLL d'une région :

```
<model_file>.asc                          config.yaml
      (modèle global VP/VS)          (segment.zones : découpage en tuiles)
                    \                      /
                     v                    v
              ┌───────────────────────────────┐
              │     segment_from_zones.py     │
              └───────────────────────────────┘
                              │
                              v
                     <tuiles_dir>/<tuile>/
                       <tuile>_standard.csv
                       <tuile>_elevated.csv
                       README.txt
                              │
                              v
              ┌───────────────────────────────┐
              │        nll_pipeline.py        │
              └───────────────────────────────┘
                              │
                              v
                     <tuiles_dir>/<tuile>/model/
                       layer.P.mod.hdr / .buf
                       layer.S.mod.hdr / .buf
                       topo.asc
```

```bash
python segment_from_zones.py
python nll_pipeline.py
```

1. **`segment_from_zones.py`** découpe le modèle global en tuiles
   régionales (une par zone de `segment.zones` : `numero`, `nom`,
   `lon_min`, `lon_max`, `lat_min`, `lat_max`, et optionnellement
   `depth_max_km`), avec extension optionnelle en altitude pour couvrir la
   topographie.
2. **`nll_pipeline.py`** fait, pour chaque tuile, la projection Azimuthal
   Equidistant, l'interpolation sur grille régulière, l'extraction du plus
   grand rectangle complet, l'écriture des fichiers binaires NLL
   (`layer.P/S.mod.hdr/.buf`) et de la topographie (`topo.asc`).

   Avec `pipeline.interp_method: grille` (par défaut), chaque nœud de la
   grille NLL est ramené en longitude/latitude par la projection inverse et
   la vitesse est interpolée linéairement dans la grille d'origine du modèle :
   environ 10 s pour une tuile de 20 millions de nœuds, contre plus d'une
   heure avec l'ancienne interpolation par points dispersés (`linear` /
   `nearest`, gardée pour un modèle non régulier). Avec `pipeline.fix_vpvs`,
   les Vp/Vs physiquement impossibles sont corrigés dans les fichiers
   produits.

   Attention : `nll_pipeline.py` traite **tous** les sous-dossiers de
   `paths.tuiles_dir` qui ont un `README.txt`. Pour refaire une seule tuile,
   utiliser un dossier de travail et une configuration à part (exemple :
   `profils_travail/tuile_3D_60km/config_tuile_3D_60km.yaml`), passée avec
   `--config`.

Le code partagé (projection, lecture des `README.txt`, configuration) est
dans `nll_common.py`.

## En cas de problème

| Message ou symptôme | Cause probable |
| --- | --- |
| `Fichier de configuration introuvable : …` | Le fichier passé en `--config` n'existe pas (souvent une faute dans le chemin d'un `config_<région>.yaml`) |
| `NonLinLoc introuvable` | Lancer `python installer_nll.py`, ou indiquer le dossier des programmes dans `nll_bin` de `config.yaml` |
| `Vel2Grid a échoué` / `Grid2Time a échoué` | Le journal `.log` indiqué donne le détail (souvent une ligne mal écrite du modèle de vitesse) |
| Téléchargement des pointés bloqué ou en erreur | Serveur fdsnws inaccessible : réseau de l'université ou VPN ; tester l'adresse dans un navigateur |
| `topo.asc non généré` | Pas d'internet ou `srtm.py` absent ; relancer avec `--force`, ou `--sans-topo` |
| `… existe déjà (--force pour l'écraser)` | Profil ou région déjà créés : choisir un autre nom, ou `--force` |
| `⚠ N stations sans grille` | Stations absentes de l'inventaire du serveur (ou hors de la tuile 3D) : leurs phases sont ignorées |
| Séismes collés au fond de la grille (profondeur = `--prof-max`) | Grille de recherche trop peu profonde : recréer le profil avec un `--prof-max` plus grand |

## Documentation

Ce README est la référence des outils (commandes, options, fichiers
produits) : c'est lui qu'on met à jour avec le code.

- `docs/Mise en place NLL sur Seiscomp.pdf` : les concepts, qui ne changent
  pas avec le code — `TRANS`, modèle 1D vs 3D, grilles `VGGRID`/`LOCGRID`,
  ce que fait l'installation d'un profil sur OAR (scolv, screloc, scrtdd),
  explication ligne par ligne des paramètres (`vel2grid.in`, `grid2time.in`,
  `NLL.<profil>.conf`), et la voie manuelle avec les programmes de NonLinLoc.
  Les commandes y renvoient à ce README.
- `docs/vel2grid_grid2time.in.example` : fichier Vel2Grid + Grid2Time
  commenté pour un modèle 1D, pour comprendre ce qu'écrit
  `creer_profil.py` ou le faire à la main.
- `modeles_vitesse/` : modèles 1D prêts à passer en `--modele` :
  - `jura.nd` : modèle du Jura, utilisé par le premier essai ;
  - `alpes_labo.txt` : modèle à 4 couches du laboratoire, celui du profil
    SeisComP `1D_ubaye` et des profils 1D du Mont-Blanc ;
  - `alpes_paul2001.txt` : modèle à 7 couches de Paul et al. (2001), réseau
    Sismalp (profil `05_ubaye_1D_paul2001`) ;
  - `auvergne_40km.txt` : modèle « auvergne-40km » des tables LOCSAT,
    retrouvé à partir des temps de trajet ; utilisé pour l'essaim d'Ambert
    (profil `05_ambert_1D_auvergne_topo`).

## Tests

```bash
pytest tests/
```

Les tests couvrent la projection Azimuthal Equidistant, la configuration,
l'extraction du plus grand rectangle complet, l'en-tête de `topo.asc`, la
conversion des XML SeisComP en pointés NLL, la préparation d'un run local,
la création d'un profil (lecture des modèles, géométrie du profil du Jura)
et la préparation de scrtdd (fenêtres de formes d'onde, routage).

## Structure des fichiers

```
Loc_ToolBox/
├── README.md                  ← ce fichier
├── requirements.txt           ← dépendances Python
├── config.example.yaml        ← configuration par défaut, chaque clé documentée (versionné)
├── config.yaml                ← configuration de la machine, facultative (non versionné)
├── installer_nll.py           ← télécharge et compile NonLinLoc dans <racine>/bin
├── choisir_zone.html          ← carte : dessiner la zone, obtenir la commande creer_profil.py
├── creer_profil.py            ← nouveau profil 1D ou 3D + configuration de la région
├── nll_run.py                 ← run NLL local : profil × période
├── fetch_picks.py             ← pointés d'une période depuis le serveur (fdsnws)
├── seiscomp_xml_to_obs.py     ← pointés SeisComP (XML déjà téléchargés) → NLLOC_OBS
├── profil_vers_seiscomp.py    ← profil local → dossier à installer dans SeisComP (scolv, scrtdd)
├── scrtdd_inputs.py           ← essai scrtdd à partir d'un run local (entrées, profil, LANCER.txt)
├── telecharger_formes_onde.py ← sur le serveur : formes d'onde pour scrtdd (FDSN + archive)
├── segment_from_zones.py      ← modèle 3D : découpage en tuiles
├── nll_pipeline.py            ← modèle 3D : fichiers NLL de chaque tuile, topographie
├── nll_common.py              ← code partagé (projection, configuration, lecture)
├── modeles_vitesse/           ← modèles de vitesse 1D (Jura, Alpes, Auvergne)
├── modeles_scrtdd/            ← modèles d'essai scrtdd (essaim, région)
├── tests/                     ← tests unitaires (pytest)
└── docs/                      ← tutoriel NLL/SeisComP + exemple de fichier .in
```
