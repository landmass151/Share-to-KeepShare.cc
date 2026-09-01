from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
import re

import requests
from bs4 import BeautifulSoup


FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("bases-à-extraire.txt")
DOSSIER_LOG = Path("log-url")

BASE_URL = "https://keepshare.org/ldf6j5ti/"
MAX_PAGES_SECURITE = 1000
MAGNET_PREFIX = "magnet:?xt=urn:btih:"


PATTERN_URLS = re.compile(
    r"""
    (?:
        https?://
        |
        magnet:\?xt=urn:btih:
    )
    [\s\S]*?
    (?=
        (?<![=&?])
        (?:
            https?://
            |
            magnet:\?xt=urn:btih:
        )
        |
        $
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

PATTERN_PLAGE_PAGES = re.compile(
    r"<(\d+|\*)-(\d+|\*)>"
)


def extraire_liens(texte):
    liens = []

    for match in PATTERN_URLS.finditer(texte):
        lien = match.group(0).strip()

        lien = lien.strip(
            " \t\r\n.,;:)]}\"'"
        )

        if lien:
            liens.append(lien)

    return list(dict.fromkeys(liens))


def lire_liens():
    if not FICHIER_LIENS.exists():
        return []

    texte = FICHIER_LIENS.read_text(
        encoding="utf-8"
    )

    return extraire_liens(texte)


def nettoyer_ligne(ligne):
    return ligne.strip().strip(
        " \t\r\n.,;:)]}\"'"
    )


def lire_urls_extractions():
    if not FICHIER_EXTRACTIONS.exists():
        return []

    urls = []
    url_actuelle = None

    lignes = FICHIER_EXTRACTIONS.read_text(
        encoding="utf-8"
    ).splitlines()

    for ligne in lignes:
        ligne = ligne.strip()

        if not ligne:
            continue

        if ligne.startswith("#"):
            continue

        urls_absolues = re.findall(
            r"https?://[^\s'\"]+",
            ligne,
            flags=re.IGNORECASE,
        )

        if urls_absolues:
            if url_actuelle:
                urls.append(
                    nettoyer_ligne(url_actuelle)
                )

            for url in urls_absolues[:-1]:
                urls.append(
                    nettoyer_ligne(url)
                )

            url_actuelle = urls_absolues[-1]

        elif url_actuelle:
            url_actuelle += ligne

    if url_actuelle:
        urls.append(
            nettoyer_ligne(url_actuelle)
        )

    return list(dict.fromkeys(urls))


def telecharger_page(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
        },
    )

    response.raise_for_status()

    return response.text


def extraire_magnets_html(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    magnets = []

    for element in soup.find_all(True):
        for valeur in element.attrs.values():
            valeurs = (
                valeur
                if isinstance(valeur, list)
                else [valeur]
            )

            for contenu in valeurs:
                if not isinstance(contenu, str):
                    continue

                contenu = contenu.strip()

                if contenu.lower().startswith(
                    MAGNET_PREFIX
                ):
                    magnets.append(contenu)

    return list(dict.fromkeys(magnets))


def identifier_lien(lien):
    lien = lien.strip()

    if lien.lower().startswith(MAGNET_PREFIX):
        partie = urlsplit(lien)
        query = parse_qs(partie.query)

        xt_values = query.get("xt", [])

        if xt_values:
            xt = xt_values[0]

            hash_value = re.sub(
                r"^urn:btih:",
                "",
                xt,
                flags=re.IGNORECASE,
            )

            if not hash_value:
                raise ValueError(
                    f"Hash magnet vide : {lien}"
                )

            return (
                MAGNET_PREFIX,
                "/" + hash_value.upper(),
            )

        match = re.search(
            r"xt=urn:btih:([^&\s]+)",
            lien,
            flags=re.IGNORECASE,
        )

        if not match:
            raise ValueError(
                f"Hash magnet introuvable : {lien}"
            )

        return (
            MAGNET_PREFIX,
            "/" + match.group(1).upper(),
        )

    partie = urlsplit(lien)

    if partie.scheme.lower() not in (
        "http",
        "https",
    ):
        raise ValueError(
            f"Type de lien non supporté : {lien}"
        )

    if not partie.netloc:
        raise ValueError(
            f"URL invalide : {lien}"
        )

    base = (
        f"{partie.scheme.lower()}://"
        f"{partie.netloc}"
    )

    chemin = partie.path or "/"

    if partie.query:
        chemin += "?" + partie.query

    return base, chemin


def lire_fichier_log(fichier_log):
    deja_envoyes = set()
    base_actuelle = None

    lignes = fichier_log.read_text(
        encoding="utf-8"
    ).splitlines()

    for ligne in lignes:
        ligne = ligne.strip()

        if not ligne:
            continue

        if ligne.startswith("/"):
            if base_actuelle:
                deja_envoyes.add(
                    (base_actuelle, ligne)
                )
        else:
            base_actuelle = ligne

    return deja_envoyes


def lire_log():
    DOSSIER_LOG.mkdir(
        parents=True,
        exist_ok=True,
    )

    deja_envoyes = set()

    for fichier_log in sorted(
        DOSSIER_LOG.glob("*.txt")
    ):
        deja_envoyes.update(
            lire_fichier_log(fichier_log)
        )

    return deja_envoyes


def obtenir_nom_fichier_log(identifiant):
    base, chemin = identifiant

    if base == MAGNET_PREFIX:
        prefixe = "magnet"

    else:
        partie = urlsplit(base)

        domaine = partie.netloc.lower()

        domaine = re.sub(
            r"[^a-z0-9]+",
            "",
            domaine,
        )

        if not domaine:
            domaine = "inconnu"

        prefixe = domaine

    valeur = chemin.lstrip("/").lower()

    caractere = next(
        (
            caractere
            for caractere in valeur
            if caractere.isalnum()
        ),
        "autre",
    )

    return f"{prefixe}-{caractere}.txt"


def chemin_fichier_log(identifiant):
    return DOSSIER_LOG / obtenir_nom_fichier_log(
        identifiant
    )


def ecrire_log(identifiants):
    DOSSIER_LOG.mkdir(
        parents=True,
        exist_ok=True,
    )

    groupes = OrderedDict()

    for identifiant in sorted(identifiants):
        fichier_log = chemin_fichier_log(
            identifiant
        )

        if fichier_log not in groupes:
            groupes[fichier_log] = []

        groupes[fichier_log].append(
            identifiant
        )

    for fichier_log, identifiants_fichier in groupes.items():
        groupes_base = OrderedDict()

        for base, chemin in identifiants_fichier:
            if base not in groupes_base:
                groupes_base[base] = []

            if chemin not in groupes_base[base]:
                groupes_base[base].append(
                    chemin
                )

        lignes = []

        for base, chemins in groupes_base.items():
            if lignes:
                lignes.append("")

            lignes.append(base)
            lignes.extend(chemins)

        contenu = "\n".join(lignes)

        if contenu:
            contenu += "\n"

        fichier_log.write_text(
            contenu,
            encoding="utf-8",
        )


def supprimer_liens_envoyes(identifiants_envoyes):
    if not FICHIER_LIENS.exists():
        return

    texte_original = FICHIER_LIENS.read_text(
        encoding="utf-8"
    )

    def remplacer_lien(match):
        lien_original = match.group(0)

        lien = lien_original.strip()

        lien = lien.strip(
            " \t\r\n.,;:)]}\"'"
        )

        try:
            identifiant = identifier_lien(lien)
        except ValueError:
            return lien_original

        if identifiant in identifiants_envoyes:
            return ""

        return lien_original

    nouveau_texte = PATTERN_URLS.sub(
        remplacer_lien,
        texte_original,
    )

    if nouveau_texte != texte_original:
        FICHIER_LIENS.write_text(
            nouveau_texte,
            encoding="utf-8",
        )

        print(
            "Les liens envoyés ont été supprimés "
            "de liens-à-envoyer.txt."
        )


def ajouter_liens_echoues(liens_echoues):
    if not liens_echoues:
        return

    contenu_existant = ""

    if FICHIER_LIENS.exists():
        contenu_existant = FICHIER_LIENS.read_text(
            encoding="utf-8"
        )

    liens_existants = set(
        extraire_liens(contenu_existant)
    )

    liens_a_ajouter = [
        lien
        for lien in liens_echoues
        if lien not in liens_existants
    ]

    if liens_a_ajouter:
        lignes_nouvelles = (
            "\n".join(liens_a_ajouter)
            + "\n"
        )

        FICHIER_LIENS.write_text(
            contenu_existant + lignes_nouvelles,
            encoding="utf-8",
        )

        print(
            f"{len(liens_a_ajouter)} lien(s) échoué(s) "
            "ajouté(s) pour réessai."
        )


def construire_url_page(url_modele, numero_page):
    if numero_page is None:
        return url_modele

    url_page = PATTERN_PLAGE_PAGES.sub(
        str(numero_page),
        url_modele,
        count=1,
    )

    return url_page.replace(
        "*",
        str(numero_page),
    )


def obtenir_numeros_pages(url_modele):
    plage = PATTERN_PLAGE_PAGES.search(
        url_modele
    )

    if plage:
        debut_texte = plage.group(1)
        fin_texte = plage.group(2)

        if (
            debut_texte == "*"
            and fin_texte == "*"
        ):
            raise ValueError(
                f"Plage invalide : {plage.group(0)}"
            )

        if debut_texte == "*":
            debut = 1
            fin = int(fin_texte)

            if debut > fin:
                raise ValueError(
                    f"Plage invalide : {plage.group(0)}"
                )

            return range(debut, fin + 1)

        if fin_texte == "*":
            debut = int(debut_texte)

            return range(
                debut,
                MAX_PAGES_SECURITE + 1,
            )

        debut = int(debut_texte)
        fin = int(fin_texte)

        if debut > fin:
            raise ValueError(
                f"Plage invalide : {plage.group(0)}"
            )

        return range(debut, fin + 1)

    if "*" in url_modele:
        return range(
            1,
            MAX_PAGES_SECURITE + 1,
        )

    return [None]


def scanner_urls_extractions(deja_envoyes):
    magnets = []

    for url_modele in lire_urls_extractions():
        try:
            numeros_pages = obtenir_numeros_pages(
                url_modele
            )
        except ValueError as error:
            print(
                f"[ERREUR] {error} dans {url_modele}"
            )
            continue

        for numero_page in numeros_pages:
            url_page = construire_url_page(
                url_modele,
                numero_page,
            )

            print(
                f"Analyse de la page : {url_page}"
            )

            try:
                html = telecharger_page(url_page)
                trouves = extraire_magnets_html(html)

            except requests.RequestException as error:
                print(
                    f"[ERREUR] Impossible de scanner "
                    f"{url_page} : {error}"
                )
                break

            if not trouves:
                print(
                    "Aucun magnet trouvé. "
                    "Arrêt du scan."
                )
                break

            magnet_deja_connu = False

            for magnet in trouves:
                try:
                    identifiant = identifier_lien(
                        magnet
                    )
                except ValueError:
                    continue

                if identifiant in deja_envoyes:
                    magnet_deja_connu = True
                else:
                    magnets.append(magnet)

            if magnet_deja_connu:
                print(
                    "Un magnet déjà présent dans les "
                    "journaux a été trouvé. "
                    "Arrêt du scan."
                )
                break

    return list(dict.fromkeys(magnets))


def envoyer_lien(lien):
    url = BASE_URL + quote(
        lien,
        safe="",
    )

    response = requests.get(
        url,
        timeout=30,
        headers={
            "Referrer-Policy": "no-referrer",
        },
        allow_redirects=True,
    )

    return response.status_code


def main():
    deja_envoyes = lire_log()

    liens = lire_liens()

    magnets_extraits = scanner_urls_extractions(
        deja_envoyes
    )

    liens.extend(magnets_extraits)

    liens = list(
        dict.fromkeys(liens)
    )

    if not liens:
        print(
            "Aucun lien ou magnet trouvé."
        )
        return

    nouveaux_liens = []
    identifiants_vus = set()

    for lien in liens:
        try:
            identifiant = identifier_lien(lien)
        except ValueError as error:
            print(f"[IGNORÉ] {error}")
            continue

        if identifiant in deja_envoyes:
            print(f"[DÉJÀ ENVOYÉ] {lien}")
            continue

        if identifiant in identifiants_vus:
            print(f"[DOUBLON] {lien}")
            continue

        identifiants_vus.add(identifiant)

        nouveaux_liens.append(
            (lien, identifiant)
        )

    if not nouveaux_liens:
        supprimer_liens_envoyes(
            deja_envoyes
        )

        print(
            "Aucun nouveau lien à envoyer."
        )
        return

    print(
        f"{len(nouveaux_liens)} nouveau(x) "
        "lien(s) à envoyer."
    )

    identifiants_envoyes = set(
        deja_envoyes
    )

    liens_echoues = []

    for index, (lien, identifiant) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        try:
            status_code = envoyer_lien(lien)

            if 200 <= status_code < 400:
                print(
                    f"[OK] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )

                identifiants_envoyes.add(
                    identifiant
                )

            else:
                print(
                    f"[ERREUR] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )

                liens_echoues.append(lien)

        except requests.RequestException as error:
            print(
                f"[ERREUR] {index}/"
                f"{len(nouveaux_liens)} - "
                f"{lien} - {error}"
            )

            liens_echoues.append(lien)

    ecrire_log(identifiants_envoyes)

    supprimer_liens_envoyes(
        identifiants_envoyes
    )

    ajouter_liens_echoues(
        liens_echoues
    )

    print(
        "Les journaux dans log-url/ "
        "ont été mis à jour."
    )


if __name__ == "__main__":
    main()
