# NonLinLoc_ToolBox

Outils pour localiser des séismes avec **NonLinLoc (NLL)** sur son propre
ordinateur, avec les pointés d'un serveur SeisComP, sans passer par le
serveur. Trois usages :

1. **Créer un profil NLL pour une nouvelle région** à partir d'un modèle de
   vitesse 1D (`creer_profil.py`) ou du modèle 3D (`segment_from_zones.py` +
   `nll_pipeline.py`).
2. **Localiser une période** avec un profil : pointés récupérés sur le
   serveur, grilles de temps calculées, NLLoc lancé en parallèle
   (`nll_run.py`).
3. **Préparer une relocalisation en double différence** avec scrtdd sur le
   serveur (`scrtdd_inputs.py`, `telecharger_formes_onde.py`).

La qualité des localisations s'analyse ensuite avec le dépôt
[LocQuality_ToolBox](https://github.com/LuDesmeuzes/LocQuality_ToolBox), qui
lit directement les dossiers produits ici.

```
  modèle de vitesse ──► creer_profil.py ──► profil NLL ─┐
                                                        ├─► nll_run.py ──► run (.hyp, csv)
  serveur SeisComP ───► pointés (fdsnws) ───────────────┘        │
                                                                  ├─► LocQuality_ToolBox
                                                                  └─► scrtdd_inputs.py ──► scrtdd (serveur)
```

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

### 1. NonLinLoc

NonLinLoc (Anthony Lomax) se compile une fois :

```bash
git clone https://github.com/alomax/NonLinLoc.git
cd NonLinLoc/src
mkdir bin
cmake .
make
```

Copier les programmes de `NonLinLoc/src/bin/` dans un dossier stable, par
exemple `Localisation/outils/bin/`. Trois servent ici : `NLLoc`, `Grid2Time`
et `Vel2Grid`. **Ils doivent rester dans le même dossier** : les scripts
cherchent `Grid2Time` et `Vel2Grid` à côté de `NLLoc`. Lancé sans argument,
`NLLoc` affiche sa version (v7.1.04 ou plus récente).

### 2. NonLinLoc_ToolBox

```bash
git clone https://github.com/LuDesmeuzes/NonLinLoc.git NonLinLoc_ToolBox
cd NonLinLoc_ToolBox
python3 -m venv .venv
source .venv/bin/activate        # à refaire dans chaque nouveau terminal
pip install -r requirements.txt
pytest tests/                    # vérification : tous les tests doivent passer
```

### 3. Configuration de la machine

Tous les chemins sont dans un fichier YAML ; aucun n'est écrit dans le
code. Une seule fois :

```bash
cp config.example.yaml config.yaml
```

puis remplacer les `/path/to/…` de `config.yaml` par vos dossiers. Pour
localiser en local, seules comptent les sections suivantes :

| Clé | Contenu |
| --- | --- |
| `run.nlloc` | Chemin du programme `NLLoc` (Vel2Grid et Grid2Time à côté) |
| `run.profils_dir` | Dossier des profils NLL (un sous-dossier par profil) |
| `run.runs_dir` | Dossier des runs (un sous-dossier par run) |
| `run.regions_dir` | Dossier des configurations par région (facultatif) |
| `fetch.cache_dir`, `fetch.obs_dir` | Dossiers des pointés ; ceux de chaque région sont créés à côté |
| `phases.default_error_s` | Incertitude des pointés qui n'en ont pas (0,02 s, comme SeisComP) |

Les sections `paths`, `segment` et `pipeline` ne servent qu'au modèle 3D.
`config.yaml` est propre à chaque machine et n'est pas versionné ;
`config.example.yaml` documente chaque clé.

Organisation conseillée (celle des exemples) :

```
Localisation/
├── outils/bin/            NLLoc, Grid2Time, Vel2Grid
├── outils/NonLinLoc_ToolBox/
├── donnees/pointes/       pointés téléchargés (cache)
├── profils/               un dossier par profil NLL
├── profils_travail/       une configuration par région
└── runs/                  un dossier par run
```

## Premier essai : le Jura en 10 minutes

L'exemple crée un profil 1D pour le Jura, puis localise les 25 séismes de
mars 2024. Il faut l'accès au serveur fdsnws du Jura. Depuis le dossier
`NonLinLoc_ToolBox`, environnement activé :

```bash
# 1. Créer le profil et la configuration de la région (≈ 15 s, topographie comprise)
python creer_profil.py --region exemple_jura --nom exemple_jura_1D \
    --modele exemples/jura.nd --lat 46.95 47.55 --lon 5.45 7.55 \
    --prof-max 50 --cellule 4 \
    --fdsnws http://ist-scjura-sig.u-ga.fr:8080/fdsnws

# 2. Localiser mars 2024 (≈ 1 min : 31 jours de pointés, 23 stations, NLLoc)
python nll_run.py --config <regions_dir>/exemple_jura/config_exemple_jura.yaml \
    --profil exemple_jura_1D --debut 2024-03-01 --fin 2024-03-31 --grilles
```

L'étape 1 affiche le chemin exact de `config_exemple_jura.yaml` et la
commande de l'étape 2. À la fin, le run doit annoncer
« 25 localisés, 0 rejetés ». Les résultats sont dans
`<runs_dir>/exemple_jura_1D_20240301_20240331/` :

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

### Avec un modèle 1D : `creer_profil.py`

```bash
python creer_profil.py --region <région> --nom <profil> --modele <fichier> \
    --lat <min> <max> --lon <min> <max> --fdsnws <adresse …/fdsnws>
```

Modèles acceptés :

- **`.nd`** (format TauP) : « profondeur Vp Vs densité » par ligne ; une
  discontinuité = deux lignes à la même profondeur ; les lignes de texte
  (`mantle`…) sont ignorées. Entre deux profondeurs, la vitesse varie
  linéairement. Exemple : `exemples/jura.nd`.
- **texte en couches** : « toit Vp Vs [densité] » par ligne, en km et km/s,
  vitesses constantes dans chaque couche, commentaires après `#`.

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

Il refuse d'écraser un profil ou une région existants (`--force` pour le
faire). Vérification : recréé avec ce script, le profil `1_jura_1D_topo`
fait à la main donne exactement les mêmes localisations.

### Avec le modèle 3D

Voir [Modèle 3D : découper une tuile](#modèle-3d--découper-une-tuile) pour
produire `model/` et `topo.asc`, puis écrire à la main, sur le modèle d'un
profil existant (ex. `profils/05_ubaye_3D_topo/`) :

1. `nll_<profil>.in` : `TRANS`, `GTFILES <modèle> <grilles> P`, `GTMODE`,
   `GT_PLFD` (pas de `GTSRCE` : `--grilles` les prend dans l'inventaire).
   `${NLLROOT}` = `run.profils_dir`. Deux profils peuvent partager les mêmes
   grilles : `GTFILES` pointe alors vers le même dossier.
2. `NLL.<profil>.conf` : `TRANS` (le même que pour les grilles), `LOCGRID`,
   `LOCSEARCH`, `LOCMETH`… et `LOCTOPO_SURFACE ${NLLROOT}/<profil>/topo.asc 0`.
   La grille de recherche n'a pas besoin du pas des grilles de temps :
   l'octree subdivise lui-même. Choisir des cellules initiales d'environ
   3 km de côté (ex. `LOCGRID 101 101 36 -50 -50 -5 1 1 1` et
   `OCT 30 30 11` : 100/30 et 35/11 km).
3. Une configuration de région : copier celle d'une autre région
   (`profils_travail/<région>/config_<région>.yaml`) et changer le serveur,
   la zone et les dossiers des pointés.

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
   grille 3D au pas de 0,5 km (87 Mo par grille), moins d'une seconde en 1D.
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
jour avec la configuration du profil sur le serveur. Sur novembre 2024 avec
le profil `1D_ubaye`, 93 % des 3022 événements communs avec le run SeisComP
`1D_ubaye_v2` ont exactement la même position ; les écarts concernent
surtout les événements pointés sur des stations à plus de 50 km.

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

## Relocaliser avec scrtdd sur le serveur

`scrtdd_inputs.py` prépare les fichiers d'entrée de scrtdd (double
différence) à partir d'un run NLL local. scrtdd lit alors les positions de
départ dans ces fichiers plutôt que dans la base : on relocalise sur le
serveur, avec son profil scrtdd et ses formes d'onde, des localisations qui
n'existent qu'en local.

```bash
python scrtdd_inputs.py --config <config de la région> --run 05_ubaye_1D_topo_20230514_20250630
python scrtdd_inputs.py --config <config> --run <run> --debut 2024-12-01 --fin 2025-02-28
python scrtdd_inputs.py --config <config> --run <run> --origines reference
```

Dans `<run>/scrtdd/` :

- `event.csv` : les localisations du run (événements `LOCATED`), avec un
  `id` scrtdd = 1, 2, … dans l'ordre chronologique ;
- `phase.csv` : les pointés de l'origine de référence, relus dans les XML du
  cache de `fetch_picks.py` (codes réseau, location et canal, nécessaires à
  la corrélation croisée), sans les stations exclues du run ni celles
  absentes de l'inventaire (scrtdd refuse le catalogue entier pour une
  seule phase à station inconnue) ;
- `station.csv` : positions de l'inventaire SeisComP, valides sur la
  période ;
- `eventlist_<run>.csv` : `origin,event` dans l'ordre des `id`, pour que
  LocQuality relie les `id` scrtdd aux Event ID ;
- `formes_onde_NN.post` : la liste des formes d'onde utiles à la corrélation
  croisée, au format POST des services FDSN (`réseau station location
  canaux début fin`) : une fenêtre par événement et par station pointée, de
  20 s avant le premier pointé à 40 s après le dernier (`--marge-avant`,
  `--marge-apres`), les 3 composantes ; 2000 fenêtres au plus par fichier ;
- `telecharger_formes_onde.py` : copie du script du dépôt, à lancer sur le
  serveur si son archive n'a pas toutes les stations (voir plus bas).
  Python 3 seul (bibliothèque standard) et `scart`.

Avec `--origines reference`, les positions de départ sont celles de
l'origine de référence du run (`evenements.csv`, en général le LOCSAT
manuel), écrites par défaut dans `<run>/scrtdd_reference/` : mêmes
événements, mêmes `id`, mêmes phases et mêmes stations que le jeu NLL, pour
comparer les deux points de départ de la double différence.

Les pointés dont le réseau diffère de l'inventaire (ex. `XX.GREVE` pour
`9W.GREVE`) sont rattachés au réseau de l'inventaire. La magnitude vaut 0
quand l'export fdsnws n'en donne pas.

Sur le serveur, copier le dossier puis lancer scrtdd avec ces trois fichiers
à la place d'une liste d'origines (syntaxe à vérifier avec `scrtdd --help`
selon la version) :

```bash
scrtdd --reloc-catalog station.csv,event.csv,phase.csv --profile <profil> --console=1 -v
```

- Si le profil scrtdd calcule les temps de trajet avec les grilles NLL
  (plugin `tttnll`), copier aussi `model/` et `time/` du profil NLL : il faut
  des grilles P **et** S pour toutes les stations de `station.csv`, y compris
  celles où une seule phase est pointée (`nll_run.py --grilles` les calcule).
- Les stations doivent être dans l'**inventaire de la base** du serveur qui
  fait tourner scrtdd : sans l'orientation des composantes, les S ne sont
  pas corrélées (Jura : 100 % d'échec en S à 8 stations). Importer leur
  StationXML avec `seiscomp exec import_inv fdsnxml <fichier>`, vérifier avec
  `seiscomp exec scinv check`, puis écrire dans la base avec
  `seiscomp update-config inventory` (`scinv ls` lit les fichiers, pas la
  base).
- Si les formes d'onde de la région ne sont pas dans le recordstream par
  défaut du serveur (le log l'indique : « waveforms … not available »),
  rassembler les fenêtres dans une archive SDS à part, puis ajouter
  `-I sdsarchive://<archive>` à la commande scrtdd :

  ```bash
  python3 telecharger_formes_onde.py --archive ~/sds/<run> --archive-serveur /data/sig/SDS
  ```

  Le script attribue chaque fenêtre à son centre de données public par le
  routage EIDA (CH → ETH, FR et 6F → RESIF…) et la télécharge ; celles des
  réseaux qu'aucun centre public ne sert (réseaux locaux, ex. 5C) sont
  extraites de l'archive du serveur (`--archive-serveur`). Tout est rangé
  avec `scart`, sans toucher à l'archive du serveur ; `bilan_formes_onde.txt`
  résume ce qui vient d'où. `fdsnws_fetch` n'est pas utilisé : il n'est pas
  installé avec tous les SeisComP. Exemple : Jura, où l'archive du serveur
  n'avait presque pas de stations suisses.
- Les formes d'onde téléchargées restent en cache : une relance sur les mêmes
  événements est beaucoup plus rapide (Ambert : 7 min → 17 s de corrélation).
- Les réglages du profil scrtdd dépendent de la région : ceux d'un essaim de
  quelques kilomètres (Ambert) laissent dériver les profondeurs sur une
  région de 160 km (Jura) ; y augmenter `solver.absoluteLocationConstraint`
  et `solver.dampingFactor`, et vérifier dans le log (`Parameters:`) que les
  valeurs ont été prises en compte.

Rapatrier ensuite les sorties de scrtdd (`reloc-event.csv`,
`reloc-phase.csv`…) dans le même dossier : les scripts `dd_*` de
LocQuality_ToolBox le lisent directement.

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
python segment_from_zones.py     # 1. découpage du modèle global en tuiles
python nll_pipeline.py           # 2. fichiers NLL de chaque tuile
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
| `Fichier de configuration introuvable : …config.yaml` | `config.yaml` pas encore créé (voir Installation, étape 3) ou mauvais `--config` |
| `Vel2Grid a échoué` / `Grid2Time a échoué` | Programmes absents du dossier de `run.nlloc` : les copier à côté de `NLLoc` ; le journal `.log` indiqué donne le détail |
| Téléchargement des pointés bloqué ou en erreur | Serveur fdsnws inaccessible : réseau de l'université ou VPN ; tester l'adresse dans un navigateur |
| `topo.asc non généré` | Pas d'internet ou `srtm.py` absent ; relancer avec `--force`, ou `--sans-topo` |
| `… existe déjà (--force pour l'écraser)` | Profil ou région déjà créés : choisir un autre nom, ou `--force` |
| `⚠ N stations sans grille` | Stations absentes de l'inventaire du serveur (ou hors de la tuile 3D) : leurs phases sont ignorées |
| Séismes collés au fond de la grille (profondeur = `--prof-max`) | Grille de recherche trop peu profonde : recréer le profil avec un `--prof-max` plus grand |

## Documentation

- `docs/Mise en place NLL sur Seiscomp.pdf` : tutoriel du pipeline NonLinLoc
  complet — concepts (`TRANS`, modèle 1D vs 3D, grilles `VGGRID`/`LOCGRID`),
  grilles de temps, puis mise en place de NLL sur SeisComP.
- `docs/vel2grid_grid2time.in.example` : fichier Vel2Grid + Grid2Time
  commenté pour un modèle 1D, pour comprendre ce qu'écrit
  `creer_profil.py` ou le faire à la main.
- `exemples/jura.nd` : modèle 1D du Jura, utilisé par le premier essai.

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
NonLinLoc_ToolBox/
├── README.md                  ← ce fichier
├── requirements.txt           ← dépendances Python
├── config.example.yaml        ← modèle de configuration (versionné)
├── config.yaml                ← configuration de la machine (non versionné)
├── creer_profil.py            ← nouveau profil 1D + configuration de la région
├── nll_run.py                 ← run NLL local : profil × période
├── fetch_picks.py             ← pointés d'une période depuis le serveur (fdsnws)
├── seiscomp_xml_to_obs.py     ← pointés SeisComP (XML déjà téléchargés) → NLLOC_OBS
├── scrtdd_inputs.py           ← fichiers d'entrée scrtdd à partir d'un run local
├── telecharger_formes_onde.py ← sur le serveur : formes d'onde pour scrtdd (FDSN + archive)
├── segment_from_zones.py      ← modèle 3D : découpage en tuiles
├── nll_pipeline.py            ← modèle 3D : fichiers NLL de chaque tuile, topographie
├── nll_common.py              ← code partagé (projection, configuration, lecture)
├── exemples/                  ← modèle 1D du premier essai
├── tests/                     ← tests unitaires (pytest)
└── docs/                      ← tutoriel NLL/SeisComP + exemple de fichier .in
```
