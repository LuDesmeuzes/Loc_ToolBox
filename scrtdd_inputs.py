"""
scrtdd_inputs.py
================
Prépare un essai scrtdd (relocalisation double différence) à partir d'un
run NLL local (nll_run.py) : les entrées de scrtdd, le profil scrtdd de
l'essai et les commandes pour le lancer sur la machine SeisComP. Les
positions de départ sont les localisations du run, les pointés ceux des XML
SeisComP téléchargés pour le run (cache de fetch_picks.py).

scrtdd lit les trois CSV à la place d'une liste d'origines de la base
(eventlist de sclistorg) : on relocalise ainsi sur le serveur des
localisations qui n'existent qu'en local, avec les mêmes grilles de temps
que NLL (plugin tttnll, installé par profil_vers_seiscomp.py).

Réglages : un modèle d'essai (modeles_scrtdd/<modèle>.yaml, ou un fichier
YAML au même format) donne le tri des événements (section entrees) et les
paramètres du profil scrtdd (section profil, noms de scrtdd 2.x). --set
change une valeur pour cet essai seulement ; les valeurs effectives sont
écrites dans essai.yaml, avec le run, la période et les comptes.

Événements gardés : localisés par NLLoc (LOCATED), avec un PUBLIC_ID, sur la
période --debut / --fin si elle est donnée, de RMS ≤ entrees.rms_max et avec
au moins entrees.phases_min phases. Phases gardées : celles utilisées par
l'origine de référence (comme pour le run NLL), sans les stations exclues du
run (--exclure-hors-modele de nll_run.py) ni celles absentes de l'inventaire.

Avec --origines reference, les positions de départ sont celles de l'origine
de référence (evenements.csv du run, en général le LOCSAT manuel) au lieu
des localisations NLL : mêmes événements, mêmes phases et mêmes stations,
pour comparer les deux points de départ de la double différence.

Sorties (dans <run.runs_dir>/<run>/scrtdd/<essai>/, ou --sortie) :
  - station.csv   : latitude,longitude,elevation (m),networkCode,stationCode,locationCode
  - event.csv     : id,isotime,latitude,longitude,depth (km),magnitude
                    (id = 1, 2, … ; magnitude 0 si absente de l'export fdsnws)
  - phase.csv     : eventId,isotime,lowerUncertainty,upperUncertainty,type,
                    networkCode,stationCode,locationCode,channelCode
                    (incertitudes « nan » si le pointé n'en a pas)
  - eventlist_<run>.csv : une ligne par événement, dans l'ordre des id
                    (origin = origine de référence dont viennent les pointés,
                    event = Event ID SeisComP) : LocQuality (ScrtddRun) s'en
                    sert pour relier les id scrtdd aux Event ID.
  - scrtdd_<essai>.cfg : le profil scrtdd de l'essai (profile.<essai>.*), à
                    ajouter à ~/.seiscomp/scrtdd.cfg
  - essai.yaml    : run, période, modèle, modifications (--set), valeurs
                    effectives, comptes, machine et dossier distant
  - LANCER.txt    : commandes à copier, dans l'ordre (copie, profil, formes
                    d'onde, scrtdd, vérification, rapatriement)
  - formes_onde_NN.post : les formes d'onde utiles à la corrélation croisée,
                    au format POST des services FDSN (« réseau station
                    location canaux début fin ») : une fenêtre par événement
                    et par station pointée, de --marge-avant s avant le
                    premier pointé à --marge-apres s après le dernier, les 3
                    composantes (HH?). 2000 fenêtres au plus par fichier.
  - telecharger_formes_onde.py : copie du script du dépôt, à lancer sur le
                    serveur pour rassembler ces fenêtres dans une archive SDS
                    dédiée (voir sa docstring).

Les positions des stations viennent de l'inventaire SeisComP
(fdsnws-station), valides sur la période du run. Les sorties de scrtdd
(reloc-event.csv…) sont rapatriées dans le dossier de l'essai, à côté de
l'eventlist : les analyses dd_* de LocQuality le lisent directement.

Le script ne se connecte pas au serveur et n'écrit rien en base.

Utilisation :
    python scrtdd_inputs.py --run 05_ubaye_1D_topo_20230514_20250630 --essai ubaye_dec24 \\
        --debut 2024-12-01 --fin 2025-02-28
    python scrtdd_inputs.py --run <run> --essai jura_v5 --modele region
    python scrtdd_inputs.py --run <run> --essai ubaye_dec24_amorti --debut 2024-12-01 \\
        --fin 2025-02-28 --set solver.dampingFactor=0.05 --set entrees.rms_max=0.3
    python scrtdd_inputs.py --run <run> --essai ubaye_sans_cc --set crossCorrelation.enable=false
    python scrtdd_inputs.py --run <run> --essai ubaye_locsat --origines reference
"""

import argparse
import csv
import difflib
import getpass
import io
import math
import re
import shutil
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from fetch_picks import days_between
from nll_common import load_config, log, read_hyp
from profil_vers_seiscomp import locgrid_region
from seiscomp_xml_to_obs import read_xml_files

STATION_COLUMNS = ["latitude", "longitude", "elevation", "networkCode", "stationCode",
                   "locationCode"]
EVENT_COLUMNS = ["id", "isotime", "latitude", "longitude", "depth", "magnitude"]
PHASE_COLUMNS = ["eventId", "isotime", "lowerUncertainty", "upperUncertainty", "type",
                 "networkCode", "stationCode", "locationCode", "channelCode"]

# Fenêtres par fichier POST (requêtes de taille raisonnable pour les services FDSN)
POST_CHUNK = 2000

# Script de téléchargement (dépôt), copié à côté des fichiers POST
WAVEFORM_SCRIPT = Path(__file__).resolve().parent / "telecharger_formes_onde.py"

# Modèles d'essai livrés avec le dépôt (--modele <nom>)
MODELS_DIR = Path(__file__).resolve().parent / "modeles_scrtdd"


def isotime(t):
    """datetime (UTC, naïf ou non) → 2024-05-14T12:34:15.229646Z"""
    return t.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"


def unc(value):
    return "nan" if value is None else f"{value:g}"


def station_inventory(url, stations, debut, fin):
    """
    Positions des stations (fdsnws-station, niveau station) valides sur la
    période : {(réseau, station): (lat, lon, altitude en m)}.
    """
    params = {"station": ",".join(sorted({s for _, s in stations})), "level": "station",
              "format": "text", "starttime": debut.isoformat(),
              "endtime": (fin + timedelta(days=1)).isoformat()}
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=120) as resp:
        text = resp.read().decode() if resp.status != 204 else ""
    if not text.strip():
        return {}
    inv = pd.read_csv(io.StringIO(text), sep="|")
    inv.columns = [c.strip().lstrip("#") for c in inv.columns]
    inv = inv.drop_duplicates(["Network", "Station"])
    return {(r.Network, r.Station): (r.Latitude, r.Longitude, r.Elevation)
            for r in inv.itertuples()}


def select_events(hyp_events, debut=None, fin=None, rms_max=None):
    """
    Événements localisés, avec PUBLIC_ID, dans la période et de RMS ≤ rms_max
    (s, si donné), triés par temps.
    """
    keep = [e for e in hyp_events if e["status"] == "LOCATED" and e["event_id"]]
    if rms_max is not None:
        keep = [e for e in keep if e.get("rms") is not None and e["rms"] <= rms_max]
    if debut:
        keep = [e for e in keep if e["time"].date() >= debut]
    if fin:
        keep = [e for e in keep if e["time"].date() <= fin]
    return sorted(keep, key=lambda e: e["time"])


def reference_positions(events, evenements_csv):
    """
    Mêmes événements (et même ordre) que events, avec la position et le temps
    de l'origine de référence lus dans evenements.csv. Les événements sans
    origine de référence complète sont ignorés.
    """
    ref = pd.read_csv(evenements_csv).dropna(subset=["origin_time", "latitude", "longitude", "depth"])
    ref = ref.drop_duplicates("event_id").set_index("event_id")
    out = []
    for ev in events:
        if ev["event_id"] not in ref.index:
            continue
        r = ref.loc[ev["event_id"]]
        out.append({**ev, "time": datetime.fromisoformat(r["origin_time"].replace("Z", "+00:00")),
                    "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
                    "depth": float(r["depth"])})
    return out


def build_tables(events, xml_events, excluded, min_phases=1):
    """
    Lignes de event.csv, phase.csv et de l'eventlist (dicts), et l'ensemble
    des (réseau, station, location) pointés. Les événements avec moins de
    min_phases pointés dans les XML (aucun par défaut) sont ignorés.
    """
    ev_rows, ph_rows, el_rows, stations = [], [], [], set()
    for ev in events:
        xml = xml_events.get(ev["event_id"])
        phases = [p for p in (xml or {}).get("phases", []) if p["station"] not in excluded]
        if not phases or len(phases) < min_phases:
            continue
        k = len(ev_rows) + 1
        mag = xml.get("magnitude")
        ev_rows.append({"id": k, "isotime": isotime(ev["time"]),
                        "latitude": f"{ev['latitude']:.6f}", "longitude": f"{ev['longitude']:.6f}",
                        "depth": f"{ev['depth']:.4f}",
                        "magnitude": f"{mag:.2f}" if mag is not None else "0"})
        el_rows.append({"origin": xml["origin_id"], "event": ev["event_id"]})
        for p in phases:
            ph_rows.append({"eventId": k, "isotime": isotime(p["time"]),
                            "lowerUncertainty": unc(p["lower_s"]),
                            "upperUncertainty": unc(p["upper_s"]),
                            "type": p["phase"], "networkCode": p["network"],
                            "stationCode": p["station"], "locationCode": p["location"],
                            "channelCode": p["channel"]})
            stations.add((p["network"], p["station"], p["location"]))
    return ev_rows, ph_rows, el_rows, stations


def waveform_windows(ph_rows, before_s=20.0, after_s=40.0):
    """
    Fenêtres de formes d'onde à télécharger, au format POST des services FDSN
    (« NET STA LOC CHA début fin », LOC vide → --, CHA = les 3 composantes) :
    une par événement et par station pointée, de before_s avant le premier
    pointé à after_s après le dernier (bruit avant la P, coda après la S).
    """
    span = {}
    for r in ph_rows:
        t = datetime.fromisoformat(r["isotime"].replace("Z", "+00:00"))
        key = (r["eventId"], r["networkCode"], r["stationCode"],
               r["locationCode"] or "--", r["channelCode"][:2] + "?")
        lo, hi = span.get(key, (t, t))
        span[key] = (min(lo, t), max(hi, t))
    fmt = "%Y-%m-%dT%H:%M:%S"
    return [f"{net} {sta} {loc} {cha} "
            f"{(lo - timedelta(seconds=before_s)).strftime(fmt)} "
            f"{(hi + timedelta(seconds=after_s)).strftime(fmt)}"
            for (_, net, sta, loc, cha), (lo, hi) in sorted(span.items())]


def write_waveform_requests(out_dir, windows):
    """formes_onde_NN.post (POST_CHUNK fenêtres au plus) et telecharger_formes_onde.py."""
    for old in out_dir.glob("formes_onde_*.post"):
        old.unlink()
    for k in range(0, len(windows), POST_CHUNK):
        part = out_dir / f"formes_onde_{k // POST_CHUNK + 1:02d}.post"
        part.write_text("\n".join(windows[k:k + POST_CHUNK]) + "\n")
    shutil.copy(WAVEFORM_SCRIPT, out_dir / WAVEFORM_SCRIPT.name)
    return -(-len(windows) // POST_CHUNK)


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)




# ─────────────────────────────────────────────────────────────────────────────
# ESSAI : MODÈLE, PROFIL SCRTDD, COMMANDES
# ─────────────────────────────────────────────────────────────────────────────

# Nom d'essai = nom du profil scrtdd (clé de configuration SeisComP)
ESSAI_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def load_model(name):
    """Modèle d'essai : modeles_scrtdd/<name>.yaml du dépôt, ou un chemin vers un fichier YAML."""
    path = Path(name).expanduser()
    if not path.suffix:
        path = MODELS_DIR / f"{name}.yaml"
    if not path.exists():
        names = sorted(p.stem for p in MODELS_DIR.glob("*.yaml"))
        raise SystemExit(f"Modèle d'essai introuvable : {path} (modèles du dépôt : {', '.join(names)})")
    model = yaml.safe_load(path.read_text()) or {}
    model["entrees"] = model.get("entrees") or {}
    model["profil"] = model.get("profil") or {}
    return path, model


def cfg_value(value):
    """Valeur au format des fichiers de configuration SeisComP (listes séparées par des virgules)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(cfg_value(v) for v in value)
    text = "" if value is None else str(value)
    # Guillemets dès qu'un caractère pourrait être mal lu (virgule d'un filtre…)
    return f'"{text}"' if re.search(r"[^\w.+-]", text) else text


def apply_overrides(model, sets):
    """
    Applique les --set clé=valeur au modèle : entrees.<nom> pour le tri des
    événements, sinon un paramètre du profil. La clé doit exister dans le
    modèle (scrtdd ignorerait en silence une faute de frappe) ; la valeur est
    lue comme en YAML (0.05, false, [10, 5]). Renvoie les modifications.
    """
    changes = []
    for item in sets or []:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise SystemExit(f"--set attend clé=valeur : {item}")
        section, name = ("entrees", key[len("entrees."):]) if key.startswith("entrees.") else ("profil", key)
        params = model[section]
        if name not in params:
            known = [f"entrees.{k}" for k in model["entrees"]] + list(model["profil"])
            close = difflib.get_close_matches(key, known, n=3)
            raise SystemExit(f"Paramètre absent du modèle : {key}"
                             + (f" (voulu : {', '.join(close)} ?)" if close else "")
                             + ". Pour en ajouter un, copier le modèle et passer --modele <copie>")
        value = yaml.safe_load(raw) if raw.strip() else None
        changes.append(f"{key} = {cfg_value(params[name])} → {cfg_value(value)}")
        params[name] = value
    return changes


def profile_cfg(name, params, table_model, region, header):
    """
    Lignes profile.<name>.* de scrtdd.cfg : la table NLLGrid du profil NLL
    (déclarée par profil_vers_seiscomp.py) et la région de sa grille de
    recherche, puis les paramètres du modèle, qui peuvent les remplacer.
    """
    base = {"tableType": "NLLGrid", "tableModel": table_model, "regionType": "RECTANGULAR",
            "region": [f"{v:.2f}" for v in region]}
    lines = [f"# {line}".rstrip() for line in header]
    lines += [f"profile.{name}.{k} = {cfg_value(v)}" for k, v in {**base, **params}.items()]
    return "\n".join(lines) + "\n"


def lancer_text(essai, run, debut, fin, modele, changes, counts, login, remote, out_dir,
                archive, profil, n_profile_lines, cross_correlation):
    """LANCER.txt : commandes à copier, sans commentaires (zsh), dans l'ordre."""
    cmd = (f"seiscomp exec scrtdd --reloc-catalog station.csv,event.csv,phase.csv "
           f"--profile {essai} --dump-diagnostics --verbosity=3 --console=1 -d \"$BASE\"")
    mods = f", modifié par --set : {'; '.join(changes)}" if changes else ""
    if cross_correlation:
        waveforms = f"""3. Formes d'onde pour la corrélation croisée ({counts['fenetres']} fenêtres). Si l'archive de
   la machine les a toutes, passer à l'étape 4. Sinon (le log de l'étape 5
   le dit : « not available »), les rassembler dans une archive dédiée,
   commune aux essais du run ; les réseaux qu'aucun centre public ne sert
   sont pris dans l'archive de la machine avec --archive-serveur (voir
   telecharger_formes_onde.py) :

cd {remote}
python3 telecharger_formes_onde.py --archive {archive}
"""
        with_archive = f"""
   Avec l'archive dédiée de l'étape 3 :

{cmd} -I sdsarchive://{archive} 2>&1 | tee scrtdd.log
"""
    else:
        waveforms = """3. Pas de corrélation croisée (crossCorrelation.enable = false) : pas de
   formes d'onde à rassembler.
"""
        with_archive = ""
    title = f"Essai scrtdd {essai} : run {run}, du {debut} au {fin}"
    return f"""{title}
{'=' * len(title)}
Préparé par scrtdd_inputs.py le {date.today().isoformat()} : {counts['evenements']} événements, {counts['phases']} phases,
{counts['stations']} stations. Modèle {modele}{mods}.
Réglages effectifs : essai.yaml. Pour en changer, relancer scrtdd_inputs.py
avec --set … --force plutôt que de modifier les fichiers sur le serveur :
essai.yaml doit dire ce qui a tourné.

0. Prérequis, une fois par profil NLL : le profil {profil} installé avec
   profil_vers_seiscomp.py (étape 5 de son INSTALLER.txt : plugin tttnll et
   table {profil}). Sur la machine SeisComP, la ligne doit citer {profil} :

grep "^ttt.NLLGrid.tables" ~/.seiscomp/scrtdd.cfg

1. Copier l'essai (depuis cette machine) :

ssh {login} "mkdir -p {remote}"
rsync -avz {out_dir}/ {login}:{remote}/

2. Sur la machine SeisComP, ajouter le profil {essai} à la configuration de
   scrtdd (une seule fois ; le compte doit donner {n_profile_lines}) :

grep -q "^profile.{essai}\\." ~/.seiscomp/scrtdd.cfg || cat {remote}/scrtdd_{essai}.cfg >> ~/.seiscomp/scrtdd.cfg
grep -c "^profile.{essai}\\." ~/.seiscomp/scrtdd.cfg

{waveforms}
4. Connexion à la base (inventaire des stations : orientation des
   composantes pour la corrélation croisée). La deuxième commande doit
   afficher une adresse du type mysql://…@…/seiscomp :

BASE=$(grep -h "^database *=" ~/.seiscomp/scolv-PROD.cfg ~/.seiscomp/global.cfg 2>/dev/null | head -1 | cut -d= -f2- | xargs)
echo "$BASE"

5. Relocalisation (seiscomp exec charge l'environnement de SeisComP, sans
   quoi le plugin tttnll est introuvable) :

cd {remote}
{cmd} 2>&1 | tee scrtdd.log
{with_archive}
6. Vérifications : les valeurs d'essai.yaml doivent apparaître dans le log ;
   nombre d'événements relocalisés (sur {counts['evenements']}) ; formes d'onde manquantes
   (0 attendu avec la corrélation croisée) :

grep -i -E "dampingFactor|absoluteLocationConstraint|minCCCoef|maxInterEventDistance" scrtdd.log | head -20
grep -c ",true," reloc-event.csv
grep -c -i "not available" scrtdd.log

7. Rapatrier les sorties dans le dossier de l'essai (depuis cette machine) :

rsync -avz --exclude mseed/ {login}:{remote}/ {out_dir}/

   Pour l'analyser avec LocQuality_ToolBox, ajouter l'essai à
   compare.scrtdd_runs de son config.yaml :
   {essai}: "{out_dir}"
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prépare un essai scrtdd (entrées, profil, commandes) à partir d'un run NLL local."
    )
    parser.add_argument("--run", required=True, help="Nom du run (dossier de run.runs_dir)")
    parser.add_argument("--essai", required=True,
                        help="Nom de l'essai, qui est aussi celui du profil scrtdd "
                             "(lettres, chiffres et _, ex. ubaye_dec24)")
    parser.add_argument("--modele", default="essaim",
                        help="Modèle d'essai : essaim (défaut), region, ou chemin d'un fichier YAML")
    parser.add_argument("--set", action="append", metavar="CLE=VALEUR",
                        help="Change une valeur du modèle pour cet essai (répétable), ex. "
                             "solver.dampingFactor=0.05 ou entrees.rms_max=0.3")
    parser.add_argument("--debut", type=date.fromisoformat,
                        help="Premier jour gardé (AAAA-MM-JJ, défaut : début du run)")
    parser.add_argument("--fin", type=date.fromisoformat,
                        help="Dernier jour gardé, inclus (AAAA-MM-JJ, défaut : fin du run)")
    parser.add_argument("--origines", choices=["nll", "reference"], default="nll",
                        help="Positions de départ : localisations NLL du run (défaut) ou "
                             "origines de référence de evenements.csv (LOCSAT)")
    parser.add_argument("--marge-avant", type=float, default=20.0,
                        help="Formes d'onde : secondes avant le premier pointé (défaut : 20)")
    parser.add_argument("--marge-apres", type=float, default=40.0,
                        help="Formes d'onde : secondes après le dernier pointé (défaut : 40)")
    parser.add_argument("--utilisateur", default=getpass.getuser(),
                        help="Identifiant sur la machine SeisComP (défaut : celui de cette machine)")
    parser.add_argument("--hote", default="ist-oar", help="Machine SeisComP (défaut : ist-oar)")
    parser.add_argument("--dossier-distant",
                        help="Dossier des essais sur la machine SeisComP "
                             "(défaut : /home/<utilisateur>/scrtdd ; l'essai va dans <run>/<essai>/)")
    parser.add_argument("--archive",
                        help="Archive SDS dédiée aux formes d'onde du run "
                             "(défaut : /home/<utilisateur>/sds/<run>)")
    parser.add_argument("--sortie", help="Dossier de sortie (défaut : <run>/scrtdd/<essai>)")
    parser.add_argument("--force", action="store_true",
                        help="Remplacer un essai existant du même nom (sorties rapatriées comprises)")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "config.yaml"),
        help="Chemin vers le fichier de configuration YAML (défaut : config.yaml)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not ESSAI_NAME.match(args.essai):
        raise SystemExit("--essai : lettres, chiffres et _ seulement, en commençant par une lettre "
                         "(c'est aussi le nom du profil scrtdd)")
    model_path, model = load_model(args.modele)
    changes = apply_overrides(model, args.set)
    entrees, params = model["entrees"], model["profil"]

    config = load_config(args.config)
    run_dir = Path(config["run"]["runs_dir"]) / args.run
    meta_path = run_dir / "run.yaml"
    if not meta_path.exists():
        raise SystemExit(f"Run introuvable : {meta_path}")
    meta = yaml.safe_load(meta_path.read_text())
    profil = meta["profil"]
    conf_path = Path(config["run"]["profils_dir"]) / profil / f"NLL.{profil}.conf"
    if not conf_path.exists():
        raise SystemExit(f"Configuration du profil NLL introuvable : {conf_path}")
    debut = args.debut or date.fromisoformat(meta["debut"])
    fin = args.fin or date.fromisoformat(meta["fin"])
    out_dir = Path(args.sortie) if args.sortie else run_dir / "scrtdd" / args.essai
    if out_dir.exists() and any(out_dir.iterdir()):
        if not args.force:
            raise SystemExit(f"L'essai {out_dir} existe déjà (--force pour le remplacer, "
                             "ou un autre --essai)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"Essai {args.essai} : run {args.run}, du {debut} au {fin}, modèle {model_path.stem}")
    for change in changes:
        log(f"--set {change}", 1)
    located = select_events(read_hyp(run_dir / f"{args.run}.hyp"), debut, fin)
    events = select_events(located, rms_max=entrees.get("rms_max"))
    log(f"{len(located)} événements localisés, {len(located) - len(events)} écartés "
        f"(RMS > {entrees.get('rms_max')} s)", 1)
    if args.origines == "reference":
        events = reference_positions(events, run_dir / "evenements.csv")
        log(f"positions de départ : origines de référence ({len(events)} événements)", 1)

    cache_dir = Path(config["fetch"]["cache_dir"])
    files = [cache_dir / f"{d.isoformat()}.xml" for d in days_between(debut, fin)]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"{len(missing)} journées absentes du cache {cache_dir} "
                         f"(ex. {missing[0]}) : relancer fetch_picks.py sur la période")
    xml_events, invalid, _ = read_xml_files(files)
    if invalid:
        log(f"⚠ {len(invalid)} XML illisibles ignorés", 1)
    xml_by_id = {e["event_id"]: e for e in xml_events}

    excluded = set((meta.get("stations_exclues") or {}).get("stations") or [])
    min_phases = entrees.get("phases_min") or 1
    ev_rows, ph_rows, el_rows, stations = build_tables(events, xml_by_id, excluded, min_phases)
    log(f"{len(ev_rows)} événements gardés, {len(events) - len(ev_rows)} écartés "
        f"(moins de {min_phases} phases), {len(ph_rows)} phases"
        + (f" ({len(excluded)} stations exclues du run)" if excluded else ""), 1)

    log("Inventaire des stations")
    inv = station_inventory(config["fetch"]["fdsnws_station_url"],
                            {(n, s) for n, s, _ in stations}, debut, fin)
    # Pointés dont le réseau diffère de l'inventaire (ex. XX.GREVE pour 9W.GREVE) :
    # rattachés au réseau de l'inventaire si le code de station n'y est pas ambigu
    networks = {}
    for net, sta in inv:
        networks.setdefault(sta, []).append(net)
    renamed = {(net, sta): networks[sta][0] for net, sta, _ in stations
               if (net, sta) not in inv and len(networks.get(sta, [])) == 1}
    if renamed:
        n_renamed = 0
        for row in ph_rows:
            new = renamed.get((row["networkCode"], row["stationCode"]))
            if new:
                row["networkCode"] = new
                n_renamed += 1
        stations = {(renamed.get((n, s), n), s, l) for n, s, l in stations}
        log(f"réseau corrigé d'après l'inventaire pour {n_renamed} phases : "
            + ", ".join(f"{n}.{s} → {new}.{s}" for (n, s), new in sorted(renamed.items())), 1)
    st_rows, unknown = [], []
    for net, sta, loc in sorted(stations):
        if (net, sta) not in inv:
            unknown.append(f"{net}.{sta}")
            continue
        lat, lon, elev = inv[(net, sta)]
        st_rows.append({"latitude": f"{lat:.6f}", "longitude": f"{lon:.6f}",
                        "elevation": f"{elev:.1f}" if not math.isnan(elev) else "0",
                        "networkCode": net, "stationCode": sta, "locationCode": loc})
    log(f"{len(st_rows)} stations", 1)
    if unknown:
        # scrtdd refuse tout le catalogue si une phase cite une station absente
        # de station.csv (« unknown station ») : ces phases sont retirées
        n_before = len(ph_rows)
        ph_rows = [r for r in ph_rows if (r["networkCode"], r["stationCode"]) in inv]
        log(f"⚠ absentes de l'inventaire : {', '.join(unknown)} → "
            f"{n_before - len(ph_rows)} phases retirées", 1)

    write_csv(out_dir / "station.csv", STATION_COLUMNS, st_rows)
    write_csv(out_dir / "event.csv", EVENT_COLUMNS, ev_rows)
    write_csv(out_dir / "phase.csv", PHASE_COLUMNS, ph_rows)
    write_csv(out_dir / f"eventlist_{args.run}.csv", ["origin", "event"], el_rows)
    windows = waveform_windows(ph_rows, args.marge_avant, args.marge_apres)
    n_files = write_waveform_requests(out_dir, windows)
    log(f"formes d'onde : {len(windows)} fenêtres en {n_files} fichiers POST "
        f"+ {WAVEFORM_SCRIPT.name}", 1)

    login = f"{args.utilisateur}@{args.hote}"
    remote = f"{(args.dossier_distant or f'/home/{args.utilisateur}/scrtdd').rstrip('/')}/{args.run}/{args.essai}"
    archive = args.archive or f"/home/{args.utilisateur}/sds/{args.run}"
    counts = {"evenements_localises": len(located), "ecartes_rms": len(located) - len(events),
              "ecartes_phases": len(events) - len(ev_rows), "evenements": len(ev_rows), "phases": len(ph_rows), "stations": len(st_rows),
              "fenetres": len(windows)}
    region = locgrid_region(conf_path.read_text().splitlines())
    header = [f"Profil scrtdd de l'essai {args.essai} (run {args.run}, du {debut} au {fin}),",
              f"écrit par scrtdd_inputs.py (Loc_ToolBox) le {date.today().isoformat()}, "
              f"modèle {model_path.stem}.",
              "Réglages et comptes : essai.yaml. Voir LANCER.txt."]
    cfg = profile_cfg(args.essai, params, profil, region, header)
    (out_dir / f"scrtdd_{args.essai}.cfg").write_text(cfg)
    record = {"essai": args.essai, "run": args.run, "profil_nll": profil,
              "debut": debut.isoformat(), "fin": fin.isoformat(), "origines": args.origines,
              "prepare_le": datetime.now().isoformat(timespec="seconds"),
              "modele": str(model_path), "description": model.get("description"),
              "modifications": changes, "comptes": counts,
              "machine": login, "dossier_distant": remote, "archive_formes_onde": archive,
              "entrees": entrees, "profil": params}
    (out_dir / "essai.yaml").write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False))
    n_lines = sum(1 for line in cfg.splitlines() if line.startswith("profile."))
    (out_dir / "LANCER.txt").write_text(
        lancer_text(args.essai, args.run, debut, fin, model_path.stem, changes, counts, login,
                    remote, out_dir, archive, profil, n_lines,
                    bool(params.get("crossCorrelation.enable"))))
    log(f"→ {out_dir} (commandes : LANCER.txt)", 1)


if __name__ == "__main__":
    main()
