import argparse
import os
import re
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import requests
from bs4 import BeautifulSoup


# ==========================================================================
# CONFIGURATION
# ==========================================================================

FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("pages-à-extraire.txt")
DOSSIER_LOG = Path("log-url")

NOM_SECRET_KEEPSHARE = "KEEPSHARE_TOKEN"

MAX_PAGES_SECURITE = 1000
TIMEOUT_HTTP = 30

USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:136.0) Gecko/136.0 Firefox/136.0"

MAGNET_PREFIX = "magnet:?xt=urn:btih:"

ARRETER_SI_PAGE_SANS_MAGNET = True
ARRETER_SI_MAGNETS_DEJA_ENVOYES = True


def obtenir_base_url_envoi():
    """
    Récupère le token KeepShare depuis le Repository secret
    et construit l'URL d'envoi.
    """

    token = os.environ.get(NOM_SECRET_KEEPSHARE)

    if token is None:
        raise RuntimeError(
            "Erreur de configuration : le Repository secret "
            f"'{NOM_SECRET_KEEPSHARE}' est absent. "
            "Ajoutez-le dans Settings > Secrets and variables "
            "> Actions."
        )

    token = token.strip()

    if not token:
        raise RuntimeError(
            "Erreur de configuration : le Repository secret "
            f"'{NOM_SECRET_KEEPSHARE}' est vide."
        )

    return (
        "https://keepshare.org/"
        + quote(token, safe="")
        + "/"
    )


BASE_URL_ENVOI = obtenir_base_url_envoi()


# ==========================================================================
# EXPRESSIONS RÉGULIÈRES
# ==========================================================================

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

PATTERN_LISTE_PAGES = re.compile(
    r"<(\d+(?:\+\d+)+)>"
)

PATTERN_TOKEN_PAGES = re.compile(
    r"<([^<>]*)>"
)

PATTERN_URL_SIMPLE = re.compile(
    r"""https?://[^\s'"]+""",
    re.IGNORECASE,
)

PATTERN_MAGNET_HASH = re.compile(
    r"xt=urn:btih:([^&\s]+)",
    re.IGNORECASE,
)


# ==========================================================================
# SESSION HTTP
# ==========================================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }
)


# ==========================================================================
# OUTILS GÉNÉRAUX
# ==========================================================================

def supprimer_ponctuation_exterieure(valeur):
    return valeur.strip().strip(
        " \t\r\n.,;:)]}\"'"
    )


def dedoublonner(valeurs):
    return list(dict.fromkeys(valeurs))


def lire_fichier(fichier):
    if not fichier.exists():
        return ""

    return fichier.read_text(
        encoding="utf-8"
    )


def ecrire_fichier(fichier, contenu):
    fichier.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fichier.write_text(
        contenu,
        encoding="utf-8",
    )


# ==========================================================================
# EXTRACTION DES LIENS
# ==========================================================================

def extraire_liens(texte):
    liens = []

    for match in PATTERN_URLS.finditer(texte):
        lien = supprimer_ponctuation_exterieure(
            match.group(0)
        )

        if lien:
            liens.append(lien)

    return dedoublonner(liens)


def reduire_lien_pour_terminal(lien):
    match = re.match(
        r"(magnet:\?xt=urn:btih:[^&\s]+)",
        lien,
        flags=re.IGNORECASE,
    )

    return match.group(1) if match else lien


def lire_liens_a_envoyer():
    return extraire_liens(
        lire_fichier(FICHIER_LIENS)
    )


# ==========================================================================
# LECTURE DES URL À SCANNER
# ==========================================================================

def lire_urls_extractions():
    urls = []
    url_en_cours = None

    for ligne in lire_fichier(
        FICHIER_EXTRACTIONS
    ).splitlines():

        ligne = ligne.strip()

        if not ligne or ligne.startswith("#"):
            continue

        urls_trouvees = PATTERN_URL_SIMPLE.findall(
            ligne
        )

        if urls_trouvees:
            if url_en_cours:
                urls.append(
                    supprimer_ponctuation_exterieure(
                        url_en_cours
                    )
                )

            for url in urls_trouvees[:-1]:
                urls.append(
                    supprimer_ponctuation_exterieure(
                        url
                    )
                )

            url_en_cours = urls_trouvees[-1]

        elif url_en_cours:
            url_en_cours += ligne

    if url_en_cours:
        urls.append(
            supprimer_ponctuation_exterieure(
                url_en_cours
            )
        )

    return dedoublonner(urls)


# ==========================================================================
# REQUÊTES HTTP
# ==========================================================================

def telecharger_page(url):
    response = SESSION.get(
        url,
        timeout=TIMEOUT_HTTP,
    )

    response.raise_for_status()

    return response.text


def envoyer_lien(lien):
    url = BASE_URL_ENVOI + quote(
        lien,
        safe="",
    )

    response = SESSION.get(
        url,
        timeout=TIMEOUT_HTTP,
        headers={
            "Referrer-Policy": "no-referrer",
        },
        allow_redirects=True,
    )

    return response.status_code


# ==========================================================================
# IDENTIFICATION DES LIENS
# ==========================================================================

def identifier_lien(lien):
    lien = lien.strip()

    if lien.lower().startswith(MAGNET_PREFIX):
        partie = urlsplit(lien)

        valeurs_xt = parse_qs(
            partie.query
        ).get("xt", [])

        if valeurs_xt:
            xt = valeurs_xt[0]

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

        match = PATTERN_MAGNET_HASH.search(lien)

        if not match:
            raise ValueError(
                f"Hash magnet introuvable : {lien}"
            )

        return (
            MAGNET_PREFIX,
            "/" + match.group(1).upper(),
        )

    partie = urlsplit(lien)

    if partie.scheme.lower() not in {
        "http",
        "https",
    }:
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


# ==========================================================================
# EXTRACTION DES MAGNETS
# ==========================================================================

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

    return dedoublonner(magnets)


# ==========================================================================
# GESTION DES JOURNAUX
# ==========================================================================

def obtenir_nom_fichier_log(identifiant):
    base, chemin = identifiant

    if base == MAGNET_PREFIX:
        prefixe = "magnet"
    else:
        domaine = urlsplit(base).netloc.lower()

        prefixe = re.sub(
            r"[^a-z0-9]+",
            "",
            domaine,
        ) or "inconnu"

    valeur = chemin.lstrip("/").lower()

    premier_caractere = next(
        (
            caractere
            for caractere in valeur
            if caractere.isalnum()
        ),
        "autre",
    )

    return f"{prefixe}-{premier_caractere}.txt"


def chemin_fichier_log(identifiant):
    return DOSSIER_LOG / obtenir_nom_fichier_log(
        identifiant
    )


def lire_fichier_log(fichier_log):
    identifiants = set()
    base_actuelle = None

    for ligne in lire_fichier(
        fichier_log
    ).splitlines():

        ligne = ligne.strip()

        if not ligne:
            continue

        if ligne.startswith("/"):
            if base_actuelle:
                identifiants.add(
                    (
                        base_actuelle,
                        ligne,
                    )
                )
        else:
            base_actuelle = ligne

    return identifiants


def lire_log():
    DOSSIER_LOG.mkdir(
        parents=True,
        exist_ok=True,
    )

    identifiants = set()

    for fichier_log in DOSSIER_LOG.glob(
        "*.txt"
    ):
        identifiants.update(
            lire_fichier_log(fichier_log)
        )

    return identifiants


def ecrire_log(identifiants):
    groupes_fichiers = OrderedDict()

    for identifiant in sorted(identifiants):
        fichier_log = chemin_fichier_log(
            identifiant
        )

        groupes_fichiers.setdefault(
            fichier_log,
            [],
        ).append(identifiant)

    for (
        fichier_log,
        identifiants_fichier,
    ) in groupes_fichiers.items():

        groupes_bases = OrderedDict()

        for base, chemin in identifiants_fichier:
            groupes_bases.setdefault(
                base,
                [],
            ).append(chemin)

        lignes = []

        for base, chemins in groupes_bases.items():
            if lignes:
                lignes.append("")

            lignes.append(base)
            lignes.extend(
                dedoublonner(chemins)
            )

        ecrire_fichier(
            fichier_log,
            "\n".join(lignes) + "\n",
        )


# ==========================================================================
# MODIFICATION DES FICHIERS
# ==========================================================================

def supprimer_liens_envoyes(
    identifiants_envoyes,
):
    contenu_original = lire_fichier(
        FICHIER_LIENS
    )

    if not contenu_original:
        return

    def remplacer_lien(match):
        lien_original = match.group(0)

        lien = supprimer_ponctuation_exterieure(
            lien_original
        )

        try:
            identifiant = identifier_lien(
                lien
            )

        except ValueError:
            return lien_original

        if identifiant in identifiants_envoyes:
            return ""

        return lien_original

    contenu_nouveau = PATTERN_URLS.sub(
        remplacer_lien,
        contenu_original,
    )

    if contenu_nouveau != contenu_original:
        ecrire_fichier(
            FICHIER_LIENS,
            contenu_nouveau,
        )

        print(
            "Les liens envoyés ont été supprimés "
            f"de {FICHIER_LIENS}."
        )


def ajouter_liens_echoues(liens_echoues):
    if not liens_echoues:
        return

    contenu_existant = lire_fichier(
        FICHIER_LIENS
    )

    liens_existants = set(
        extraire_liens(contenu_existant)
    )

    liens_a_ajouter = [
        lien
        for lien in liens_echoues
        if lien not in liens_existants
    ]

    if not liens_a_ajouter:
        return

    contenu_nouveau = contenu_existant

    if (
        contenu_nouveau
        and not contenu_nouveau.endswith("\n")
    ):
        contenu_nouveau += "\n"

    contenu_nouveau += (
        "\n".join(liens_a_ajouter)
        + "\n"
    )

    ecrire_fichier(
        FICHIER_LIENS,
        contenu_nouveau,
    )

    print(
        f"{len(liens_a_ajouter)} lien(s) échoué(s) "
        "ajouté(s) pour réessai."
    )


# ==========================================================================
# PAGINATION
# ==========================================================================

def obtenir_numeros_pages(url_modele):
    tokens = PATTERN_TOKEN_PAGES.findall(
        url_modele
    )

    if tokens:
        if len(tokens) > 1:
            raise ValueError(
                "Un seul bloc de pagination est "
                f"autorisé : {url_modele}"
            )

        contenu = tokens[0]

        if "-" in contenu and "+" in contenu:
            raise ValueError(
                "Les opérateurs '-' et '+' ne peuvent "
                f"pas être combinés : <{contenu}>"
            )

        expression_plage = PATTERN_PLAGE_PAGES.fullmatch(
            f"<{contenu}>"
        )

        if expression_plage:
            debut_texte, fin_texte = (
                expression_plage.groups()
            )

            if (
                debut_texte == "*"
                and fin_texte == "*"
            ):
                raise ValueError(
                    f"Plage invalide : <{contenu}>"
                )

            debut = (
                1
                if debut_texte == "*"
                else int(debut_texte)
            )

            fin = (
                MAX_PAGES_SECURITE
                if fin_texte == "*"
                else int(fin_texte)
            )

            if debut > fin:
                raise ValueError(
                    f"Plage invalide : <{contenu}>"
                )

            return range(
                debut,
                fin + 1,
            )

        expression_liste = PATTERN_LISTE_PAGES.fullmatch(
            f"<{contenu}>"
        )

        if expression_liste:
            numeros = [
                int(numero)
                for numero in contenu.split("+")
            ]

            return dedoublonner(numeros)

        raise ValueError(
            f"Syntaxe de pagination invalide : "
            f"<{contenu}>"
        )

    if "*" in url_modele:
        return range(
            1,
            MAX_PAGES_SECURITE + 1,
        )

    return [None]


def construire_url_page(url_modele, numero_page):
    if numero_page is None:
        return url_modele

    if PATTERN_TOKEN_PAGES.search(url_modele):
        return PATTERN_TOKEN_PAGES.sub(
            str(numero_page),
            url_modele,
            count=1,
        )

    return url_modele.replace(
        "*",
        str(numero_page),
    )


# ==========================================================================
# COMPRESSION DES PAGES ÉCHOUÉES
# ==========================================================================

def compacter_pages_echouees(pages):
    groupes = OrderedDict()

    for page in dedoublonner(pages):
        match = re.match(
            r"^(.*?)(\d+)(\D*)$",
            page,
        )

        if not match:
            groupes.setdefault(
                ("url", page),
                [],
            )

            continue

        prefixe = match.group(1)
        numero = int(match.group(2))
        suffixe = match.group(3)

        groupes.setdefault(
            (
                "page",
                prefixe,
                suffixe,
            ),
            [],
        ).append(numero)

    resultat = []

    for cle, valeurs in groupes.items():
        if cle[0] == "url":
            resultat.append(cle[1])
            continue

        _, prefixe, suffixe = cle

        numeros = sorted(set(valeurs))

        suites = []
        suite_actuelle = [numeros[0]]

        for numero in numeros[1:]:
            precedent = suite_actuelle[-1]

            if numero == precedent + 1:
                suite_actuelle.append(numero)
            else:
                suites.append(suite_actuelle)
                suite_actuelle = [numero]

        suites.append(suite_actuelle)

        elements = []

        for suite in suites:
            if len(suite) >= 2:
                debut = suite[0]
                fin = suite[-1]

                valeur = (
                    f"{prefixe}"
                    f"<{debut}-{fin}>"
                    f"{suffixe}"
                )

                elements.append(
                    (
                        debut,
                        valeur,
                    )
                )

        numeros_isoles = [
            suite[0]
            for suite in suites
            if len(suite) == 1
        ]

        if len(numeros_isoles) >= 2:
            numeros_texte = "+".join(
                str(numero)
                for numero in numeros_isoles
            )

            valeur = (
                f"{prefixe}"
                f"<{numeros_texte}>"
                f"{suffixe}"
            )

            elements.append(
                (
                    numeros_isoles[0],
                    valeur,
                )
            )

        elif len(numeros_isoles) == 1:
            numero = numeros_isoles[0]

            valeur = (
                f"{prefixe}"
                f"{numero}"
                f"{suffixe}"
            )

            elements.append(
                (
                    numero,
                    valeur,
                )
            )

        elements.sort(
            key=lambda element: element[0]
        )

        resultat.extend(
            valeur
            for _, valeur in elements
        )

    return resultat


def ajouter_pages_echouees(pages_echouees):
    if not pages_echouees:
        return

    contenu_existant = lire_fichier(
        FICHIER_EXTRACTIONS
    )

    pages_compactees = compacter_pages_echouees(
        pages_echouees
    )

    lignes_existantes = {
        ligne.strip()
        for ligne in contenu_existant.splitlines()
        if ligne.strip()
    }

    lignes_a_ajouter = []

    for page in pages_compactees:
        ligne = f"# PAGE ÉCHOUÉE : {page}"

        if ligne not in lignes_existantes:
            lignes_a_ajouter.append(ligne)

    if not lignes_a_ajouter:
        return

    contenu_nouveau = contenu_existant

    if (
        contenu_nouveau
        and not contenu_nouveau.endswith("\n")
    ):
        contenu_nouveau += "\n"

    if (
        contenu_nouveau
        and not contenu_nouveau.endswith("\n\n")
    ):
        contenu_nouveau += "\n"

    contenu_nouveau += (
        "\n".join(lignes_a_ajouter)
        + "\n"
    )

    ecrire_fichier(
        FICHIER_EXTRACTIONS,
        contenu_nouveau,
    )

    print(
        f"{len(lignes_a_ajouter)} groupe(s) de page(s) "
        "échouée(s) ajouté(s) dans "
        f"{FICHIER_EXTRACTIONS}."
    )


# ==========================================================================
# SCAN DES PAGES
# ==========================================================================

def scanner_urls_extractions(
    identifiants_deja_envoyes,
    force_scan=False,
):
    magnets = []
    pages_echouees = []

    if force_scan:
        print(
            "Mode forcé activé : toutes les pages "
            "configurées seront scannées."
        )

    for url_modele in lire_urls_extractions():
        try:
            numeros_pages = obtenir_numeros_pages(
                url_modele
            )

        except ValueError as erreur:
            print(
                f"[ERREUR] {erreur} dans "
                f"{url_modele}"
            )

            continue

        for numero_page in numeros_pages:
            url_page = construire_url_page(
                url_modele,
                numero_page,
            )

            print(" ")
            print(
                f"Analyse de la page : {url_page}"
            )

            try:
                html = telecharger_page(
                    url_page
                )

                magnets_page = extraire_magnets_html(
                    html
                )

            except requests.RequestException as erreur:
                print(
                    "[ERREUR] Impossible de scanner "
                    f"{url_page} : {erreur}"
                )

                pages_echouees.append(url_page)
                continue

            if not magnets_page:
                print("Aucun magnet trouvé.")

                if (
                    ARRETER_SI_PAGE_SANS_MAGNET
                    and not force_scan
                ):
                    print("Arrêt du scan.")
                    break

                continue

            magnets_nouveaux = []

            for magnet in magnets_page:
                try:
                    identifiant = identifier_lien(
                        magnet
                    )

                except ValueError:
                    continue

                if (
                    identifiant
                    not in identifiants_deja_envoyes
                ):
                    magnets_nouveaux.append(
                        magnet
                    )

            magnets_nouveaux = dedoublonner(
                magnets_nouveaux
            )

            if magnets_nouveaux:
                magnets.extend(
                    magnets_nouveaux
                )

                print(
                    f"{len(magnets_nouveaux)} nouveau(x) "
                    "magnet(s) trouvé(s)."
                )

                continue

            print(
                "Aucun nouveau magnet sur cette page. "
                "Tous les magnets sont déjà présents "
                "dans les journaux."
            )

            if (
                ARRETER_SI_MAGNETS_DEJA_ENVOYES
                and not force_scan
            ):
                print("Arrêt du scan.")
                break

    ajouter_pages_echouees(
        pages_echouees
    )

    return dedoublonner(magnets)


# ==========================================================================
# PRÉPARATION DES LIENS
# ==========================================================================

def preparer_liens_a_envoyer(
    liens,
    identifiants_deja_envoyes,
):
    nouveaux_liens = []
    identifiants_vus = set()

    for lien in liens:
        try:
            identifiant = identifier_lien(
                lien
            )

        except ValueError as erreur:
            print(f"[IGNORÉ] {erreur}")
            continue

        lien_terminal = reduire_lien_pour_terminal(
            lien
        )

        if identifiant in identifiants_deja_envoyes:
            print(
                f"[DÉJÀ ENVOYÉ] {lien_terminal}"
            )

            continue

        if identifiant in identifiants_vus:
            print(
                f"[DOUBLON] {lien_terminal}"
            )

            continue

        identifiants_vus.add(
            identifiant
        )

        nouveaux_liens.append(
            (
                lien,
                identifiant,
            )
        )

    return nouveaux_liens


# ==========================================================================
# ENVOI DES LIENS
# ==========================================================================

def envoyer_nouveaux_liens(
    nouveaux_liens,
    identifiants_envoyes,
):
    liens_echoues = []
    total = len(nouveaux_liens)

    for index, (
        lien,
        identifiant,
    ) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        lien_terminal = reduire_lien_pour_terminal(
            lien
        )

        try:
            status_code = envoyer_lien(
                lien
            )

        except requests.RequestException as erreur:
            print(
                f"[ERREUR] {index}/{total} - "
                f"{lien_terminal} - {erreur}"
            )

            liens_echoues.append(lien)
            continue

        if 200 <= status_code < 400:
            print(
                f"[OK] {index}/{total} - "
                f"HTTP {status_code} - "
                f"{lien_terminal}"
            )

            identifiants_envoyes.add(
                identifiant
            )

        else:
            print(
                f"[ERREUR] {index}/{total} - "
                f"HTTP {status_code} - "
                f"{lien_terminal}"
            )

            liens_echoues.append(lien)

    return liens_echoues


# ==========================================================================
# PROGRAMME PRINCIPAL
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extrait et envoie des liens, "
            "avec prise en charge de la pagination."
        )
    )

    parser.add_argument(
        "--force-scan",
        action="store_true",
        help=(
            "Force le scan de toutes les pages configurées "
            "sans arrêt anticipé."
        ),
    )

    arguments = parser.parse_args()
    force_scan = arguments.force_scan

    identifiants_deja_envoyes = lire_log()

    liens = lire_liens_a_envoyer()

    magnets_extraits = scanner_urls_extractions(
        identifiants_deja_envoyes,
        force_scan=force_scan,
    )

    liens.extend(magnets_extraits)
    liens = dedoublonner(liens)

    if not liens:
        print(
            "Aucun lien ou magnet trouvé."
        )

        return

    nouveaux_liens = preparer_liens_a_envoyer(
        liens,
        identifiants_deja_envoyes,
    )

    if not nouveaux_liens:
        supprimer_liens_envoyes(
            identifiants_deja_envoyes
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
        identifiants_deja_envoyes
    )

    liens_echoues = envoyer_nouveaux_liens(
        nouveaux_liens,
        identifiants_envoyes,
    )

    ecrire_log(
        identifiants_envoyes
    )

    supprimer_liens_envoyes(
        identifiants_envoyes
    )

    ajouter_liens_echoues(
        liens_echoues
    )

    print(
        f"Les journaux dans {DOSSIER_LOG}/ "
        "ont été mis à jour."
    )


if __name__ == "__main__":
    try:
        main()

    except RuntimeError as erreur:
        print(f"[ERREUR] {erreur}")
        raise SystemExit(1)
