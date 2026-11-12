"""
profil_vers_seiscomp.py
=======================
Prépare un profil local (creer_profil.py, nll_run.py) pour SeisComP : un
dossier à copier tel quel sur la machine SeisComP, avec le fichier de
contrôle, la topographie, les grilles de temps et les lignes de
configuration pour :
  - le localisateur NonLinLoc (plugin locnll, dans scolv) ;
  - scrtdd : les grilles sont déclarées comme table de temps de trajet
    SeisComP (plugin tttnll de scrtdd, interface NLLGrid), et un profil
    scrtdd du même nom les utilise.

NLL et scrtdd lisent ainsi les mêmes grilles, celles calculées en local,
sans les recalculer. Seules les grilles des stations pointées dans les runs
du profil sont copiées (tous les runs de <run.runs_dir> dont run.yaml
nomme ce profil, ou ceux de --run).

Le fichier de contrôle est autonome : les fichiers qu'il cite (topographie,
y compris celle d'un autre profil) sont copiés dans le dossier et cités par
leur chemin sur la machine SeisComP, ${NLLROOT} remplacé par --nllroot
(locnll n'interprète pas les variables dans le fichier de contrôle).

Vérifications : TRANS du fichier de contrôle identique à celui des grilles
copiées, stations des runs sans grille signalées, aucun chemin local restant.

Sorties (dans <racine>/export_seiscomp/<profil>/, à copier dans
<nllroot>/<profil>/) :
  - NLL.<profil>.conf     : fichier de contrôle NLL
  - topo.asc              : topographie (si le profil en a une)
  - time/                 : grilles de temps (.hdr, .buf) des stations des
                            runs, et grilles du modèle (.mod, exigées par tttnll)
  - scolv-NLL.cfg         : configuration SeisComP complète du plugin, pour
                            une première installation (plugin, NLLROOT, profil)
  - locnll_<profil>.cfg   : lignes du seul profil, à ajouter à un
                            scolv-NLL.cfg existant
  - scrtdd-NLL.cfg        : pour scrtdd, première installation : plugin
                            tttnll, table NLLGrid et profil scrtdd
  - scrtdd_<profil>.cfg   : table et profil scrtdd seuls, à ajouter à une
                            configuration scrtdd qui a déjà tttnll
  - INSTALLER.txt         : commandes à copier, dans l'ordre

Le script ne se connecte pas au serveur et n'écrit rien en base.

Utilisation :
    python profil_vers_seiscomp.py --profil 05_ubaye_1D_topo
    python profil_vers_seiscomp.py --profil 1_jura_1D_topo \\
        --run 1_jura_1D_topo_20180101_20251231
"""

import argparse
import getpass
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from nll_common import AzimuthalEquidistant, load_config, log
from nll_run import keyword_values, read_grid_control, stations_used, time_grid_root


def profile_runs(runs_dir, profil, names=None):
    """Dossiers des runs du profil : ceux de names, sinon tous ceux dont run.yaml nomme profil."""
    runs = []
    for meta_path in sorted(Path(runs_dir).glob("*/run.yaml")):
        meta = yaml.safe_load(meta_path.read_text()) or {}
        if names is not None and meta_path.parent.name not in names:
            continue
        if meta.get("profil") != profil:
            if names is not None:
                raise SystemExit(f"Le run {meta_path.parent.name} est du profil {meta.get('profil')}, "
                                 f"pas {profil}")
            continue
        runs.append(meta_path.parent)
    missing = set(names or []) - {r.name for r in runs}
    if missing:
        raise SystemExit(f"Runs introuvables dans {runs_dir} : {', '.join(sorted(missing))}")
    return runs


def run_stations(run_dir):
    """Stations pointées d'un run : fichier de pointés de run.yaml, sinon phases.csv."""
    meta = yaml.safe_load((Path(run_dir) / "run.yaml").read_text()) or {}
    obs = meta.get("pointes")
    if obs and Path(obs).exists():
        return set().union(*stations_used(obs).values())
    phases = Path(run_dir) / "phases.csv"
    if phases.exists():
        return set(pd.read_csv(phases, usecols=["station"])["station"])
    raise SystemExit(f"Ni pointés ni phases.csv pour le run {run_dir}")


def grid_files(grid_root, stations):
    """
    Fichiers des grilles (.time/.angle, .hdr/.buf, P et S) des stations, et
    stations sans aucune grille.
    """
    grid_root = Path(grid_root)
    files, without = [], []
    for s in sorted(stations):
        found = sorted(grid_root.parent.glob(f"{grid_root.name}.[PS].{s}.*.hdr"))
        found = [f for hdr in found for f in (hdr, hdr.with_suffix(".buf")) if f.exists()]
        if found:
            files += found
        else:
            without.append(s)
    return files, without


def model_files(grid_root):
    """Grilles du modèle (<préfixe>.P.mod.*, <préfixe>.S.mod.*), à côté des grilles de temps."""
    grid_root = Path(grid_root)
    return sorted(grid_root.parent.glob(f"{grid_root.name}.[PS].mod.*"))


def hdr_trans(hdr_path):
    """(LatOrig, LongOrig, RotCW) de la ligne TRANSFORM d'un .hdr de grille."""
    text = Path(hdr_path).read_text()
    m = re.search(r"LatOrig\s+(\S+)\s+LongOrig\s+(\S+)\s+RotCW\s+(\S+)", text)
    if not m:
        raise SystemExit(f"Pas de TRANSFORM AZIMUTHAL_EQUIDIST lisible dans {hdr_path}")
    return tuple(float(v) for v in m.groups())


def check_trans(conf_lines, hdrs, tol=1e-4):
    """Arrête si le TRANS du fichier de contrôle diffère de celui d'une grille."""
    trans = keyword_values(conf_lines, "TRANS")
    if not trans or trans[0] != "AZIMUTHAL_EQUIDIST":
        raise SystemExit(f"TRANS AZIMUTHAL_EQUIDIST attendu dans le fichier de contrôle : {trans}")
    ref = (float(trans[2]), float(trans[3]), float(trans[4]))
    for hdr in hdrs:
        if not np.allclose(hdr_trans(hdr), ref, atol=tol):
            raise SystemExit(f"TRANS du profil {ref} différent de celui de {hdr.name} "
                             f"{hdr_trans(hdr)} : grilles d'un autre profil ?")


def export_conf(conf_path, profils_dir, remote_dir, out_dir):
    """
    Fichier de contrôle pour la machine SeisComP : chaque fichier cité par
    ${NLLROOT}/… est copié dans out_dir et cité par remote_dir/<nom>.
    Renvoie (lignes, fichiers copiés).
    """
    lines, copied = [], []
    for raw in Path(conf_path).read_text().splitlines():
        words = []
        for word in raw.split(" "):
            if "${NLLROOT}" in word:
                local = Path(word.replace("${NLLROOT}", str(profils_dir)))
                if not local.exists():
                    raise SystemExit(f"Fichier cité par {conf_path.name} introuvable : {local}")
                shutil.copy2(local, out_dir / local.name)
                copied.append(local.name)
                word = f"{remote_dir}/{local.name}"
            words.append(word)
        lines.append(" ".join(words))
    return lines, copied


def locgrid_region(conf_lines):
    """Rectangle géographique (lat_min, lon_min, lat_max, lon_max) de LOCGRID, au centième près vers l'extérieur."""
    trans = keyword_values(conf_lines, "TRANS")
    nx, ny, _, x0, y0, _, dx, dy, _ = (float(v) for v in keyword_values(conf_lines, "LOCGRID")[:9])
    x1, y1 = x0 + (nx - 1) * dx, y0 + (ny - 1) * dy
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    xs = [x0, xm, x1, x0, x1, x0, xm, x1]
    ys = [y0, y0, y0, ym, ym, y1, y1, y1]
    lon, lat = AzimuthalEquidistant(float(trans[3]), float(trans[2])).inverse(xs, ys)
    return (float(np.floor(lat.min() * 100) / 100), float(np.floor(lon.min() * 100) / 100),
            float(np.ceil(lat.max() * 100) / 100), float(np.ceil(lon.max() * 100) / 100))


def profile_block(profil, grid_prefix, region):
    """Lignes NonLinLoc.profile.<profil>.* de la configuration SeisComP."""
    p = f"NonLinLoc.profile.{profil}"
    return "\n".join([
        f"{p}.earthModelID = {profil}",
        f"{p}.tablePath = ${{NLLROOT}}/{profil}/time/{grid_prefix}",
        f"{p}.controlFile = ${{NLLROOT}}/{profil}/NLL.{profil}.conf",
        f"{p}.stationNameFormat = @STA@",
        f"{p}.region = {region[0]:.2f}, {region[1]:.2f}, {region[2]:.2f}, {region[3]:.2f}",
    ]) + "\n"


def scrtdd_block(profil, table_path, region):
    """Table NLLGrid du profil et profil scrtdd qui l'utilise (chemins complets)."""
    t, p = f"ttt.NLLGrid.{profil}", f"profile.{profil}"
    return "\n".join([
        f"{t}.tablePath = {table_path}",
        f"{p}.tableType = NLLGrid",
        f"{p}.tableModel = {profil}",
        f"{p}.regionType = RECTANGULAR",
        f"{p}.region = {region[0]:.2f}, {region[1]:.2f}, {region[2]:.2f}, {region[3]:.2f}",
    ]) + "\n"


def scrtdd_cfg(profil, block):
    """scrtdd-NLL.cfg d'une première installation : plugin tttnll, liste des tables, un profil."""
    return "\n".join([
        "# Grilles NLL comme table de temps de trajet SeisComP (plugin tttnll de",
        "# scrtdd) et profil scrtdd qui les utilise, écrits par",
        "# profil_vers_seiscomp.py (NonLinLoc_ToolBox). Voir INSTALLER.txt.",
        "plugins = ${plugins}, tttnll",
        f"ttt.NLLGrid.tables = {profil}",
        "",
    ]) + block


def scolv_cfg(profil, nllroot, block, pick_error):
    """
    scolv-NLL.cfg d'une première installation : plugin, chemins, incertitude
    des pointés qui n'en ont pas (celle de nll_run.py, phases.default_error_s ;
    0,5 s par défaut dans le plugin), un profil.
    """
    return "\n".join([
        "# Configuration du plugin NonLinLoc (locnll) pour scolv, écrite par",
        "# profil_vers_seiscomp.py (NonLinLoc_ToolBox). Ajoutée à une copie de",
        "# scolv-PROD.cfg : voir INSTALLER.txt.",
        "plugins = ${plugins}, locnll",
        f"NLLROOT = {nllroot}",
        "NonLinLoc.outputPath = ${NLLROOT}/output/",
        "# Incertitude (s) des pointés sans incertitude, comme en local",
        f"NonLinLoc.defaultPickError = {pick_error:g}",
        "",
        "# Profils disponibles (ordre = priorité pour une recherche automatique)",
        f"NonLinLoc.profiles = {profil}",
        "",
    ]) + block


def installer_text(profil, login, nllroot, out_dir, n_stations):
    """INSTALLER.txt : commandes à copier, sans commentaires (zsh)."""
    remote = f"{login}:{nllroot}/{profil}/"
    return f"""Installation du profil {profil} dans scolv (plugin NonLinLoc)
{'=' * (52 + len(profil))}
Dossier préparé par profil_vers_seiscomp.py : fichier de contrôle, grilles de
temps de {n_stations} stations, configuration. Rien n'est écrit en base.

1. Copier le dossier sur la machine SeisComP (depuis cette machine) :

ssh {login} "mkdir -p {nllroot}/output"
rsync -avz {out_dir}/ {remote}

2. Sur la machine SeisComP, configuration de scolv.

   Première installation (pas encore de ~/.seiscomp/scolv-NLL.cfg) : copie
   de la configuration habituelle, puis ajout du plugin et du profil.

cp ~/.seiscomp/scolv-PROD.cfg ~/.seiscomp/scolv-NLL.cfg
cat {nllroot}/{profil}/scolv-NLL.cfg >> ~/.seiscomp/scolv-NLL.cfg

   Profil ajouté à un scolv-NLL.cfg existant : lignes du profil, puis son
   nom ajouté à la liste NonLinLoc.profiles.

cat {nllroot}/{profil}/locnll_{profil}.cfg >> ~/.seiscomp/scolv-NLL.cfg
sed -i 's/^NonLinLoc.profiles = .*/&, {profil}/' ~/.seiscomp/scolv-NLL.cfg
grep "^NonLinLoc.profiles" ~/.seiscomp/scolv-NLL.cfg

3. Lancer scolv avec cette configuration :

./LaunchScolv.bash NLL

4. Essai : ouvrir un événement de la zone, choisir le localisateur
   NonLinLoc et le profil {profil}, puis Relocate. Comparer à la
   localisation locale du même événement (runs/<run>/<run>.hyp).

5. scrtdd avec les mêmes grilles (plugin tttnll). Vérifier qu'il est là :

ls ~/seiscomp/share/plugins | grep tttnll

   Première installation (pas encore de tttnll dans ~/.seiscomp/scrtdd.cfg) :

cat {nllroot}/{profil}/scrtdd-NLL.cfg >> ~/.seiscomp/scrtdd.cfg

   Profil ajouté à une configuration qui a déjà tttnll : table et profil,
   puis le nom ajouté à la liste ttt.NLLGrid.tables.

cat {nllroot}/{profil}/scrtdd_{profil}.cfg >> ~/.seiscomp/scrtdd.cfg
sed -i 's/^ttt.NLLGrid.tables = .*/&, {profil}/' ~/.seiscomp/scrtdd.cfg
grep "^ttt.NLLGrid.tables" ~/.seiscomp/scrtdd.cfg

   Le profil scrtdd {profil} ne règle que la table de temps et la région :
   les autres réglages gardent leur valeur par défaut. On l'appelle avec
   --profile {profil}, par exemple avec --reloc-catalog.
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prépare un profil local pour le plugin NonLinLoc de SeisComP (scolv).",
        epilog="Exemple : python profil_vers_seiscomp.py --profil 05_ubaye_1D_topo",
    )
    parser.add_argument("--profil", required=True, help="Nom du profil (dossier de run.profils_dir)")
    parser.add_argument("--run", action="append", metavar="NOM",
                        help="Run dont prendre les stations (répétable ; défaut : tous les runs du profil)")
    parser.add_argument("--utilisateur", default=getpass.getuser(),
                        help="Identifiant sur la machine SeisComP (défaut : celui de cette machine)")
    parser.add_argument("--hote", default="ist-oar",
                        help="Machine SeisComP (défaut : ist-oar)")
    parser.add_argument("--nllroot",
                        help="Dossier des profils sur la machine SeisComP "
                             "(défaut : /home/<utilisateur>/.seiscomp/nll)")
    parser.add_argument("--force", action="store_true",
                        help="Écraser un export existant du même profil")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "config.yaml"),
        help="Chemin vers le fichier de configuration YAML (défaut : config.yaml)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    profils_dir = Path(config["run"]["profils_dir"])
    profile_dir = profils_dir / args.profil
    conf_path = profile_dir / f"NLL.{args.profil}.conf"
    if not conf_path.exists():
        raise SystemExit(f"Configuration du profil introuvable : {conf_path}")
    nllroot = (args.nllroot or f"/home/{args.utilisateur}/.seiscomp/nll").rstrip("/")
    remote_dir = f"{nllroot}/{args.profil}"
    out_dir = Path(config["racine"]) / "export_seiscomp" / args.profil
    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"{out_dir} existe déjà (--force pour l'écraser)")
        shutil.rmtree(out_dir)
    (out_dir / "time").mkdir(parents=True)

    log(f"Profil {args.profil} → {args.utilisateur}@{args.hote}:{remote_dir}")
    runs = profile_runs(config["run"]["runs_dir"], args.profil, args.run)
    if not runs:
        raise SystemExit(f"Aucun run du profil {args.profil} dans {config['run']['runs_dir']} "
                         "(nll_run.py d'abord, ou --run)")
    stations = set().union(*(run_stations(r) for r in runs))
    log(f"{len(runs)} runs, {len(stations)} stations pointées : {', '.join(r.name for r in runs)}", 1)

    grid_root = time_grid_root(profile_dir, read_grid_control(profile_dir, profils_dir))
    files, without = grid_files(grid_root, stations)
    if without:
        log(f"⚠ {len(without)} stations sans grille (ignorées par NLL, comme en local) : "
            f"{', '.join(without)}", 1)
    if not files:
        raise SystemExit(f"Aucune grille de temps pour ces stations dans {grid_root.parent}")

    models = model_files(grid_root)
    if not models:
        log(f"⚠ Pas de grilles du modèle ({grid_root.name}.P.mod.*) à côté des grilles de temps : "
            "NLL fonctionnera, pas scrtdd (tttnll)", 1)
    lines, copied = export_conf(conf_path, profils_dir, remote_dir, out_dir)
    check_trans(lines, [f for f in files + models if f.suffix == ".hdr"])
    files += models
    for f in files:
        shutil.copy2(f, out_dir / "time" / f.name)
    size = sum(f.stat().st_size for f in files) / 1e6
    log(f"{len(files)} fichiers de grilles ({size:.0f} Mo), {', '.join(copied) or 'pas de fichier'} "
        "cité par le fichier de contrôle", 1)
    (out_dir / conf_path.name).write_text("\n".join(lines) + "\n")

    region = locgrid_region(lines)
    block = profile_block(args.profil, grid_root.name, region)
    (out_dir / f"locnll_{args.profil}.cfg").write_text(block)
    pick_error = (config["phases"].get("default_error_s") or {}).get("P", 0.02)
    (out_dir / "scolv-NLL.cfg").write_text(scolv_cfg(args.profil, nllroot, block, pick_error))
    dd_block = scrtdd_block(args.profil, f"{remote_dir}/time/{grid_root.name}", region)
    (out_dir / f"scrtdd_{args.profil}.cfg").write_text(dd_block)
    (out_dir / "scrtdd-NLL.cfg").write_text(scrtdd_cfg(args.profil, dd_block))
    n_stations = len(stations) - len(without)
    (out_dir / "INSTALLER.txt").write_text(
        installer_text(args.profil, f"{args.utilisateur}@{args.hote}", nllroot, out_dir, n_stations))

    local = [p.name for p in out_dir.iterdir() if p.is_file() and p.suffix in (".conf", ".cfg")
             and re.search(re.escape(str(Path(config["racine"]))) + "|/Users/", p.read_text())]
    if local:
        raise SystemExit(f"Chemins locaux restants dans {', '.join(local)}")
    log(f"→ {out_dir} (commandes : INSTALLER.txt)", 1)
    log("Terminé.")


if __name__ == "__main__":
    main()
