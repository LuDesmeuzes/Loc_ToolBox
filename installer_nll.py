"""
installer_nll.py
================
Télécharge NonLinLoc (dépôt GitHub d'Anthony Lomax), le compile avec cmake et
copie ses programmes dans <racine>/bin, où les scripts de la boîte à outils
le trouvent sans rien configurer (nll_common.find_nll()).

Le script vérifie d'abord que git, cmake, make et un compilateur C sont
installés, et donne la commande d'installation sinon. Les sources sont
gardées : relancer le script recompile sans retélécharger (--maj pour
prendre la dernière version).

Sorties :
  - <racine>/sources/NonLinLoc/ : sources de NonLinLoc (git clone)
  - <racine>/sources/compilation_NonLinLoc.log : sortie de git, cmake et make
  - <racine>/bin/ : NLLoc, Vel2Grid, Grid2Time et les autres programmes NLL

Utilisation :
    python installer_nll.py
    python installer_nll.py --maj
    python installer_nll.py --dossier ~/bin/nll
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from nll_common import NLL_PROGRAMS, find_nll, load_config, log

DEPOT = "https://github.com/alomax/NonLinLoc"

INSTALL_HINTS = {
    "darwin": {"git": "xcode-select --install", "make": "xcode-select --install",
               "cc": "xcode-select --install", "cmake": "brew install cmake (ou pip install cmake)"},
    "linux": {"git": "sudo apt install git", "make": "sudo apt install build-essential",
              "cc": "sudo apt install build-essential", "cmake": "sudo apt install cmake (ou pip install cmake)"},
}


def missing_tools():
    """Outils de compilation absents, avec la commande pour les installer."""
    hints = INSTALL_HINTS.get("darwin" if sys.platform == "darwin" else "linux")
    return {tool: hints[tool] for tool in ("git", "cmake", "make", "cc") if not shutil.which(tool)}


def run(cmd, cwd, log_file):
    """Lance une commande en ajoutant sa sortie à log_file ; s'arrête si elle échoue."""
    with open(log_file, "a") as out:
        out.write(f"\n$ {' '.join(cmd)}\n")
        out.flush()
        if subprocess.run(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT).returncode != 0:
            raise SystemExit(f"Échec de « {' '.join(cmd)} » (voir {log_file})")


def build(source, log_file):
    """Compile NonLinLoc dans source/src/bin (procédure du README de NonLinLoc)."""
    src = source / "src"
    bin_dir = src / "bin"
    if bin_dir.is_symlink() or bin_dir.is_file():
        bin_dir.unlink()
    bin_dir.mkdir(exist_ok=True)
    (src / "CMakeCache.txt").unlink(missing_ok=True)
    run(["cmake", "."], src, log_file)
    run(["make", f"-j{os.cpu_count() or 2}"], src, log_file)
    return bin_dir


def parse_args():
    parser = argparse.ArgumentParser(description="Télécharge et compile NonLinLoc dans <racine>/bin")
    parser.add_argument("--dossier", help="Dossier où copier les programmes (défaut : <racine>/bin)")
    parser.add_argument("--maj", action="store_true", help="Mettre à jour les sources avant de compiler")
    parser.add_argument("--depot", default=DEPOT, help=f"Dépôt git de NonLinLoc (défaut : {DEPOT})")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "config.yaml"),
        help="Configuration de la machine (défaut : config.yaml, facultatif)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    root = Path(config["racine"])
    target = Path(args.dossier).expanduser() if args.dossier else root / "bin"
    found = find_nll(config, root)
    if found and not args.maj and found != target:
        log(f"NonLinLoc est déjà installé dans {found} : rien à faire (--maj pour le recompiler ici)")
        return

    missing = missing_tools()
    if missing:
        lines = [f"{tool} : {hint}" for tool, hint in missing.items()]
        raise SystemExit("Outils de compilation manquants :\n  - " + "\n  - ".join(lines))

    source = root / "sources" / "NonLinLoc"
    log_file = source.parent / "compilation_NonLinLoc.log"
    source.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("")
    if not source.exists():
        log(f"Téléchargement de {args.depot}")
        run(["git", "clone", "--depth", "1", args.depot, str(source)], source.parent, log_file)
    elif args.maj:
        log("Mise à jour des sources")
        run(["git", "pull", "--ff-only"], source, log_file)
    log(f"Compilation (quelques minutes ; sortie dans {log_file})")
    bin_dir = build(source, log_file)

    absent = [prog for prog in NLL_PROGRAMS if not (bin_dir / prog).is_file()]
    if absent:
        raise SystemExit(f"Compilation incomplète : {', '.join(absent)} absents de {bin_dir} (voir {log_file})")
    target.mkdir(parents=True, exist_ok=True)
    programs = [p for p in bin_dir.iterdir() if p.is_file() and os.access(p, os.X_OK)]
    for prog in programs:
        shutil.copy2(prog, target / prog.name)
    log(f"{len(programs)} programmes copiés dans {target}")
    if target != root / "bin" and not config.get("nll_bin"):
        log(f"Ajouter « nll_bin: {target} » à config.yaml pour que les scripts les trouvent", 1)


if __name__ == "__main__":
    main()
