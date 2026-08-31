from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
import re

import requests
from bs4 import BeautifulSoup


FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("urls-extractions.txt")

DOSSIER_LOG = Path("log-url")
FICHIER_LOG_ANCIEN = Path("log-url.txt")

BASE_URL = "https://keepshare.org/ldf6j5ti/"

# Limite de sécurité pour les paginations ouvertes.
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
    """
    Extrait plusieurs URLs ou magnets présents dans un texte.
    """
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
    """
    Lit le fichier manuel liens-à-envoyer.txt.
    """
    if not FICHIER_LIENS.exists():
        return []

    texte = FICHIER_LIENS.read_text(
        encoding="utf-8"
    )

    return extraire_liens(texte)


def nettoyer_ligne(ligne):
    """
    Nettoie les caractères inutiles autour d'une ligne.

    Les caractères < et > sont conservés pour les plages de pages.
    """
    return ligne.strip().strip(
        " \t\r\n.,;:)]}\"'"
    )


def lire_urls_extractions():
    """
    Lit urls-extractions.txt.

    Formats acceptés :

        https://exemple.com/page=1
        https://exemple.com/page=*
        https://exemple.com/page=<1-7>
        https://exemple.com/page=<29-*>
        https://exemple.com/page=<*-10>
    """
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
    """
    Télécharge une page HTML.
    """
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    response.raise_for_status()

    return response.text


def extraire_magnets_html(html):
    """
    Recherche les magnets présents dans les attributs HTML.
    """
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
    """
    Crée un identifiant compact pour le journal.

    Exemple URL :

        https://exemple.com/test?a=1

    devient :

        ("https://exemple.com", "/test?a=1")

    Exemple magnet :

        magnet:?xt=urn:btih:ABC123&dn=test

    devient :

        ("magnet:?xt=urn:btih:", "/ABC123")
    """
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

    if partie.fragment:
        chemin += "#" + partie.fragment

    return base, chemin


def lire_fichier_log(chemin_fichier):
    """
    Lit un fichier de journal et reconstruit ses identifiants.
    """
    lignes = chemin_fichier.read_text(
        encoding="utf-8"
    ).splitlines()

    deja_envoyes = set()
    base_actuelle = None

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
    """
    Lit tous les fichiers présents dans log-url/.

    Le fichier log-url.txt est également lu pour permettre
    une migration automatique vers le nouveau format.
    """
    DOSSIER_LOG.mkdir(
        exist_ok=True
    )

    deja_envoyes = set()

    fichiers_logs = sorted(
        DOSSIER_LOG.glob("path-*.txt")
    )

    for fichier_log in fichiers_logs:
        deja_envoyes.update(
            lire_fichier_log(fichier_log)
        )

    # Compatibilité avec l'ancien journal unique.
    if FICHIER_LOG_ANCIEN.exists():
        deja_envoyes.update(
            lire_fichier_log(FICHIER_LOG_ANCIEN)
        )

    return deja_envoyes


def obtenir_prefixe_log(identifiant):
    """
    Détermine le nom du journal correspondant à un identifiant.

    Exemples :

        magnet ... /ABC123
        -> path-magnet-a.txt

        magnet ... /9ABC123
        -> path-magnet-9.txt

        https://google.com + /index
        -> path-googlecom-i.txt
    """
    base, chemin = identifiant

    if base == MAGNET_PREFIX:
        prefixe = "path-magnet"
    else:
        partie = urlsplit(base)

        domaine = partie.netloc.lower()

        # Conserve uniquement les caractères adaptés à un nom de fichier.
        domaine = re.sub(
            r"[^a-z0-9]+",
            "",
            domaine,
        )

        if not domaine:
            domaine = "inconnu"

        prefixe = f"path-{domaine}"

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
    """
    Retourne le chemin complet du fichier de journal.
    """
    return DOSSIER_LOG / obtenir_prefixe_log(
        identifiant
    )


def ecrire_log(identifiants):
    """
    Réécrit les journaux répartis dans log-url/.
    """
    DOSSIER_LOG.mkdir(
        exist_ok=True
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

    for fichier_log, identifiants_fichier in grupos.items():
        groupes_base = OrderedDict()

        for base, chemin in identifiants_fichier:
            if base not in groupes_base:
                groupes_base[base] = []

            if chemin not in grupos_base[base]:
                grupos_base[base].append(chemin)

        lignes = []

        for base, chemins in grupos_base.items():
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
