# Loc_ToolBox

*Version française : [README.md](README.md)*

The production chain for earthquake locations: fetch picks from a SeisComP
server, locate with **NonLinLoc (NLL)** on your own computer, install a
profile in SeisComP and prepare double-difference relocation (scrtdd).
Analysis of the results lives in a separate repository (LocQuality_ToolBox,
see below). Four uses:

1. **Create an NLL profile for a new region** from a 1D velocity model or
   from the 3D model (`creer_profil.py`).
2. **Locate a period** with a profile: picks fetched from the server, travel
   time grids computed, NLLoc run in parallel (`nll_run.py`).
3. **Prepare a double-difference relocation** with scrtdd on the server
   (`scrtdd_inputs.py`, `telecharger_formes_onde.py`).
4. **Install a profile in SeisComP** (scolv with the NonLinLoc plugin, and
   scrtdd), using the grids computed locally (`profil_vers_seiscomp.py`).

Location quality is then analysed with the
[LocQuality_ToolBox](https://github.com/LuDesmeuzes/LocQuality_ToolBox)
repository, which reads the folders produced here directly.

> Note: the scripts, their options and their messages are in French. This
> README keeps those names as they are, since they are what you type. The
> generated instruction files (`INSTALLER.txt`, `LANCER.txt`) can be written
> in English: set `langue: en` in `config.yaml`, or pass `--langue en`.

```
  velocity model ───► creer_profil.py ──► NLL profile ─┐
                                                        ├─► nll_run.py ──► run (.hyp, csv)
  SeisComP server ──► picks (fdsnws) ──────────────────┘        │
                                                                  ├─► LocQuality_ToolBox
                                                                  └─► scrtdd_inputs.py ──► scrtdd (server)
  NLL profile + runs ──► profil_vers_seiscomp.py ──► folder to copy ──► scolv (SeisComP)
```

## Getting started

1. **Install** the tools and NonLinLoc, then do the **first try on the
   Ubaye** (sections [Installation](#installation) and
   [First try](#first-try-the-ubaye-in-5-minutes), a few minutes).
2. **Understand what the tools do**: the PDF *Mise en place NLL sur
   SeisComP* (`docs/`, in French) explains the concepts, the parameters line
   by line and the installation on OAR. The commands themselves are in this
   README.
3. **Your region**: choose the area, create the profile, launch a run
   ([Create a profile](#creating-a-profile-for-a-new-region),
   [Launch a run](#launching-a-run-nll_runpy)).
4. **Analyse location quality** with
   [LocQuality_ToolBox](https://github.com/LuDesmeuzes/LocQuality_ToolBox).
5. **Install the profile on OAR**, then prepare **scrtdd**
   ([Install a profile in SeisComP](#installing-a-profile-in-seiscomp-profil_vers_seiscomppy),
   [Relocate with scrtdd](#relocating-with-scrtdd-on-the-server)).

## Requirements

- macOS or Linux, Python 3.9 or newer, `git`, a C compiler and `cmake`
  (for NonLinLoc).
- Access to the **fdsnws** web service of the region's SeisComP server
  (e.g. `http://ist-scprod-sig.u-ga.fr:8080/fdsnws`, the production server). ISTerre
  servers are reachable from the university network; elsewhere, use the
  VPN.
- Internet access for topography (SRTM data, downloaded once).
- For the 3D model only: the model file by Jean Virieux and Nouibat Ahmed
  (see [3D model](#3d-model-cutting-a-tile)).

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

`source .venv/bin/activate` must be run again in every new terminal.
`pytest` checks the installation: all tests should pass.

The repository can live anywhere. Work (profiles, runs, picks) goes into a
separate **working folder**, `racine`. By default it is
`Loc_ToolBox_travail/` **next to** the repository, created if needed, so it
survives a fresh clone of the repository.

### 2. NonLinLoc

NonLinLoc (Anthony Lomax) is compiled once, with the provided script:

```bash
python installer_nll.py
```

It downloads NonLinLoc, compiles it (a few minutes) and copies its programs
into `<racine>/bin/`, where the scripts find them with no configuration. If
a build tool is missing, it prints the command to install it:
`xcode-select --install` and `brew install cmake` on macOS,
`sudo apt install build-essential cmake` on Linux.

NonLinLoc already compiled elsewhere? The scripts look for `NLLoc`,
`Vel2Grid` and `Grid2Time`, which must be **in the same folder**, in this
order: `nll_bin` from `config.yaml`, `<racine>/bin/`,
`<racine>/outils/bin/`, then the PATH.

### 3. Configuration (optional)

Without `config.yaml`, the scripts use `config.example.yaml`, and everything
works with the default working folder. To change it, or any other setting:

```bash
cp config.example.yaml config.yaml
```

then edit in `config.yaml`:

| Key | Content |
| --- | --- |
| `racine` | Working folder (default: `Loc_ToolBox_travail/` next to the repository) |
| `nll_bin` | Folder of the NonLinLoc programs, if they are neither in `<racine>/bin/` nor in the PATH |
| `paths.model_file` | Global 3D model (for `--modele-3d` only) |
| `langue` | Language of the generated instruction files (`INSTALLER.txt`, `LANCER.txt`, comments in the `.cfg` files): `fr` (default) or `en`. The commands do not change |

The other paths (`run.profils_dir`, `run.runs_dir`, `fetch.cache_dir`…) are
relative to `racine` and have default values: no need to touch them. An
absolute path (`/…` or `~/…`) is used as is. `config.example.yaml` documents
every key. `config.yaml` is specific to each machine and is not versioned.

Contents of the working folder:

```
<racine>/
├── bin/                   NLLoc, Grid2Time, Vel2Grid (installer_nll.py)
├── donnees/pointes/       downloaded picks (cache)
├── profils/               one folder per NLL profile
├── profils_travail/       one configuration per region
└── runs/                  one folder per run
```

## First try: the Ubaye in 5 minutes

This example creates a 1D profile for the Ubaye, then locates the roughly
1,080 earthquakes of September 2024 (Ubaye swarm). It requires access to the
production fdsnws server (`ist-scprod-sig`). From the `Loc_ToolBox` folder,
with the environment activated:

1. Create the profile and the region configuration (≈ 5 s, topography
   included):

```bash
python creer_profil.py --region exemple_ubaye --nom exemple_ubaye_1D \
    --modele modeles_vitesse/alpes_labo.txt --lat 44.39 44.59 --lon 6.61 6.90 \
    --prof-max 40 --fdsnws http://ist-scprod-sig.u-ga.fr:8080/fdsnws
```

2. Locate September 2024 (≈ 1 min: 30 days of picks, 34 stations, NLLoc).
   The easiest is to copy the command that step 1 prints under « Étape
   suivante » (next step), which has the actual path, replacing the
   `AAAA-MM-JJ` placeholders (YYYY-MM-DD) with the dates. Written by hand,
   `<racine>` is the working folder (by default `Loc_ToolBox_travail/`, next
   to the repository):

```bash
python nll_run.py --config <racine>/profils_travail/exemple_ubaye/config_exemple_ubaye.yaml \
    --profil exemple_ubaye_1D --debut 2024-09-01 --fin 2024-09-30 --grilles
```

At the end, the run should report « 1083 localisés, 0 rejetés » (1083
located, 0 rejected; the number may vary slightly if events have been
reviewed on the server since). The results are in
`<racine>/runs/exemple_ubaye_1D_20240901_20240930/`:

- `exemple_ubaye_1D_20240901_20240930.hyp`: the locations in NLLoc format;
- `evenements.csv`: one event per line, with the server origin for
  comparison;
- `phases.csv`: the residuals of each phase;
- `run.yaml`: profile, period, parameters and counts.

The run then prints the next two steps (install the profile in SeisComP,
prepare a scrtdd relocation): see below.

To look at these results (map, cross-sections, comparison with the server),
move on to LocQuality_ToolBox (`paths.nll_runs`).

## Creating a profile for a new region

A profile is a folder in `profils/` that contains everything NLL needs for a
region: velocity model, travel time grids, search parameters. It carries the
name of a SeisComP NLL profile when it is a copy of one.

### Choosing the area on a map: `choisir_zone.html`

The simplest way for a new region is to open `choisir_zone.html` in a
browser (double-click, or `open choisir_zone.html` on macOS,
`xdg-open choisir_zone.html` on Linux; internet is needed for the base map).
Draw a rectangle around the earthquakes to locate. Then choose the 1D or 3D
model, the grid spacing, the topography, the region and the server. The
page then shows the complete `creer_profil.py` command, with a profile name
built as `<spacing>_<region>_<1D|3D>[_topo]`, and a button to copy it.

The map also shows the NLL search grid that will be created (dashed: the
area plus the margin, rounded to 5 km). In 3D, it shows the model tile
(dotted, to check: it must cover the stations) and estimates the disk space
of the travel time grids. The page does not run anything itself: the copied
command is what creates the profile.

### With a 1D model: `creer_profil.py`

```bash
python creer_profil.py --region <region> --nom <profile> --modele <file> \
    --lat <min> <max> --lon <min> <max> --fdsnws <address …/fdsnws>
```

Required options:

| Option | What it is | Example |
| --- | --- | --- |
| `--region` | Short region name. It names the region configuration (`<regions_dir>/<region>/config_<region>.yaml`) and the picks cache (`par_jour_<region>`). Several profiles can share a region: a 1D then a 3D, or two models to compare. The existing configuration is then kept, provided the server, the area and the event types are the same. | `ubaye` |
| `--nom` | Profile name. It names the folder `<profils_dir>/<profile>/`, it is what you pass to `nll_run.py --profil`, and it appears in run names (`<profile>_<start>_<end>`). When the profile is a copy of a SeisComP NLL profile, reuse the same name. Otherwise, the convention is `<n>_<region>_<1D or 3D>[_topo]`. | `1_ubaye_1D_topo` |
| `--modele` | 1D velocity model (formats below). For a 3D model, see `--modele-3d` below. | `modeles_vitesse/alpes_labo.txt` |
| `--lat`, `--lon` | Area of the earthquakes to locate, in degrees: min and max latitudes, min and max longitudes (east positive). Picks are fetched in this area, and the search grid covers it, plus `--marge`. Stations may lie outside. | `--lat 44.39 44.59 --lon 6.61 6.90` |
| `--fdsnws` | fdsnws address of the region's SeisComP server, up to `/fdsnws`: the script appends `/event/1/query` and `/station/1/query`. | `http://ist-scprod-sig.u-ga.fr:8080/fdsnws` |

Region and profile names are limited to unaccented letters, digits, `_` and `-`, because they are used as folder and file names. All options, with their default values, are listed by `python creer_profil.py --help`.

Accepted models:

- **`.nd`** (TauP format): "depth Vp Vs density" per line; a discontinuity
  = two lines at the same depth; text lines (`mantle`…) are ignored.
  Between two depths, velocity varies linearly. Example:
  `modeles_vitesse/jura.nd`.
- **layered text**: "top Vp Vs [density]" per line, in km and km/s,
  constant velocities within each layer, comments after `#`. Examples:
  `modeles_vitesse/alpes_labo.txt`, `modeles_vitesse/alpes_paul2001.txt`,
  `modeles_vitesse/auvergne_40km.txt`.

Depths in km below sea level. The first layer is extended up to −5 km to
cover the relief.

The script picks the parameters itself, following the Ubaye, Mont-Blanc,
Ambert and Jura profiles:

| NLL parameter | Choice | Option |
| --- | --- | --- |
| `TRANS` (projection centre) | centre of the area | — |
| `LOCGRID` (search grid, 1 km spacing) | the area + 10 km on each side, rounded to 5 km; from −5 km to 30 km | `--marge`, `--prof-max` |
| `LOCSEARCH OCT` (octree search) | initial cells of about 3 km; nodes = 5 × initial cells, at least 50,000 | `--cellule` |
| `VGGRID` (2D travel time grids) | 1 km spacing, over 400 km, from −5 to max(60, max depth + 10) km | `--pas`, `--distance-max` |
| `LOCTOPO_SURFACE` (topography) | SRTM relief over the search footprint | `--sans-topo` |
| Event types fetched | `earthquake` (no quarry blasts) | `--types` |

Two settings depend on the region:

- **`--prof-max`**: maximum search depth. Set it a little beyond the
  deepest earthquakes in the region's catalogue (the Jura has some down to
  54 km: `--prof-max 50` could have been 60).
- **`--cellule`**: size of the initial search cells. NLL does not test every
  position: it divides the search volume into cells of `--cellule` km,
  computes the probability at the centre of each, then splits the most
  likely one into 8, and repeats until its node budget is used up (5th
  number of `LOCSEARCH OCT`). Cells that are too large sample coarsely and
  may miss the right area; too small, they consume the budget at the start,
  leaving less for refinement (the script sets the budget to 5 times the
  number of initial cells, so smaller cells make each location slower).
  Keep 3 km; go to 4 or 5 km if the area is larger than 100 km across. Jura
  (180 × 90 × 55 km): 34,200 initial cells at 3 km, 14,490 at 4 km, i.e. a
  budget of 171,000 instead of 75,000 nodes (computation about 2.3 times
  longer at 3 km, estimated from the number of nodes).

The script writes:

- **`<profils_dir>/<profile>/`**: `NLL.<profile>.conf` (location
  parameters), `nll_<profile>.in` (travel time grids, read by
  `nll_run.py --grilles`), `vel2grid_P.in` and `vel2grid_S.in`, `model/`
  (NLL model, computed by Vel2Grid), `topo.asc`, a `README.txt` summarising
  the choices, and `time/` (empty: travel time grids are computed at the
  first run, only for the stations with picks);
- **`<regions_dir>/<region>/config_<region>.yaml`**: the region
  configuration (fdsnws server, area, picks folders), to pass as `--config`
  to `fetch_picks.py`, `nll_run.py` and `scrtdd_inputs.py`.

It refuses to overwrite an existing profile, or an existing region with a different server or area (`--force` to do
so). Check: rebuilt with this script, the hand-made `1_jura_1D_topo`
profile gives exactly the same locations.

### With the 3D model: `creer_profil.py --modele-3d`

The same script creates a 3D profile from the model by Jean Virieux and
Nouibat Ahmed (see [3D model](#3d-model-cutting-a-tile) to obtain it).
`--modele-3d` without a value uses `paths.model_file` from `config.yaml`:

```bash
python creer_profil.py --region montblanc --nom 1_montblanc_3D_topo --modele-3d \
    --lat 45.72 45.95 --lon 6.70 7.03 --pas 1 \
    --fdsnws http://ist-scprod-sig.u-ga.fr:8080/fdsnws
```

The script cuts a **tile** of the model around the area, converts it to NLL
format with `segment_from_zones.py` and `nll_pipeline.py` (settings in the
`segment` and `pipeline` sections of `config.yaml`), generates the
topography over the tile and writes the profile (travel time grids in
`GRID3D`). The projection centre is that of the tile. Three things differ
from 1D:

- **The tile must cover the stations**, not just the earthquakes: a station
  outside the model has no travel time grid, and its phases are lost. By
  default, the tile extends 80 km around the area (`--marge-tuile`);
  `--tuile-lat` / `--tuile-lon` set it explicitly. At Mont-Blanc, with a
  ±99 km tile, 71 stations were still outside the model (1,010 phases out
  of 155,219).
- **Disk space**: one full 3D grid per station and per phase. The script
  prints the estimate: on a 200 km tile, ≈ 20 MB per station and per phase
  at 1 km spacing, ≈ 157 MB at 0.5 km (Mont-Blanc: `time/` = 5 GB at 1 km,
  40 GB at 0.5 km). Start with 1 km spacing.
- **The model only covers one region**: the script stops if the tile goes
  outside it, or if the search grid exceeds the resulting model.

Check: rebuilt with this script (`--tuile-lat 44.94 46.73 --tuile-lon
5.59 8.14 --pas 0.5 --marge 37 --cellule 3.34`), the hand-made
`05_montblanc_3D_topo` profile gives the same NLL model.

For a hand-written profile (another 3D model, special settings), follow an
existing profile: `nll_<profile>.in` (`TRANS`,
`GTFILES <model> <grids> P`, `GTMODE GRID3D`, `GT_PLFD`; `${NLLROOT}` =
`run.profils_dir`; two profiles can share the same grids by pointing
`GTFILES` to the same folder) and `NLL.<profile>.conf` (same `TRANS`,
`LOCGRID`, `LOCSEARCH`, `LOCMETH`…, `LOCTOPO_SURFACE`).

## Launching a run: `nll_run.py`

`nll_run.py` locates the events of a period with NLL on the command line,
with a profile, without going through the server:

```bash
python nll_run.py --config <region config> --profil <profile> \
    --debut YYYY-MM-DD --fin YYYY-MM-DD --grilles
```

Options, to add as needed (they can be combined):
- `--grilles`: compute missing travel time grids (step 3);
- `--nom <name>`: name the run something other than
  `<profile>_<start>_<end>`;
- `--locsearch "OCT 15 15 15 0.001 50000 5000 0 1"`: override the profile's
  `LOCSEARCH`, for a test;
- `--jobs N`: number of chunks run in parallel;
- `--force`: overwrite a run with the same name.

1. The picks for the period are fetched by `fetch_picks.py` (below), with a
   daily cache.
2. The control file reuses `<profils_dir>/<profile>/NLL.<profile>.conf`
   (`TRANS`, `LOCGRID`, `LOCSEARCH`, `LOCMETH`, `LOCTOPO_SURFACE`…), with the
   travel time grids from `<profile>/time/`. `${NLLROOT}` is replaced by
   `run.profils_dir`. `--locsearch` replaces `LOCSEARCH` for a test.
3. **`--grilles`** first computes the missing travel time grids
   (Grid2Time), only for the stations picked during the period, for both P
   and S even if only one of the two phases is picked there (scrtdd may need
   the other). The `TRANS`, `GTFILES`, `GTMODE` and `GT_PLFD` lines are read
   from `<profile>/nll_<profile>.in`. Station positions come from the server
   inventory (`fetch.fdsnws_station_url`), valid over the period. Count
   about 2 s per station and per phase for a 3D grid at 0.5 km spacing
   (157 MB per grid, angles included), under one second in 1D.
4. `NLLoc` runs in parallel on `--jobs` chunks of the period (default:
   number of cores − 1): about 2 minutes for 3,000 events.
5. The run is written to `<runs_dir>/<name>/` (default
   `<profile>_<start>_<end>`): `<name>.hyp`, `evenements.csv`, `phases.csv`
   and `run.yaml`. LocQuality_ToolBox reads this folder directly
   (`paths.nll_runs`).
6. At the end of the run, `nll_run.py` prints the next two commands, ready
   to copy: `profil_vers_seiscomp.py` to install the profile in SeisComP
   (once per profile), then `scrtdd_inputs.py` to prepare an scrtdd
   relocation of this run (name `reloc1`, change as you like).

Picked stations without a travel time grid are reported: NLLoc ignores their
phases. With `--grilles`, these are stations missing from the server
inventory, or outside the tile in 3D (`--exclure-hors-modele <profile>`
removes their phases, to compare profiles on the same data).

For a local run to reproduce SeisComP, `NLL.<profile>.conf` must match the
profile configuration on the server: this is what
`profil_vers_seiscomp.py` guarantees, by installing the local profile as is
(see
[Install a profile in SeisComP](#installing-a-profile-in-seiscomp-profil_vers_seiscomppy)).

## SeisComP picks: `fetch_picks.py`

`fetch_picks.py` fetches from the SeisComP server (fdsnws-event web
service) the events of a period within `fetch.zone`, with their preferred
origin (the manual one), its arrivals and its picks, and converts them to
`NLLOC_OBS` format. `nll_run.py` calls it automatically; it can also be run
on its own:

```bash
python fetch_picks.py --config <region config> --debut YYYY-MM-DD --fin YYYY-MM-DD
```

One request per day; each day is kept in `fetch.cache_dir` and is not
requested again (`--refresh` to download again, e.g. after picks have been
revised). The service only returns the preferred origin of each event: the
server's NLL origins cannot be retrieved this way.

Only the arrivals actually used (`timeUsed`) are kept. Picks without an
uncertainty (almost all of them) get `phases.default_error_s`, the value of
SeisComP's `NonLinLoc.defaultPickError` (0.02 s). Each event is preceded by
`PUBLIC_ID <Event ID>`, which NLLoc copies into its `.hyp` files.

`seiscomp_xml_to_obs.py` does the same conversion on folders of
already-downloaded XML files (`phases.xml_dirs`, one or more events per
file): `python seiscomp_xml_to_obs.py`.

## Installing a profile in SeisComP: `profil_vers_seiscomp.py`

`profil_vers_seiscomp.py` prepares a local profile for SeisComP, on each
user's OAR instance:
- for the NonLinLoc locator (`locnll` plugin, in scolv);
- for scrtdd: the grids are declared as a SeisComP travel time table
  (`tttnll` plugin, shipped with scrtdd, `NLLGrid` interface), under the
  profile name. The scrtdd profiles that use it come from each relocation
  (`scrtdd_inputs.py`, see [Relocate with scrtdd](#relocating-with-scrtdd-on-the-server)).

NLL and scrtdd thus read the same grids, the ones computed locally. The
folder also allows relocating with screloc the whole period covered by the
profile's runs, from the same origins and the same picks as `nll_run.py`, to
compare the server with the local results. The script connects to nothing and writes nothing
to the database: it fills a folder, and `INSTALLER.txt` gives the commands
to copy.

```bash
python profil_vers_seiscomp.py --config <region config> --profil <profile>
```

For example, for the profile of the first try:
`--config <racine>/profils_travail/exemple_ubaye/config_exemple_ubaye.yaml --profil exemple_ubaye_1D`.
To try it in scolv (step 4 of `INSTALLER.txt`), the database opened by scolv
needs events from the profile's region.

The region configuration (the one passed to `nll_run.py`) gives the cache of
daily pick XML files; without it, those from `config.yaml` are used.

| Option | What it is | Default |
| --- | --- | --- |
| `--profil` | Profile to install (folder in `<profils_dir>`) | required |
| `--run` | Run to take the stations from, repeatable | all runs of the profile |
| `--utilisateur` | Username on the SeisComP machine | that of the computer |
| `--hote` | SeisComP machine | `ist-oar.u-ga.fr` |
| `--nllroot` | Profiles folder on the SeisComP machine | `/home/<user>/.seiscomp/nll` |
| `--langue` | Language of `INSTALLER.txt` and of the `.cfg` comments: `fr` or `en` | `langue` key of the config, otherwise `fr` |

Only the grids of stations picked in the profile's runs are copied: run
`nll_run.py --grilles` on the desired period first. The folder
`<racine>/export_seiscomp/<profile>/` contains:

| File | Content |
| --- | --- |
| `NLL.<profile>.conf` | Control file, with the SeisComP machine's paths (`${NLLROOT}` replaced) |
| `topo.asc` | Topography, copied even if it comes from another profile |
| `time/` | Travel time grids (P and S) of the runs' stations, and the model grids (`.mod`, required by `tttnll`) |
| `scolv-NLL.cfg` | Plugin configuration for a first installation: `plugins`, `NLLROOT`, `NonLinLoc.profiles` and the profile's lines |
| `locnll_<profile>.cfg` | Only the profile's lines (`earthModelID`, `tablePath`, `controlFile`, `stationNameFormat`, `region`), to add to an existing `scolv-NLL.cfg` |
| `scrtdd-NLL.cfg` | For scrtdd, first installation: `tttnll` plugin, `ttt.NLLGrid.tables` and the profile's table |
| `scrtdd_<profile>.cfg` | The table only (`ttt.NLLGrid.<profile>.tablePath`), to add to an scrtdd configuration that already has `tttnll` |
| `screloc.cfg` | screloc configuration: plugin and profile, `reloc.locator = NonLinLoc`, `reloc.allowManualOrigins = true` (the starting origins are the manual LOCSAT ones) |
| `screloc/entree/` | Daily XML files for the runs' periods, copied from the `fetch_picks.py` cache |
| `INSTALLER.txt` | Commands to copy, in order |

The configuration goes into `~/.seiscomp/scolv-NLL.cfg`, a copy of
`scolv-PROD.cfg`: the usual scolv configuration stays untouched, and you
run `./LaunchScolv.bash NLL` to locate with NonLinLoc. `region` is the
rectangle of the search grid (`LOCGRID`).

`NonLinLoc.defaultPickError` is set to `phases.default_error_s` (0.02 s, as
locally; the plugin's default is 0.5 s). screloc is run with
`seiscomp exec screloc … --ep <day>.xml`, otherwise the `locnll` plugin may
not be found; it writes nothing to the database, only XML, which contains
the starting origins and the relocated ones (suffix `.nll`). screloc also
uses arrivals disabled by the analyst (`timeUsed = false`), which
`nll_run.py` discards: this is the main cause of differences between the two
(validated on November 2024, Ubaye 1D profile: 98% of positions identical
within 10 m with the same phases).

On the scrtdd side, the lines go into `~/.seiscomp/scrtdd.cfg`; scrtdd
profiles come from the relocations. The `tttnll` plugin finds a station's
grid by its position, not by its name: a station moved by more than 10 m
(`maxSearchDistance`) since the grids were computed no longer has travel
times.

The script stops if the control file's `TRANS` does not match the grids'.
It also reports the runs' stations that have no grid: NLL ignores their
phases, on the server as well as locally.

## Relocating with scrtdd on the server

`scrtdd_inputs.py` prepares an scrtdd (double-difference) **relocation**
from a local NLL run: the scrtdd inputs, the relocation's scrtdd profile and
the commands to run it on the SeisComP machine. scrtdd reads the starting
positions from these files rather than from the database: you relocate on
the server locations that only exist locally, with the same travel time
grids as NLL (`tttnll` plugin).

Prerequisite, once per NLL profile: the profile installed with
`profil_vers_seiscomp.py` (step 5 of its `INSTALLER.txt`: `tttnll` plugin
and the profile's travel time table in `~/.seiscomp/scrtdd.cfg`).

It takes two stages: **one** `scrtdd_inputs.py` command locally, which
prepares the relocation, then the commands in its `LANCER.txt`, in order, on
the SeisComP machine. The basic command is printed at the end of every
`nll_run.py`:

```bash
python scrtdd_inputs.py --config <region config> --run <run> --reloc <reloc>
```

`<run>` is the name of an `nll_run.py` run (folder in `<racine>/runs/`,
e.g. `exemple_ubaye_1D_20240901_20240930`); its profile must be installed
(prerequisite above). `<reloc>` is a free name (letters, digits, `_`), for
example `ubaye_sept24`.

Options, to add as needed (they can be combined):
- `--debut YYYY-MM-DD --fin YYYY-MM-DD`: keep only part of the run (default:
  the whole run);
- `--modele region`: settings for an extended region (default: `essaim`,
  see below);
- `--set <name>=<value>`: change a value for this relocation, repeatable
  (e.g. `--set solver.dampingFactor=0.05 --set entrees.rms_max=0.3`);
- `--recordstream <source>`: read waveforms from somewhere other than the
  config's server (see "Waveforms" below);
- `--langue en`: `LANCER.txt` and the scrtdd profile header in English
  (default: `langue` key of the config, otherwise `fr`);
- `--force`: replace a relocation with the same name.

For example, a relocation of December only, with stronger damping:

```bash
python scrtdd_inputs.py --config <region config> --run <run> --reloc <reloc> \
    --debut 2024-12-01 --fin 2024-12-31 --set solver.dampingFactor=0.05
```

### Settings: templates and `--set`

Settings come from a **settings template** (`modeles_scrtdd/`), a commented
YAML file in two sections:

- `entrees`: selection of the run's events before scrtdd — `rms_max`
  (maximum NLL RMS, s) and `phases_min` (minimum number of phases; 8 by
  default, like `minNumPhases`: below that, an event cannot form any pair);
- `profil`: the scrtdd profile parameters, under their scrtdd 2.x names
  (without the `profile.<reloc>.` prefix). The travel time table (NLLGrid,
  grids of the run's NLL profile) and the region (LOCGRID search grid) are
  added by the script.

| Template | For | Difference |
|---|---|---|
| `essaim` (default) | a swarm a few km across (Ubaye, Ambert) | scrtdd defaults, cross-correlation |
| `region` | an extended region (Jura, ~160 km) | more constrained inversion: `dampingFactor` 0.1, `absoluteLocationConstraint` 1.0 (Jura v4, to be confirmed) |

To change a value for one relocation: `--set <name>=<value>` (repeatable),
for example `--set crossCorrelation.enable=false` or
`--set solver.downWeightingByResidual=[8,4]`. The name must exist in the
template (a typo is rejected; scrtdd would silently ignore it). For a
lasting set of settings, or a parameter missing from the template: copy the
template and pass `--modele <path to the copy>`.

### The relocation folder

In `<run>/scrtdd/<reloc>/` (`--sortie` for another folder; `--force`
replaces an existing relocation, including outputs already brought back):

| File | Content |
|---|---|
| `event.csv` | the run's retained locations, scrtdd `id` = 1, 2, … in chronological order |
| `phase.csv` | the picks of the reference origin, re-read from the XML files in the `fetch_picks.py` cache, without the stations excluded from the run or those missing from the inventory (scrtdd would reject the whole catalogue) |
| `station.csv` | positions from the SeisComP inventory, valid over the period |
| `eventlist_<run>.csv` | `origin,event` in `id` order: this is how LocQuality links scrtdd `id`s to Event IDs |
| `scrtdd_<reloc>.cfg` | the relocation's scrtdd profile (`profile.<reloc>.*`), to add to `~/.seiscomp/scrtdd.cfg` |
| `reloc.yaml` | run, period, template, changes (`--set`), effective values, counts (events dropped by the selection), machine and folders |
| `LANCER.txt` | **the commands to copy, in order**: copy, profile, waveforms, scrtdd, checks, bringing results back |
| `formes_onde_NN.post` | waveforms needed for cross-correlation, in FDSN services POST format: one window per event and per picked station, from 20 s before the first pick to 40 s after the last (`--marge-avant`, `--marge-apres`) |
| `telecharger_formes_onde.py` | copy of the repository's script, to run on the server if its archive lacks some stations |

The relocation name is also the scrtdd profile name: letters, digits and
`_`. By default, the relocation is copied to `/home/<user>/scrtdd/<run>/<reloc>/`
on `ist-oar` (`--utilisateur`, `--hote`, `--dossier-distant`), and the
waveforms are gathered in `/home/<user>/sds/<run>/`, shared by the run's
relocations (`--archive`).

With `--origines reference`, the starting positions are those of the run's
reference origin (`evenements.csv`, usually the manual LOCSAT): same events,
same phases and same stations as the NLL set, to compare the two starting
points of the double difference.

Picks whose network differs from the inventory (e.g. `XX.GREVE` for
`9W.GREVE`) are attached to the inventory's network. Magnitude is set to 0
when the fdsnws export does not provide one.

### Good to know

- **Version**: parameter names are those of scrtdd 2.x; many have changed
  since 1.8. `LANCER.txt` has you check in the log that the values from
  `reloc.yaml` were applied.
- **Grids**: with `tttnll`, P **and** S grids are needed for every station
  in `station.csv`, including those where only one phase is picked
  (`nll_run.py --grilles` computes them, `profil_vers_seiscomp.py` copies
  them).
- **Inventory**: S-wave correlation needs the component orientation, hence
  the stations must be in the inventory of the database scrtdd reads (Jura
  on a test database: 100% S failure at 8 stations). On a test database,
  import their StationXML with `seiscomp exec import_inv fdsnxml <file>`,
  check with `seiscomp exec scinv check`, then
  `seiscomp update-config inventory`. Never import anything into a
  production database.
- **Waveforms**: for cross-correlation, scrtdd reads waveforms from the
  server's fdsnws-dataselect service (`-I` in `LANCER.txt`):
  `fetch.recordstream` from the config
  (`fdsnws://ist-scprod-sig.u-ga.fr:8081` by default), or `--recordstream`.
  Without `-I`, scrtdd would look for a local SeedLink (`localhost:18000`:
  "Connection refused" in a loop). If many windows are missing (log line
  "Catalog waveform data: … not available N"), `telecharger_formes_onde.py`
  gathers them into a dedicated SDS archive, which scrtdd then reads with
  `-I sdsarchive://<archive>` (step 5 of `LANCER.txt`). The script assigns
  each window to its public data centre via EIDA routing (CH → ETH, FR and
  6F → RESIF…); windows from networks no public centre serves (e.g. 5C) are
  extracted from the machine's archive (`--archive-serveur`). Everything is
  stored with `scart`, without touching the machine's archive;
  `bilan_formes_onde.txt` summarises what came from where.
- **Cache**: scrtdd keeps the waveforms it reads in
  `performance.cacheDirectory` (`<folder>/<profile>/wfcache`): a rerun on
  the same events is much faster (Ambert: 7 min → 17 s of correlation). By
  default, this folder is inside the SeisComP installation, often read-only
  ("cacheDirectory: failed to create path"): step 5 of `INSTALLER.txt` puts
  it in `~/scrtdd/cache`, once per machine.

Once the outputs are brought back (`reloc-event.csv`, `reloc-phase.csv`,
diagnostics folder), the `dd_*` scripts of LocQuality_ToolBox read the
relocation folder directly: add it to `compare.scrtdd_runs`.

## 3D model: cutting a tile

The 3D model by Jean Virieux and Nouibat Ahmed (VP/VS as a function of
longitude, latitude and depth) is available from
ludovic.desmeuzes@univ-grenoble-alpes.fr or
mickael.langlais@univ-grenoble-alpes.fr; set its path in
`paths.model_file`. Two scripts derive the NLL files for a region from it:

```
<model_file>.asc                          config.yaml
      (global VP/VS model)          (segment.zones: tiling)
                    \                      /
                     v                    v
              ┌───────────────────────────────┐
              │     segment_from_zones.py     │
              └───────────────────────────────┘
                              │
                              v
                     <tuiles_dir>/<tile>/
                       <tile>_standard.csv
                       <tile>_elevated.csv
                       README.txt
                              │
                              v
              ┌───────────────────────────────┐
              │        nll_pipeline.py        │
              └───────────────────────────────┘
                              │
                              v
                     <tuiles_dir>/<tile>/model/
                       layer.P.mod.hdr / .buf
                       layer.S.mod.hdr / .buf
                       topo.asc
```

```bash
python segment_from_zones.py
python nll_pipeline.py
```

1. **`segment_from_zones.py`** cuts the global model into regional tiles
   (one per zone in `segment.zones`: `numero`, `nom`, `lon_min`, `lon_max`,
   `lat_min`, `lat_max`, and optionally `depth_max_km`), with an optional
   upward extension to cover the topography.
2. **`nll_pipeline.py`** performs, for each tile, the Azimuthal Equidistant
   projection, the interpolation onto a regular grid, the extraction of the
   largest complete rectangle, and writes the NLL binary files
   (`layer.P/S.mod.hdr/.buf`) and the topography (`topo.asc`).

   With `pipeline.interp_method: grille` (the default), each node of the
   NLL grid is mapped back to longitude/latitude by the inverse projection
   and the velocity is linearly interpolated in the model's original grid:
   about 10 s for a 20-million-node tile, versus more than an hour with the
   former scattered-point interpolation (`linear` / `nearest`, kept for a
   non-regular model). With `pipeline.fix_vpvs`, physically impossible
   Vp/Vs values are corrected in the output files.

   Warning: `nll_pipeline.py` processes **all** subfolders of
   `paths.tuiles_dir` that have a `README.txt`. To redo a single tile, use
   a separate working folder and configuration (example:
   `profils_travail/tuile_3D_60km/config_tuile_3D_60km.yaml`), passed with
   `--config`.

Shared code (projection, reading `README.txt` files, configuration) is in
`nll_common.py`.

## Troubleshooting

Messages are shown as the scripts print them (in French).

| Message or symptom | Likely cause |
| --- | --- |
| `Fichier de configuration introuvable : …` (configuration file not found) | The file passed as `--config` does not exist (often a typo in the path of a `config_<region>.yaml`) |
| `NonLinLoc introuvable` (NonLinLoc not found) | Run `python installer_nll.py`, or set the programs folder in `nll_bin` in `config.yaml` |
| `Vel2Grid a échoué` / `Grid2Time a échoué` (failed) | The `.log` file mentioned gives the details (often a badly written line in the velocity model) |
| Pick download stuck or failing | fdsnws server unreachable: university network or VPN; test the address in a browser |
| `topo.asc non généré` (not generated) | No internet or `srtm.py` missing; rerun with `--force`, or `--sans-topo` |
| `… existe déjà (--force pour l'écraser)` (already exists) | Profile or region already created: choose another name, or `--force` |
| `⚠ N stations sans grille` (stations without a grid) | Stations missing from the server inventory (or outside the 3D tile): their phases are ignored |
| Earthquakes stuck at the bottom of the grid (depth = `--prof-max`) | Search grid too shallow: recreate the profile with a larger `--prof-max` |

## Documentation

This README is the reference for the tools (commands, options, output
files): it is the one kept up to date with the code. The French
[README.md](README.md) is the primary version.

- `docs/Mise en place NLL sur Seiscomp.pdf` (in French): the concepts,
  which do not change with the code — `TRANS`, 1D vs 3D model,
  `VGGRID`/`LOCGRID` grids, what installing a profile on OAR does (scolv,
  screloc, scrtdd), line-by-line explanation of the parameters
  (`vel2grid.in`, `grid2time.in`, `NLL.<profile>.conf`), and the manual
  route with the NonLinLoc programs. Its commands refer to the README.
- `docs/vel2grid_grid2time.in.example`: a commented Vel2Grid + Grid2Time
  file for a 1D model, to understand what `creer_profil.py` writes or to do
  it by hand.
- `modeles_vitesse/`: 1D models ready to pass as `--modele`:
  - `jura.nd`: Jura model;
  - `alpes_labo.txt`: the lab's 4-layer model, used by the SeisComP profile
    `1D_ubaye`, the Mont-Blanc 1D profiles and the first try;
  - `alpes_paul2001.txt`: 7-layer model from Paul et al. (2001), Sismalp
    network (profile `05_ubaye_1D_paul2001`);
  - `auvergne_40km.txt`: "auvergne-40km" model from the LOCSAT tables,
    recovered from the travel times; used for the Ambert swarm (profile
    `05_ambert_1D_auvergne_topo`).

## Tests

```bash
pytest tests/
```

The tests cover the Azimuthal Equidistant projection, the configuration,
the extraction of the largest complete rectangle, the `topo.asc` header,
the conversion of SeisComP XML into NLL picks, the preparation of a local
run, profile creation (model reading, Jura profile geometry) and scrtdd
preparation (waveform windows, routing).

## File structure

```
Loc_ToolBox/
├── README.md                  ← French README
├── README.en.md               ← this file
├── requirements.txt           ← Python dependencies
├── config.example.yaml        ← default configuration, every key documented (versioned)
├── config.yaml                ← machine configuration, optional (not versioned)
├── installer_nll.py           ← downloads and compiles NonLinLoc into <racine>/bin
├── choisir_zone.html          ← map: draw the area, get the creer_profil.py command
├── creer_profil.py            ← new 1D or 3D profile + region configuration
├── nll_run.py                 ← local NLL run: profile × period
├── fetch_picks.py             ← picks for a period from the server (fdsnws)
├── seiscomp_xml_to_obs.py     ← SeisComP picks (already downloaded XML) → NLLOC_OBS
├── profil_vers_seiscomp.py    ← local profile → folder to install in SeisComP (scolv, scrtdd)
├── scrtdd_inputs.py           ← scrtdd relocation from a local run (inputs, profile, LANCER.txt)
├── telecharger_formes_onde.py ← on the server: waveforms for scrtdd (FDSN + archive)
├── segment_from_zones.py      ← 3D model: tiling
├── nll_pipeline.py            ← 3D model: NLL files for each tile, topography
├── nll_common.py              ← shared code (projection, configuration, reading)
├── modeles_vitesse/           ← 1D velocity models (Jura, Alps, Auvergne)
├── modeles_scrtdd/            ← scrtdd settings templates (swarm, region)
├── tests/                     ← unit tests (pytest)
└── docs/                      ← NLL/SeisComP tutorial + example .in file
```
