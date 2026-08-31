from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
import re

import requests
from bs4 import BeautifulSoup


FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("urls-extractions.txt")
FICHIER_LOG = Path("log-url.txt")

BASE_URL = "https://keepshare.org/ldf6j5ti/"

# Limite de sécurité uniquement.
# Le nombre de pages n'est pas pré-rempli :
# le scan s'arrête avant cette limite lorsqu'un lien
# déjà présent dans log-url.txt est trouvé.
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


def extraire_liens(texte):
    """
    Extrait plusieurs URLs ou magnets présents dans un texte.

    Plusieurs liens peuvent être présents sur la même ligne.
    """
    liens = []

    for match in PATTERN_URLS.finditer(texte):
        lien = match.group(0).strip()

        lien = lien.strip(
            " \t\r\n.,;:)]}>\"'"
        )

        if lien:
            liens.append(lien)

    return list(dict.fromkeys(liens))


def lire_liens():
    """
    Lit le fichier manuel liens à envoyer.txt.
    """
    if not FICHIER_LIENS.exists():
        return []

    texte = FICHIER_LIENS.read_text(encoding="utf-8")

    return extraire_liens(texte)


def nettoyer_ligne(ligne):
    return ligne.strip().strip(" \t\r\n.,;:)]}>\"'")


def lire_urls_extractions():
    """
    Lit urls-extractions.txt.

    Une ligne qui commence par http:// ou https://
    démarre une nouvelle URL.

    Une ligne qui ne commence pas par http:// ou https://
    est ajoutée à l'URL précédente.

    Exemple :

    https://exemple.com/recherche?q=test
    &p=*

    devient :

    https://exemple.com/recherche?q=test&p=*
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

        # Plusieurs URLs HTTP(S) peuvent être présentes sur une même ligne.
        urls_absolues = re.findall(
            r"https?://[^\s<>'\"]+",
            ligne,
            flags=re.IGNORECASE,
        )

        if urls_absolues:
            if url_actuelle:
                urls.append(nettoyer_ligne(url_actuelle))

            # Les URLs précédentes de la même ligne sont terminées.
            for url in urls_absolues[:-1]:
                urls.append(nettoyer_ligne(url))

            # La dernière URL peut recevoir une ligne complémentaire.
            url_actuelle = urls_absolues[-1]

        elif url_actuelle:
            # Ajout d'un paramètre ou d'une continuation à l'URL précédente.
            url_actuelle += ligne

    if url_actuelle:
        urls.append(nettoyer_ligne(url_actuelle))

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
    Reproduit le comportement du bookmarklet :
    recherche les magnets présents dans les attributs HTML.
    """
    soup = BeautifulSoup(html, "html.parser")
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

    Exemple HTTP :

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

        # Méthode de secours
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


def lire_log():
    """
    Lit log-url.txt et reconstruit les identifiants déjà envoyés.

    Format attendu :

    https://exemple.com
    /page-1
    /page-2

    magnet:?xt=urn:btih:
    /HASH1
    /HASH2
    """
    FICHIER_LOG.touch(exist_ok=True)

    lignes = FICHIER_LOG.read_text(
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


def ecrire_log(identifiants):
    """
    Réécrit log-url.txt en regroupant les chemins
    sous leur base respective.
    """
    groupes = OrderedDict()

    for base, chemin in identifiants:
        if base not in groupes:
            groupes[base] = []

        if chemin not in groupes[base]:
            groupes[base].append(chemin)

    lignes = []

    for base, chemins in groupes.items():
        if lignes:
            lignes.append("")

        lignes.append(base)
        lignes.extend(chemins)

    contenu = "\n".join(lignes)

    if contenu:
        contenu += "\n"

    FICHIER_LOG.write_text(
        contenu,
        encoding="utf-8",
    )


def scanner_urls_extractions(deja_envoyes):
    """
    Scanne les URLs présentes dans urls-extractions.txt.

    Pour une URL sans *, une seule page est scannée.

    Pour une URL contenant *, le script commence à la page 1,
    puis continue avec les pages suivantes.

    Exemple :

        https://exemple.com/recherche&p=*

    devient :

        https://exemple.com/recherche&p=1
        https://exemple.com/recherche&p=2
        https://exemple.com/recherche&p=3

    Le scan s'arrête lorsqu'un magnet déjà présent dans
    log-url.txt est trouvé.
    """
    magnets = []

    for base_url in lire_urls_extractions():
        page = 1
        pagination = "*" in base_url

        while True:
            if pagination:
                if page > MAX_PAGES_SECURITE:
                    print(
                        "Limite de sécurité atteinte : "
                        f"{MAX_PAGES_SECURITE} pages."
                    )
                    break

                url_page = base_url.replace(
                    "*",
                    str(page),
                )
            else:
                url_page = base_url

            print(f"Analyse de la page : {url_page}")

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
                    "Aucun magnet trouvé sur cette page. "
                    "Arrêt du scan."
                )
                break

            magnet_deja_connu = False

            for magnet in trouves:
                try:
                    identifiant = identifier_lien(magnet)
                except ValueError:
                    continue

                if identifiant in deja_envoyes:
                    magnet_deja_connu = True
                else:
                    magnets.append(magnet)

            if magnet_deja_connu:
                print(
                    "Un magnet déjà présent dans "
                    "log-url.txt a été trouvé. "
                    "Arrêt du scan."
                )
                break

            if not pagination:
                break

            page += 1

    return list(dict.fromkeys(magnets))


def envoyer_lien(lien):
    """
    Envoie le lien vers l'URL de base.
    """
    url = BASE_URL + quote(lien, safe="")

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

    # Liens ajoutés manuellement
    liens = lire_liens()

    # Magnets extraits des pages HTML
    magnets_extraits = scanner_urls_extractions(
        deja_envoyes
    )

    liens.extend(magnets_extraits)

    # Suppression des doublons bruts
    liens = list(dict.fromkeys(liens))

    if not liens:
        print("Aucun lien ou magnet trouvé.")
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
        print("Aucun nouveau lien à envoyer.")
        return

    print(
        f"{len(nouveaux_liens)} nouveau(x) lien(s) "
        "à envoyer."
    )

    identifiants_envoyes = set(deja_envoyes)

    for index, (lien, identifiant) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        try:
            status_code = envoyer_lien(lien)

            if 200 <= status_code < 400:
                print(
                    f"[OK] {index}/{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )

                identifiants_envoyes.add(identifiant)

            else:
                print(
                    f"[ERREUR] {index}/{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )

        except requests.RequestException as error:
            print(
                f"[ERREUR] {index}/{len(nouveaux_liens)} - "
                f"{lien} - {error}"
            )

    ecrire_log(identifiants_envoyes)

    print()
    print("Le fichier log-url.txt a été mis à jour.")


if __name__ == "__main__":
    main()

