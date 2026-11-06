#!/usr/bin/env python3
"""
telecharger_formes_onde.py
==========================
Rassemble dans une archive SDS dédiée les formes d'onde dont scrtdd a besoin
pour la corrélation croisée : les fenêtres des fichiers formes_onde_*.post
écrits par scrtdd_inputs.py (une ligne « réseau station location canaux début
fin » par événement et par station pointée).

À lancer sur le serveur SeisComP, dans le dossier des fichiers .post. Ne
dépend que de Python 3 (bibliothèque standard) et de scart (SeisComP).

Étapes :
  1. routage EIDA : chaque fenêtre est attribuée au centre de données public
     qui sert son réseau (CH → ETH, FR → RESIF…) ;
  2. téléchargement fdsnws-dataselect, par paquets de --paquet fenêtres,
     dans mseed/ (les paquets déjà téléchargés ne sont pas redemandés) ;
  3. les fenêtres qu'aucun centre public ne sert (réseaux locaux ou
     temporaires, ex. 5C) sont extraites de l'archive du serveur
     (--archive-serveur) avec scart ;
  4. tout est rangé avec scart dans l'archive dédiée, sans toucher à celle
     du serveur.

Sorties (dans le dossier courant) :
  - mseed/*.mseed        : données brutes téléchargées ou extraites
  - non_routees.txt      : fenêtres sans centre public
  - bilan_formes_onde.txt : nombre de fenêtres et d'octets par centre

Utilisation :
    python3 telecharger_formes_onde.py --archive ~/sds/<run>
    python3 telecharger_formes_onde.py --archive ~/sds/<run> --archive-serveur /data/sig/SDS
Puis : scrtdd … -I sdsarchive://<archive>
"""

import argparse
import glob
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROUTING_URL = "https://www.orfeus-eu.org/eidaws/routing/1/query"


def read_windows(pattern="formes_onde_*.post"):
    lines = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            lines += [l.strip() for l in f if l.strip()]
    return lines


def post(url, body, timeout=600, retries=3):
    """
    POST texte ; renvoie (code HTTP, contenu). 204 / 404 = pas de données ;
    pour une autre erreur du serveur, contenu = son message (à ne pas archiver).
    """
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=body.encode(), method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (204, 404):
                return err.code, b""
            if err.code in (400, 413) or attempt == retries:
                return err.code, err.read()
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt == retries:
                print(f"  ⚠ {url} : {err}")
                return 0, b""
        time.sleep(10 * attempt)
    return 0, b""


def parse_routing(text):
    """Réponse du routage (format post) → {url dataselect: [fenêtres]}."""
    routes, url = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            url = None
        elif line.startswith("http"):
            url = line
            routes.setdefault(url, [])
        elif url:
            routes[url].append(line)
    return routes


def route(windows, chunk=2000):
    """Fenêtres → ({url: [fenêtres]}, [fenêtres sans centre public])."""
    routes = {}
    for k in range(0, len(windows), chunk):
        part = windows[k:k + chunk]
        code, content = post(ROUTING_URL, "service=dataselect\nformat=post\n" + "\n".join(part) + "\n")
        if code not in (200, 204):
            # Sans routage, tout passerait pour « sans centre public » : on s'arrête
            sys.exit(f"Routage EIDA impossible (HTTP {code}) : {ROUTING_URL}")
        for url, lines in parse_routing(content.decode(errors="replace")).items():
            routes.setdefault(url, []).extend(lines)
    routed = {l for lines in routes.values() for l in lines}
    return routes, [w for w in windows if w not in routed]


def fetch(url, lines):
    """
    Données de lines (fenêtres POST) auprès d'un centre, en redécoupant la
    requête tant que le centre la refuse (400 / 413, ex. RESIF : 200 fenêtres
    au plus). Renvoie (données miniSEED, messages d'erreur).
    """
    code, content = post(url, "\n".join(lines) + "\n")
    if code in (200, 204, 404):
        return content, []
    if code in (400, 413) and len(lines) > 1:
        half = len(lines) // 2
        a, err_a = fetch(url, lines[:half])
        b, err_b = fetch(url, lines[half:])
        return a + b, err_a + err_b
    return b"", [f"HTTP {code} : {content.decode(errors='replace').strip()[:200]}"]


def scart_list(windows):
    """Fenêtres POST → lignes de liste scart « début;fin;NET.STA.LOC.CHA »."""
    out = []
    for w in windows:
        net, sta, loc, cha, start, end = w.split()
        loc = "" if loc == "--" else loc
        out.append(f"{start.replace('T', ' ')};{end.replace('T', ' ')};{net}.{sta}.{loc}.{cha}")
    return out


def scart(args):
    cmd = ["seiscomp", "exec", "scart"] + args
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd)


def main():
    # Une ligne écrite = une ligne visible, même redirigée dans un fichier (nohup … > log)
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[3])
    parser.add_argument("--archive", required=True, help="Archive SDS dédiée à remplir")
    parser.add_argument("--archive-serveur",
                        help="Archive SDS du serveur, pour les réseaux qu'aucun centre public ne sert")
    parser.add_argument("--paquet", type=int, default=500,
                        help="Fenêtres par requête dataselect (défaut : 500)")
    args = parser.parse_args()
    archive = os.path.expanduser(args.archive)
    os.makedirs(archive, exist_ok=True)
    os.makedirs("mseed", exist_ok=True)

    windows = read_windows()
    if not windows:
        sys.exit("Aucun fichier formes_onde_*.post dans le dossier courant")
    print(f"{len(windows)} fenêtres")

    print("Routage EIDA")
    routes, unrouted = route(windows)
    bilan = []
    for url, lines in sorted(routes.items()):
        name = url.split("/")[2]
        print(f"== {name} : {len(lines)} fenêtres")
        n_bytes = 0
        for k in range(0, len(lines), args.paquet):
            out = f"mseed/{name}_{k // args.paquet + 1:03d}.mseed"
            if os.path.exists(out) and os.path.getsize(out) > 0:
                n_bytes += os.path.getsize(out)
                continue
            content, errors = fetch(url, lines[k:k + args.paquet])
            if content:
                with open(out, "wb") as f:
                    f.write(content)
            n_bytes += len(content)
            print(f"  paquet {k // args.paquet + 1} : {len(content) // 1024} Ko"
                  + (f" ; ⚠ {errors[0]}" if errors else ""))
        bilan.append(f"{name}\t{len(lines)} fenêtres\t{n_bytes // 1024 ** 2} Mo")

    with open("non_routees.txt", "w") as f:
        f.write("\n".join(unrouted) + "\n")
    nets = sorted({w.split()[0] for w in unrouted})
    print(f"{len(unrouted)} fenêtres sans centre public (réseaux : {', '.join(nets) or '-'})")
    bilan.append(f"sans centre public\t{len(unrouted)} fenêtres\t{', '.join(nets)}")

    if unrouted and args.archive_serveur:
        print(f"Extraction depuis l'archive du serveur {args.archive_serveur}")
        with open("liste_scart.txt", "w") as f:
            f.write("\n".join(scart_list(unrouted)) + "\n")
        with open("mseed/archive_serveur.mseed", "wb") as f:
            subprocess.run(["seiscomp", "exec", "scart", "-d", "-s", "--list", "liste_scart.txt",
                            os.path.expanduser(args.archive_serveur)], stdout=f)
    elif unrouted:
        print("  (--archive-serveur non donné : ces fenêtres ne sont pas récupérées)")

    print(f"Rangement dans {archive}")
    for path in sorted(glob.glob("mseed/*.mseed")):
        if os.path.getsize(path) > 0:
            scart(["-I", f"file://{os.path.abspath(path)}", archive])

    with open("bilan_formes_onde.txt", "w") as f:
        f.write("\n".join(bilan) + "\n")
    print("\n".join(bilan))


if __name__ == "__main__":
    main()
