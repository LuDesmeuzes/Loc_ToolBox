"""
hyp_vers_csv.py
===============
Écrit localisations.csv à partir du .hyp d'un run, sans relancer NLLoc :
pour les runs faits avant que nll_run.py n'écrive ce fichier, ou pour un
.hyp venu d'ailleurs.

Une ligne par événement localisé (les rejetés sont ignorés), colonnes
evid, time, latitude, longitude, depth_km (sous le niveau de la mer),
erh_km, erz_km, rms_s, n_phases, gap_deg : lisible tel quel par l'outil
carte et coupes HTML.

Entrées : dossiers de run (<nom>/<nom>.hyp) ou fichiers .hyp, autant que
voulu.

Sorties :
  - <dossier du run>/localisations.csv pour un dossier de run ;
  - <dossier du .hyp>/<nom du .hyp>.csv pour un fichier .hyp
    (localisations.csv s'il s'agit du <nom>.hyp d'un run) ;
  - ou --sortie, avec une seule entrée.
Un localisations.csv existant est remplacé.

Utilisation :
    python hyp_vers_csv.py <runs_dir>/05_ubaye_1D_topo_20230514_20250630
    python hyp_vers_csv.py <runs_dir>/*/
    python hyp_vers_csv.py autre.hyp --sortie autre_localisations.csv
"""

import argparse
from pathlib import Path

from nll_run import write_locations


def hyp_and_output(path):
    """Dossier de run ou fichier .hyp → (.hyp, CSV à écrire)."""
    path = Path(path)
    if path.is_dir():
        hyp = path / f"{path.name}.hyp"
        if not hyp.exists():
            raise SystemExit(f"Pas de {hyp.name} dans {path} : est-ce un dossier de run ?")
        return hyp, path / "localisations.csv"
    if path.suffix != ".hyp" or not path.exists():
        raise SystemExit(f"Ni dossier de run ni fichier .hyp : {path}")
    if path.stem == path.parent.name:
        return path, path.parent / "localisations.csv"
    return path, path.with_suffix(".csv")


def parse_args():
    parser = argparse.ArgumentParser(
        description="localisations.csv à partir du .hyp d'un run (sans relancer NLLoc)")
    parser.add_argument("entrees", nargs="+", help="dossiers de run ou fichiers .hyp")
    parser.add_argument("--sortie", help="CSV à écrire (une seule entrée)")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.sortie and len(args.entrees) > 1:
        raise SystemExit("--sortie ne va qu'avec une seule entrée")
    for entree in args.entrees:
        hyp, out = hyp_and_output(entree)
        if args.sortie:
            out = Path(args.sortie)
        n = write_locations(hyp, out)
        print(f"{n} localisations → {out}")


if __name__ == "__main__":
    main()
