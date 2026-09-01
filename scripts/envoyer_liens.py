from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
import os
import re

import requests
from bs4 import BeautifulSoup


FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("bases-à-extraire.txt")
FICHIER_PAGES_A_REESSAYER = Path("pages-à-envoyer.txt")
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


def nettoyer_ligne(ligne):
    return ligne.strip().strip(
        " \t\r\n.,;:)]}\"'"
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


def reduire_lien_pour_terminal(lien):
    """
    Réduit un magnet uniquement pour l'affichage.
    """

    match = re.match(
        r"(magnet:\?xt=urn:btih:[^&\s]+)",
        lien,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return lien


def lire_liens():
    if not FICHIER_LIENS.exists():
        return []

    try:
        texte = FICHIER_LIENS.read_text(
            encoding="utf-8"
        )

    except OSError as error:
        print(
            f"[ERREUR] Impossible de lire "
            f"{FICHIER_LIENS} : {error}"
        )
        return []

    return extraire_liens(texte)


def lire_urls_extractions():
    """
    Lit les URLs présentes dans bases-à-extraire.txt.

    Une URL peut être coupée sur plusieurs lignes.
    """

    if not FICHIER_EXTRACTIONS.exists():
        return []

    urls = []
    url_actuelle = None

    try:
        lignes = FICHIER_EXTRACTIONS.read_text(
            encoding="utf-8"
        ).splitlines()

    except OSError as error:
        print(
            f"[ERREUR] Impossible de lire "
            f"{FICHIER_EXTRACTIONS} : {error}"
        )
        return []

    for ligne in lignes:
        ligne = ligne.strip()

        if not ligne or ligne.startswith("#"):
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


def lire_pages_a_reessayer():
    """
    Lit les URLs enregistrées dans
    pages-à-envoyer.txt.

    Les lignes vides, les commentaires et les
    doublons sont ignorés.
    """

    if not FICHIER_PAGES_A_REESSAYER.exists():
        return []

    try:
        lignes = FICHIER_PAGES_A_REESSAYER.read_text(
            encoding="utf-8"
        ).splitlines()

    except OSError as error:
        print(
            f"[ERREUR] Impossible de lire "
            f"{FICHIER_PAGES_A_REESSAYER} : {error}"
        )
        return []

    pages = []
    pages_vues = set()

    for ligne in lignes:
        ligne = ligne.strip()

        if not ligne or ligne.startswith("#"):
            continue

        ligne = nettoyer_ligne(ligne)

        if not ligne or ligne in pages_vues:
            continue

        pages_vues.add(ligne)
        pages.append(ligne)

    return pages


def enregistrer_pages_a_reessayer(pages):
    """
    Réécrit pages-à-envoyer.txt.

    Les pages présentes dans `pages` sont conservées.

    Si la liste est vide, le fichier est supprimé.
    """

    pages_propres = []
    pages_vues = set()

    for page in pages:
        page = page.strip()

        if not page or page.startswith("#"):
            continue

        page = nettoyer_ligne(page)

        if not page or page in pages_vues:
            continue

        pages_vues.add(page)
        pages_propres.append(page)

    try:
        if not pages_propres:
            if FICHIER_PAGES_A_REESSAYER.exists():
                FICHIER_PAGES_A_REESSAYER.unlink()

                print(
                    f"Aucune page restante. "
                    f"{FICHIER_PAGES_A_REESSAYER} supprimé."
                )

            return

        contenu = "\n".join(pages_propres) + "\n"

        fichier_temporaire = (
            FICHIER_PAGES_A_REESSAYER.with_name(
                FICHIER_PAGES_A_REESSAYER.name
                + ".tmp"
            )
        )

        fichier_temporaire.write_text(
            contenu,
            encoding="utf-8",
        )

        os.replace(
            fichier_temporaire,
            FICHIER_PAGES_A_REESSAYER,
        )

        print(
            f"{len(pages_propres)} page(s) conservée(s) "
            "pour réessai."
        )

    except OSError as error:
        print(
            f"[ERREUR] Impossible de modifier "
            f"{FICHIER_PAGES_A_REESSAYER} : {error}"
        )


def ajouter_page_a_reessayer(url_page):
    """
    Ajoute une page à pages-à-envoyer.txt.
    """

    url_page = nettoyer_ligne(url_page)

    if not url_page:
        return

    pages = lire_pages_a_reessayer()

    if url_page in pages:
        return

    pages.append(url_page)

    enregistrer_pages_a_reessayer(pages)

    print(
        f"Page ajoutée pour réessai : {url_page}"
    )


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
    """
    Transforme un lien en identifiant comparable.

    Deux magnets ayant le même hash sont considérés
    comme identiques, même si leur nom diffère.
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

    try:
        lignes = fichier_log.read_text(
            encoding="utf-8"
        ).splitlines()

    except OSError as error:
        print(
            f"[ERREUR] Impossible de lire "
            f"{fichier_log} : {error}"
        )
        return set()

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

        prefixe = domaine or "inconnu"

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
                groupes_base[base].append(chemin)

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
    """
    Supprime de liens-à-envoyer.txt les liens dont
    l'identifiant est présent dans les journaux.
    """

    if not FICHIER_LIENS.exists():
        return

    try:
        texte_original = FICHIER_LIENS.read_text(
            encoding="utf-8"
        )

    except OSError as error:
        print(
            f"[ERREUR] Impossible de lire "
            f"{FICHIER_LIENS} : {error}"
        )
        return

    def remplacer_lien(match):
        lien_original = match.group(0)
        lien = nettoyer_ligne(lien_original)

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

    if nouveau_texte == texte_original:
        return

    try:
        FICHIER_LIENS.write_text(
            nouveau_texte,
            encoding="utf-8",
        )

        print(
            "Les liens envoyés ont été supprimés "
            "de liens-à-envoyer.txt."
        )

    except OSError as error:
        print(
            f"[ERREUR] Impossible d'écrire "
            f"{FICHIER_LIENS} : {error}"
        )


def ajouter_liens_echoues(liens_echoues):
    """
    Ajoute les liens dont l'envoi a échoué dans
    liens-à-envoyer.txt.
    """

    if not liens_echoues:
        return

    contenu_existant = ""

    if FICHIER_LIENS.exists():
        try:
            contenu_existant = FICHIER_LIENS.read_text(
                encoding="utf-8"
            )

        except OSError as error:
            print(
                f"[ERREUR] Impossible de lire "
                f"{FICHIER_LIENS} : {error}"
            )
            return

    liens_existants = set(
        extraire_liens(contenu_existant)
    )

    liens_a_ajouter = []

    for lien in liens_echoues:
        if lien not in liens_existants:
            liens_a_ajouter.append(lien)
            liens_existants.add(lien)

    if not liens_a_ajouter:
        return

    lignes_nouvelles = (
        "\n".join(liens_a_ajouter)
        + "\n"
    )

    try:
        FICHIER_LIENS.write_text(
            contenu_existant + lignes_nouvelles,
            encoding="utf-8",
        )

        print(
            f"{len(liens_a_ajouter)} lien(s) échoué(s) "
            "ajouté(s) pour réessai."
        )

    except OSError as error:
        print(
            f"[ERREUR] Impossible d'écrire "
            f"{FICHIER_LIENS} : {error}"
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


def extraire_nouveaux_magnets(
    magnets,
    deja_envoyes,
):
    magnets_nouveaux = []
    identifiants_trouves = set()

    for magnet in magnets:
        try:
            identifiant = identifier_lien(magnet)

        except ValueError:
            print(
                f"[IGNORÉ] Magnet invalide : {magnet}"
            )
            continue

        if identifiant in deja_envoyes:
            continue

        if identifiant in identifiants_trouves:
            continue

        identifiants_trouves.add(identifiant)
        magnets_nouveaux.append(magnet)

    return magnets_nouveaux


def scanner_pages_a_reessayer(deja_envoyes):
    """
    Réessaie les URLs de pages-à-envoyer.txt.

    Une page est conservée uniquement si la requête
    échoue encore.

    Une page récupérée correctement est supprimée,
    même si aucun magnet n'est trouvé ou si le magnet
    est déjà présent dans les journaux.
    """

    pages = lire_pages_a_reessayer()

    if not pages:
        print(
            "Aucune page à réessayer."
        )
        return []

    magnets_trouves = []
    pages_en_echec = []

    print(
        f"{len(pages)} page(s) à réessayer."
    )

    for numero, url_page in enumerate(
        pages,
        start=1,
    ):
        print(
            f"[RÉESSAI {numero}/{len(pages)}] "
            f"{url_page}"
        )

        try:
            html = telecharger_page(url_page)

        except requests.RequestException as error:
            print(
                f"[ERREUR] Échec de la page : "
                f"{url_page}"
            )
            print(
                f"         {error}"
            )

            # Seules les pages ayant échoué
            # sont conservées.
            pages_en_echec.append(url_page)
            continue

        # La requête a réussi.
        # Cette URL n'est volontairement pas ajoutée
        # à pages_en_echec.
        magnets_page = extraire_magnets_html(html)

        print(
            f"[OK] Page récupérée : {url_page}"
        )

        print(
            f"     {len(magnets_page)} magnet(s) trouvé(s)."
        )

        magnets_nouveaux = (
            extraire_nouveaux_magnets(
                magnets_page,
                deja_envoyes,
            )
        )

        magnets_trouves.extend(
            magnets_nouveaux
        )

    # Réécriture après le traitement de toutes les pages.
    # Les pages réussies disparaissent du fichier.
    # Les pages en échec y restent.
    enregistrer_pages_a_reessayer(
        pages_en_echec
    )

    return list(
        dict.fromkeys(magnets_trouves)
    )


def scanner_urls_extractions(deja_envoyes):
    magnets = []

    for url_modele in lire_urls_extractions():
        try:
            numeros_pages = obtenir_numeros_pages(
                url_modele
            )

        except ValueError as error:
            print(
                f"[ERREUR] {error} dans "
                f"{url_modele}"
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

                ajouter_page_a_reessayer(
                    url_page
                )

                # On poursuit la plage.
                continue

            if not trouves:
                print(
                    "Aucun magnet trouvé. "
                    "Arrêt du scan."
                )
                break

            magnets_nouveaux_page = (
                extraire_nouveaux_magnets(
                    trouves,
                    deja_envoyes,
                )
            )

            if magnets_nouveaux_page:
                magnets.extend(
                    magnets_nouveaux_page
                )

                print(
                    f"{len(magnets_nouveaux_page)} "
                    "nouveau(x) magnet(s) trouvé(s). "
                    "Poursuite du scan."
                )

                continue

            print(
                "Aucun nouveau magnet sur cette page. "
                "Tous les magnets sont déjà présents "
                "dans les journaux. Arrêt du scan."
            )

            break

    return list(
        dict.fromkeys(magnets)
    )


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
    print(
        "Répertoire de travail :",
        Path.cwd()
    )

    print(
        "Fichier des pages à réessayer :",
        FICHIER_PAGES_A_REESSAYER.resolve()
    )

    deja_envoyes = lire_log()

    liens = lire_liens()

    magnets_pages_a_reessayer = (
        scanner_pages_a_reessayer(
            deja_envoyes
        )
    )

    magnets_extraits = (
        scanner_urls_extractions(
            deja_envoyes
        )
    )

    liens.extend(
        magnets_pages_a_reessayer
    )

    liens.extend(
        magnets_extraits
    )

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
            print(
                f"[IGNORÉ] {error}"
            )
            continue

        if identifiant in deja_envoyes:
            print(
                "[DÉJÀ ENVOYÉ] "
                f"{reduire_lien_pour_terminal(lien)}"
            )
            continue

        if identifiant in identifiants_vus:
            print(
                "[DOUBLON] "
                f"{reduire_lien_pour_terminal(lien)}"
            )
            continue

        identifiants_vus.add(
            identifiant
        )

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

    for index, (
        lien,
        identifiant,
    ) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        lien_terminal = (
            reduire_lien_pour_terminal(lien)
        )

        try:
            status_code = envoyer_lien(lien)

            if 200 <= status_code < 400:
                print(
                    f"[OK] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - "
                    f"{lien_terminal}"
                )

                identifiants_envoyes.add(
                    identifiant
                )

            else:
                print(
                    f"[ERREUR] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - "
                    f"{lien_terminal}"
                )

                liens_echoues.append(
                    lien
                )

        except requests.RequestException as error:
            print(
                f"[ERREUR] {index}/"
                f"{len(nouveaux_liens)} - "
                f"{lien_terminal} - "
                f"{error}"
            )

            liens_echoues.append(
                lien
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
        "Les journaux dans log-url/ "
        "ont été mis à jour."
    )


if __name__ == "__main__":
    main()
