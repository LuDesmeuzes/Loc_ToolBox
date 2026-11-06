"""
creer_profil.py
===============
Crée un profil NLL complet pour une nouvelle région à partir d'un modèle de
vitesse 1D, et la configuration de la région pour fetch_picks.py,
nll_run.py et scrtdd_inputs.py.

Le profil est prêt pour `nll_run.py --grilles` : les grilles de temps des
stations sont calculées au premier run, pour les seules stations pointées.

Choix faits automatiquement (modifiables par option) :
  - centre de la projection (TRANS) : milieu de la zone ;
  - grille de recherche (LOCGRID, pas de 1 km) : la zone + --marge km de
    chaque côté, arrondie à 5 km, de -5 km à --prof-max km ;
  - recherche octree (LOCSEARCH OCT) : cellules initiales d'environ
    --cellule km de côté ; nombre de nœuds = 5 × cellules initiales, au
    moins 50 000 ;
  - grilles de temps 2D (Vel2Grid / Grid2Time) au pas --pas km, sur
    --distance-max km et de -5 km à max(60, --prof-max + 10) km ;
  - topographie SRTM (LOCTOPO_SURFACE) sur l'emprise de la grille de
    recherche, sauf --sans-topo (internet nécessaire, package srtm.py).

Modèles de vitesse acceptés :
  - .nd (format TauP) : « profondeur Vp Vs densité » par ligne, une
    discontinuité = deux lignes à la même profondeur ; les lignes de texte
    (mantle, outer-core…) sont ignorées. Entre deux profondeurs, la vitesse
    varie linéairement (gradient NLL) ;
  - texte en couches : « toit Vp Vs [densité] » par ligne (km, km/s),
    vitesses constantes dans chaque couche, commentaires après #.
Les profondeurs sont comptées sous le niveau de la mer ; la première
couche est prolongée jusqu'au toit des grilles (-5 km). Pour un modèle 3D,
utiliser segment_from_zones.py et nll_pipeline.py (voir README).

Sorties :
  - <run.profils_dir>/<nom>/ : NLL.<nom>.conf (localisation), nll_<nom>.in
    (grilles de temps, lu par nll_run.py --grilles), vel2grid_P/S.in,
    model/ (modèle NLL, Vel2Grid), topo.asc, README.txt, time/ (vide)
  - <run.regions_dir>/<region>/config_<region>.yaml : configuration de la
    région (serveur fdsnws, zone, cache des pointés), à passer en --config
    à fetch_picks.py, nll_run.py et scrtdd_inputs.py

Configuration (config.yaml de la machine) : run.profils_dir, run.runs_dir,
run.nlloc (Vel2Grid est cherché à côté), run.regions_dir (défaut :
profils_travail/ à côté de profils_dir), fetch.cache_dir et fetch.obs_dir
(les dossiers de la région sont créés à côté), phases.

Utilisation :
    python creer_profil.py --region jura --nom 1_jura_1D_topo \\
        --modele ../../donnees/modele_vitesse/jura.nd \\
        --lat 46.95 47.55 --lon 5.45 7.55 --pas 1 --prof-max 50 --cellule 4 \\
        --fdsnws http://ist-scjura-sig.u-ga.fr:8080/fdsnws
"""

import argparse
import math
import subprocess
from datetime import date
from pathlib import Path

import yaml

from nll_common import AzimuthalEquidistant, load_config, log

# Toit des grilles (km, négatif = au-dessus du niveau de la mer) : couvre le relief
Z_TOP_KM = -5.0

# Lignes de localisation communes à tous les profils (reprises des profils SeisComP)
LOC_LINES = """LOCSIG NonLinLoc - ISTERRE SIG
LOCMETH EDT_OT_WT 9999.0 4 -1 -1 1.7 -1 -1.0 1
LOCGAU 0.05 0.0
LOCPHASEID  P   P p Pn Pg P1
LOCPHASEID  S   S s Sn Sg S1
LOCQUAL2ERR 0.025 0.050 0.100 0.200 0.400 99999.9
LOCANGLES ANGLES_YES 5"""


# ─────────────────────────────────────────────────────────────────────────────
# MODÈLE DE VITESSE
# ─────────────────────────────────────────────────────────────────────────────

def _numbers(path):
    """Lignes de nombres d'un fichier texte (commentaires # et lignes de texte ignorés)."""
    rows = []
    for raw in Path(path).read_text().splitlines():
        line = raw.split("#", 1)[0].split()
        try:
            rows.append([float(v) for v in line])
        except ValueError:
            continue  # ligne de texte (mantle, outer-core, en-tête…)
    return [r for r in rows if r]


def read_nd(path):
    """
    Modèle .nd (TauP) → couches NLL : liste de dicts {top, vp, vp_grad, vs,
    vs_grad, rho, rho_grad} (gradients par km). Une couche par intervalle de
    profondeur ; la dernière se prolonge au-delà du dernier point.
    """
    pts = [r[:4] + [2.7] * (4 - len(r[:4])) for r in _numbers(path) if len(r) >= 3]
    layers = []
    for (z1, vp1, vs1, r1), (z2, vp2, vs2, r2) in zip(pts, pts[1:]):
        if z2 <= z1:
            continue  # discontinuité : la couche suivante commence ici
        dz = z2 - z1
        layers.append({"top": z1, "vp": vp1, "vp_grad": (vp2 - vp1) / dz,
                       "vs": vs1, "vs_grad": (vs2 - vs1) / dz,
                       "rho": r1, "rho_grad": (r2 - r1) / dz})
    z, vp, vs, rho = pts[-1]
    layers.append({"top": z, "vp": vp, "vp_grad": 0.0, "vs": vs, "vs_grad": 0.0,
                   "rho": rho, "rho_grad": 0.0})
    return layers


def read_layers(path):
    """Modèle texte « toit Vp Vs [densité] » → couches NLL à vitesse constante."""
    layers = []
    for r in _numbers(path):
        if len(r) < 3:
            continue
        layers.append({"top": r[0], "vp": r[1], "vp_grad": 0.0, "vs": r[2], "vs_grad": 0.0,
                       "rho": r[3] if len(r) > 3 else 2.7, "rho_grad": 0.0})
    return sorted(layers, key=lambda l: l["top"])


def read_model(path):
    """Couches NLL du modèle (.nd ou texte en couches), la première partant de Z_TOP_KM."""
    layers = read_nd(path) if Path(path).suffix == ".nd" else read_layers(path)
    if not layers:
        raise SystemExit(f"Aucune couche lue dans {path}")
    for l in layers:
        if not (1.0 < l["vp"] < 10.0 and 0.5 < l["vs"] < l["vp"]):
            raise SystemExit(f"Vitesses invraisemblables dans {path} (km/s attendus) : {l}")
    first = layers[0]
    if first["top"] > Z_TOP_KM:
        if first["vp_grad"] == 0 and first["vs_grad"] == 0:
            first["top"] = Z_TOP_KM  # même vitesse jusqu'au toit des grilles
        else:
            layers.insert(0, {**first, "top": Z_TOP_KM, "vp_grad": 0.0, "vs_grad": 0.0,
                              "rho_grad": 0.0})
    return layers


def layer_lines(layers):
    """Lignes LAYER du fichier Vel2Grid."""
    return [f"LAYER {l['top']:7.1f} {l['vp']:6.2f} {l['vp_grad']:g} {l['vs']:6.2f} "
            f"{l['vs_grad']:g} {l['rho']:5.2f} {l['rho_grad']:g}" for l in layers]


# ─────────────────────────────────────────────────────────────────────────────
# GÉOMÉTRIE
# ─────────────────────────────────────────────────────────────────────────────

def ceil_to(x, step):
    return math.ceil(round(x / step, 9)) * step


def geometry(zone, prof_max, pas, marge_km=10.0, cellule_km=3.0, distance_max_km=400.0):
    """
    Centre, grille de recherche, octree et grille de vitesse 2D d'un profil.
    zone = (lat_min, lat_max, lon_min, lon_max) en degrés.
    """
    lat_min, lat_max, lon_min, lon_max = zone
    lat0 = round((lat_min + lat_max) / 2, 3)
    lon0 = round((lon_min + lon_max) / 2, 3)
    proj = AzimuthalEquidistant(lon0, lat0)
    xs, ys = proj.forward([lon_min, lon_max, lon_min, lon_max, lon0, lon0],
                          [lat_min, lat_min, lat_max, lat_max, lat_min, lat_max])
    hx = ceil_to(max(abs(v) for v in xs) + marge_km, 5)
    hy = ceil_to(max(abs(v) for v in ys) + marge_km, 5)
    depth = prof_max - Z_TOP_KM
    oct_n = [math.ceil(round(2 * hx / cellule_km, 9)), math.ceil(round(2 * hy / cellule_km, 9)),
             math.ceil(round(depth / cellule_km, 9))]
    n_cells = oct_n[0] * oct_n[1] * oct_n[2]
    vg_zmax = max(60.0, prof_max + 10)
    return {
        "lat0": lat0, "lon0": lon0, "half_x": hx, "half_y": hy,
        "locgrid": (int(2 * hx) + 1, int(2 * hy) + 1, int(round(depth)) + 1, -hx, -hy, Z_TOP_KM),
        "oct": (*oct_n, max(50000, ceil_to(5 * n_cells, 5000))),
        "vggrid": (2, int(round(distance_max_km / pas)) + 1,
                   int(round((vg_zmax - Z_TOP_KM) / pas)) + 1, pas),
        "vg_zmax": vg_zmax,
    }


def topo_bounds(geo, pad_deg=0.05):
    """Emprise lon/lat (arrondie à 0,05°) de la grille de recherche, avec une marge."""
    proj = AzimuthalEquidistant(geo["lon0"], geo["lat0"])
    hx, hy = geo["half_x"], geo["half_y"]
    xs = [-hx, 0, hx, -hx, hx, -hx, 0, hx]
    ys = [-hy, -hy, -hy, 0, 0, hy, hy, hy]
    lons, lats = proj.inverse(xs, ys)
    lo = lambda v: math.floor(round((v - pad_deg) / 0.05, 6)) * 0.05
    hi = lambda v: math.ceil(round((v + pad_deg) / 0.05, 6)) * 0.05
    return (round(lo(min(lons)), 2), round(hi(max(lons)), 2),
            round(lo(min(lats)), 2), round(hi(max(lats)), 2))


# ─────────────────────────────────────────────────────────────────────────────
# FICHIERS DU PROFIL
# ─────────────────────────────────────────────────────────────────────────────

def profile_files(nom, geo, layers, model_path, pas, topo):
    """Contenu des fichiers texte du profil : {nom de fichier: texte}."""
    trans = f"TRANS AZIMUTHAL_EQUIDIST WGS-84 {geo['lat0']:.6f} {geo['lon0']:.6f} 0"
    nx, ny, nz, x0, y0, z0 = geo["locgrid"]
    ox, oy, oz, nodes = geo["oct"]
    vg = geo["vggrid"]
    today = date.today().isoformat()
    files = {}
    for phase in "PS":
        files[f"vel2grid_{phase}.in"] = "\n".join([
            f"# Modèle de vitesse du profil {nom} (créé par creer_profil.py le {today}),",
            f"# lu dans {model_path}. Toits en km sous le niveau de la mer.",
            "CONTROL 1 159753", trans, "VGOUT ${MODEL}", f"VGTYPE {phase}",
            f"VGGRID {vg[0]} {vg[1]} {vg[2]} 0.0 0.0 {Z_TOP_KM:.1f} {pas} {pas} {pas} SLOW_LEN",
            "#LAYER depth Vp_top Vp_grad Vs_top Vs_grad p_top p_grad",
            *layer_lines(layers), ""])
    files[f"nll_{nom}.in"] = "\n".join([
        f"# Génération des grilles de temps (Grid2Time) du profil {nom}, lue par nll_run.py --grilles.",
        f"# Grilles 2D au pas de {pas:g} km, de {Z_TOP_KM:g} à {geo['vg_zmax']:g} km, sur {(vg[1] - 1) * pas:g} km.",
        "CONTROL 1 159753", trans,
        f"GTFILES ${{NLLROOT}}/{nom}/model/layer ${{NLLROOT}}/{nom}/time/layer P",
        "GTMODE GRID2D ANGLES_YES", "GT_PLFD 1.0e-4 1", ""])
    conf = [
        f"# Profil {nom}, créé par creer_profil.py le {today}.",
        f"# LOCGRID {2 * geo['half_x']:g} x {2 * geo['half_y']:g} km de {z0:g} à {z0 + nz - 1:g} km ;"
        f" cellules initiales de l'octree d'environ {2 * geo['half_x'] / ox:.1f} km.",
        "CONTROL 1 159753", trans, LOC_LINES.splitlines()[0],
        f"LOCSEARCH OCT {ox} {oy} {oz} 0.001 {nodes} 5000 0 1",
        f"LOCGRID  {nx} {ny} {nz} {x0:g} {y0:g} {z0:.4f}  1.0000 1.0000 1.0000  PROB_DENSITY  SAVE",
        *LOC_LINES.splitlines()[1:]]
    if topo:
        conf.append(f"LOCTOPO_SURFACE ${{NLLROOT}}/{nom}/topo.asc 0")
    files[f"NLL.{nom}.conf"] = "\n".join(conf + [""])
    return files


def readme_text(nom, args, geo, layers, topo_box):
    nx, ny, nz, x0, y0, z0 = geo["locgrid"]
    lines = [f"Profil {nom} — créé le {date.today().isoformat()} par creer_profil.py",
             "=" * (len(nom) + 45),
             f"Région : {args.region}, zone {args.zone[0]}–{args.zone[1]}° N × "
             f"{args.zone[2]}–{args.zone[3]}° E.",
             f"Modèle 1D : {Path(args.modele).resolve()}",
             "   toit   Vp    Vs     (km, km/s)"]
    lines += [f"  {l['top']:5.1f}  {l['vp']:4.2f}  {l['vs']:4.2f}"
              + ("  (gradient)" if l["vp_grad"] or l["vs_grad"] else "") for l in layers]
    lines += [f"TRANS {geo['lat0']}° N {geo['lon0']}° E (centre de la zone).",
              f"Grilles 2D au pas de {args.pas:g} km sur {args.distance_max:g} km, "
              f"de {Z_TOP_KM:g} à {geo['vg_zmax']:g} km.",
              f"LOCGRID {2 * geo['half_x']:g} x {2 * geo['half_y']:g} km de {z0:g} à {z0 + nz - 1:g} km ; "
              f"OCT {' '.join(str(v) for v in geo['oct'][:3])}, {geo['oct'][3]} nœuds au plus."]
    if topo_box:
        lines.append(f"topo.asc : relief SRTM {topo_box[0]}–{topo_box[1]}° E × "
                     f"{topo_box[2]}–{topo_box[3]}° N au pas de 0,001° (en-tête GMT 4).")
    lines.append(f"Configuration de la région : config_{args.region}.yaml.")
    return "\n".join(lines) + "\n"


def region_config(base, args, regions_dir):
    """Configuration de la région (fetch, phases, run) à partir de celle de la machine."""
    url = args.fdsnws.rstrip("/")
    fetch = base.get("fetch", {})
    donnees_xml = Path(fetch["cache_dir"]).parent
    obs_root = Path(fetch["obs_dir"])
    run = dict(base["run"])
    run.setdefault("regions_dir", str(regions_dir))
    return {
        "phases": {"output_dir": str(obs_root),
                   "default_error_s": base.get("phases", {}).get("default_error_s", {"P": 0.02, "S": 0.02})},
        "fetch": {
            "fdsnws_url": f"{url}/event/1/query",
            "fdsnws_station_url": f"{url}/station/1/query",
            "zone": {"lat_min": args.zone[0], "lat_max": args.zone[1],
                     "lon_min": args.zone[2], "lon_max": args.zone[3]},
            "event_types": args.types,
            "cache_dir": str(donnees_xml / f"par_jour_{args.region}"),
            "obs_dir": str(obs_root / args.region),
        },
        "run": run,
    }


def check_machine(base):
    """Vérifie config.yaml avant de créer quoi que ce soit ; s'arrête avec un message clair sinon."""
    problems = []
    run = base.get("run") or {}
    fetch = base.get("fetch") or {}
    for key, value in [("run.profils_dir", run.get("profils_dir")), ("run.runs_dir", run.get("runs_dir")),
                       ("run.nlloc", run.get("nlloc")), ("fetch.cache_dir", fetch.get("cache_dir")),
                       ("fetch.obs_dir", fetch.get("obs_dir"))]:
        if not value:
            problems.append(f"{key} manque")
        elif "/path/to" in str(value):
            problems.append(f"{key} vaut encore {value} : y mettre votre dossier")
    if run.get("nlloc") and "/path/to" not in str(run["nlloc"]):
        for prog in ("NLLoc", "Vel2Grid", "Grid2Time"):
            if not (Path(run["nlloc"]).parent / prog).exists():
                problems.append(f"{prog} introuvable dans {Path(run['nlloc']).parent} "
                                "(les trois programmes NLL doivent être dans le même dossier)")
    if problems:
        raise SystemExit("config.yaml à compléter :\n  - " + "\n  - ".join(problems))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crée un profil NLL 1D et la configuration d'une nouvelle région."
    )
    parser.add_argument("--region", required=True, help="Nom court de la région (ex. jura)")
    parser.add_argument("--nom", required=True, help="Nom du profil (ex. 1_jura_1D_topo)")
    parser.add_argument("--modele", required=True, help="Modèle 1D : fichier .nd ou texte « toit Vp Vs »")
    parser.add_argument("--lat", required=True, nargs=2, type=float, metavar=("MIN", "MAX"),
                        help="Latitudes de la zone des séismes, en degrés (ex. 46.95 47.55)")
    parser.add_argument("--lon", required=True, nargs=2, type=float, metavar=("MIN", "MAX"),
                        help="Longitudes de la zone des séismes, en degrés (ex. 5.45 7.55)")
    parser.add_argument("--fdsnws", required=True,
                        help="Adresse fdsnws du serveur SeisComP de la région (…/fdsnws)")
    parser.add_argument("--pas", type=float, default=1.0, help="Pas des grilles de temps en km (défaut : 1)")
    parser.add_argument("--prof-max", type=float, default=30.0,
                        help="Profondeur maximale de la recherche en km (défaut : 30)")
    parser.add_argument("--marge", type=float, default=10.0,
                        help="Marge autour de la zone pour la recherche, en km (défaut : 10)")
    parser.add_argument("--cellule", type=float, default=3.0,
                        help="Taille des cellules initiales de l'octree en km (défaut : 3)")
    parser.add_argument("--distance-max", type=float, default=400.0,
                        help="Distance station–séisme couverte par les grilles, en km (défaut : 400)")
    parser.add_argument("--types", nargs="+", default=["earthquake"],
                        help="Types d'événements gardés (défaut : earthquake)")
    parser.add_argument("--sans-topo", action="store_true", help="Ne pas générer la topographie")
    parser.add_argument("--force", action="store_true", help="Écraser un profil ou une région existants")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "config.yaml"),
        help="Configuration de la machine (défaut : config.yaml)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    (lat_min, lat_max), (lon_min, lon_max) = sorted(args.lat), sorted(args.lon)
    if not (-90 <= lat_min < lat_max <= 90 and -180 <= lon_min < lon_max <= 180):
        raise SystemExit("--lat et --lon attendent deux valeurs différentes, en degrés")
    args.zone = (lat_min, lat_max, lon_min, lon_max)
    base = load_config(args.config)
    check_machine(base)
    profils_dir = Path(base["run"]["profils_dir"])
    regions_dir = Path(base["run"].get("regions_dir") or profils_dir.parent / "profils_travail")
    profile_dir = profils_dir / args.nom
    region_dir = regions_dir / args.region
    region_cfg = region_dir / f"config_{args.region}.yaml"
    for path in (profile_dir, region_cfg):
        if path.exists() and not args.force:
            raise SystemExit(f"{path} existe déjà (--force pour l'écraser)")

    log(f"Profil {args.nom}, région {args.region} : "
        f"{lat_min}–{lat_max}° N, {lon_min}–{lon_max}° E")
    layers = read_model(args.modele)
    log(f"modèle : {len(layers)} couches lues dans {args.modele}", 1)
    geo = geometry(args.zone, args.prof_max, args.pas, args.marge, args.cellule, args.distance_max)
    nx, ny, nz, *_ = geo["locgrid"]
    log(f"TRANS {geo['lat0']} {geo['lon0']} ; LOCGRID {nx} {ny} {nz} ; "
        f"OCT {' '.join(str(v) for v in geo['oct'])}", 1)

    (profile_dir / "model").mkdir(parents=True, exist_ok=True)
    (profile_dir / "time").mkdir(exist_ok=True)
    for name, text in profile_files(args.nom, geo, layers, args.modele, args.pas,
                                    topo=not args.sans_topo).items():
        (profile_dir / name).write_text(text.replace("${MODEL}", str(profile_dir / "model" / "layer")))

    vel2grid = Path(base["run"]["nlloc"]).with_name("Vel2Grid")
    for phase in "PS":
        with open(profile_dir / f"vel2grid_{phase}.log", "w") as out:
            if subprocess.run([str(vel2grid), f"vel2grid_{phase}.in"], cwd=profile_dir,
                              stdout=out, stderr=subprocess.STDOUT).returncode != 0:
                raise SystemExit(f"Vel2Grid a échoué (voir {profile_dir / f'vel2grid_{phase}.log'})")
    log("modèle NLL écrit (Vel2Grid P et S)", 1)

    topo_box = None
    if not args.sans_topo:
        from nll_pipeline import step4_generate_topo
        topo_box = topo_bounds(geo)
        log("Topographie")
        step4_generate_topo(profile_dir, *topo_box, 0.001)
        if not (profile_dir / "topo.asc").exists():
            raise SystemExit("topo.asc non généré (srtm.py installé ? accès internet ?) ; "
                             "relancer avec --force, ou --sans-topo")
    (profile_dir / "README.txt").write_text(readme_text(args.nom, args, geo, layers, topo_box))

    region_dir.mkdir(parents=True, exist_ok=True)
    header = (f"# Région {args.region} (creer_profil.py, {date.today().isoformat()}) : "
              f"à passer en --config à fetch_picks.py, nll_run.py et scrtdd_inputs.py.\n")
    region_cfg.write_text(header + yaml.safe_dump(region_config(base, args, regions_dir),
                                                  allow_unicode=True, sort_keys=False))
    log(f"→ {profile_dir}")
    log(f"→ {region_cfg}")
    log("Étape suivante (premier run, calcule les grilles de temps) :")
    log(f"python nll_run.py --config {region_cfg} --profil {args.nom} "
        f"--debut AAAA-MM-JJ --fin AAAA-MM-JJ --grilles", 1)


if __name__ == "__main__":
    main()
