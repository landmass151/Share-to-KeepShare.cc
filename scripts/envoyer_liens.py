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

# Limite de sécurité utilisée uniquement avec le caractère *.
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


# Exemple reconnu :
#   <1-7>
#   <2-10>
#   <30-60>
PATTERN_PLAGE_PAGES = re.compile(
    r"<(\d+)-(\d+)>"
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

    Les caractères < et > sont conservés afin de permettre
    la notation des plages de pages, par exemple <1-7>.
    """
    return ligne.strip().strip(
        " \t\r\n.,;:)]}\"'"
    )


def lire_urls_extractions():
    """
    Lit urls-extractions.txt.

    Une ligne qui contient une URL HTTP(S)
    démarre une nouvelle URL.

    Une ligne qui ne contient pas d'URL HTTP(S)
    est ajoutée à l'URL précédente.

    Formats acceptés :

        https://exemple.com/page=1

        https://exemple.com/page=*

        https://exemple.com/page=<1-7>

    Exemple :

        https://exemple.com/recherche?q=test
        &p=*

    devient :

        https://exemple.com/recherche?q=test&p=*

    Exemple de plage :

        https://exemple.com/recherche?q=test&p=<1-7>

    génère les pages 1 à 7 inclusivement.
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

        # Les caractères < et > sont volontairement autorisés.
        # Cela permet de conserver une plage comme <1-7>.
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

            # Les URLs précédentes présentes sur la même ligne
            # sont terminées.
            for url in urls_absolues[:-1]:
                urls.append(
                    nettoyer_ligne(url)
                )

            # La dernière URL peut recevoir
            # une ligne complémentaire.
            url_actuelle = urls_absolues[-1]

        elif url_actuelle:
            # Ajout d'un paramètre ou d'une continuation
            # à l'URL précédente.
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

        # Méthode de secours.
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
    FICHIER_LOG.touch(
        exist_ok=True
    )

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


def supprimer_liens_envoyes(identifiants_envoyes):
    """
    Supprime de liens-à-envoyer.txt les URLs et magnets
    qui ont été envoyés avec succès.
    """
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
            f"{texte_original.count(chr(10))} ligne(s) "
            "du fichier manuel traitée(s)."
        )


def construire_url_page(url_modele, numero_page):
    """
    Remplace une plage de pages ou un astérisque.

    Exemple :

        p=<1-7> avec numero_page=3
        devient p=3

        p=* avec numero_page=3
        devient p=3
    """
    if numero_page is None:
        return url_modele

    url_page = PATTERN_PLAGE_PAGES.sub(
        str(numero_page),
        url_modele,
        count=1,
    )

    url_page = url_page.replace(
        "*",
        str(numero_page),
    )

    return url_page


def scanner_urls_extractions(deja_envoyes):
    """
    Scanne les URLs présentes dans urls-extractions.txt.

    Formats acceptés :

        URL fixe :
        https://exemple.com/page=1

        Pagination avec astérisque :
        https://exemple.com/page=*

        Plage de pages :
        https://exemple.com/page=<1-7>

    Une plage est inclusive :

        <1-7> analyse les pages 1, 2, 3, 4, 5, 6 et 7.

    Avec *, le script commence à la page 1 et continue
    jusqu'à l'arrêt ou jusqu'à MAX_PAGES_SECURITE.

    Le scan s'arrête dès qu'un magnet déjà présent
    dans log-url.txt est trouvé.
    """
    magnets = []

    for base_url in lire_urls_extractions():
        plage = PATTERN_PLAGE_PAGES.search(base_url)

        if plage:
            debut = int(plage.group(1))
            fin = int(plage.group(2))

            if debut > fin:
                print(
                    f"[ERREUR] Plage invalide : {plage.group(0)} "
                    f"dans {base_url}"
                )
                continue

            numeros_pages = range(
                debut,
                fin + 1,
            )

        elif "*" in base_url:
            numeros_pages = range(
                1,
                MAX_PAGES_SECURITE + 1,
            )

        else:
            numeros_pages = [None]

        for numero_page in numeros_pages:
            url_page = construire_url_page(
                base_url,
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
                    "Aucun magnet trouvé sur cette page. "
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
                    "Un magnet déjà présent dans "
                    "log-url.txt a été trouvé. "
                    "Arrêt du scan."
                )
                break

    return list(dict.fromkeys(magnets))


def envoyer_lien(lien):
    """
    Envoie le lien vers l'URL de base.
    """
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

    # Liens ajoutés manuellement.
    liens = lire_liens()

    # Magnets extraits des pages HTML.
    magnets_extraits = scanner_urls_extractions(
        deja_envoyes
    )

    liens.extend(magnets_extraits)

    # Suppression des doublons bruts.
    liens = list(dict.fromkeys(liens))

    if not liens:
        print(
            "Aucun lien ou magnet trouvé."
        )

        # Nettoyage des anciens liens déjà envoyés
        # encore présents dans le fichier manuel.
        supprimer_liens_envoyes(
            deja_envoyes
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
                f"[DÉJÀ ENVOYÉ] {lien}"
            )
            continue

        if identifiant in identifiants_vus:
            print(
                f"[DOUBLON] {lien}"
            )
            continue

        identifiants_vus.add(
            identifiant
        )

        nouveaux_liens.append(
            (lien, identifiant)
        )

    if not nouveaux_liens:
        # Nettoyage des anciens liens déjà envoyés
        # encore présents dans le fichier manuel.
        supprimer_liens_envoyes(
            deja_envoyes
        )

        print(
            "Aucun nouveau lien à envoyer."
        )
        return

    print(
        f"{len(nouveaux_liens)} nouveau(x) lien(s) "
        "à envoyer."
    )

    identifiants_envoyes = set(
        deja_envoyes
    )

    for index, (lien, identifiant) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        try:
            status_code = envoyer_lien(
                lien
            )

            if 200 <= status_code < 400:
                print(
                    f"[OK] {index}/{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )

                identifiants_envoyes.add(
                    identifiant
                )

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

    ecrire_log(
        identifiants_envoyes
    )

    # Suppression uniquement des liens envoyés avec succès.
    supprimer_liens_envoyes(
        identifiants_envoyes
    )

    print()
    print(
        "Le fichier log-url.txt a été mis à jour."
    )
    print(
        "Les liens envoyés avec succès "
        "ont été supprimés."
    )


if __name__ == "__main__":
    main()
