from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

FICHIER_LIENS = Path("liens-à-envoyer.txt")
FICHIER_EXTRACTIONS = Path("bases-à-extraire.txt")
DOSSIER_LOG = Path("log-url")

BASE_URL = "https://keepshare.org/ldf6j5ti/"
MAX_PAGES = 1000
TIMEOUT = 30
NOMBRE_TENTATIVES = 3

MAGNET_PREFIX = "magnet:?xt=urn:btih:"


# ---------------------------------------------------------------------
# Expressions régulières
# ---------------------------------------------------------------------

RE_LIEN = re.compile(
    r"(?:https?://|magnet:\?xt=urn:btih:)[^\s<>'\"]+",
    re.IGNORECASE,
)

RE_PLAGE_PAGES = re.compile(r"<(\d+|\*)-(\d+|\*)>")


# ---------------------------------------------------------------------
# Utilitaires généraux
# ---------------------------------------------------------------------

def extraire_liens(texte):
    """
    Extrait les URL HTTP(S) et les liens magnet d'un texte.
    """
    liens = []


def supprimer_doublons(elements: list[str]) -> list[str]:
    """Supprime les doublons tout en conservant l'ordre."""
    return list(dict.fromkeys(elements))


def extraire_liens(texte: str) -> list[str]:
    """Extrait les URL HTTP(S) et les magnets d'un texte."""
    liens = []

    for correspondance in RE_LIEN.finditer(texte):
        lien = nettoyer_lien(correspondance.group(0))

        if lien:
            liens.append(lien)

    return supprimer_doublons(liens)


def lire_liens():
    """
    Lit les liens ajoutés manuellement dans
    liens-à-envoyer.txt.
    """
    if not FICHIER_LIENS.exists():
        return []

    contenu = FICHIER_LIENS.read_text(encoding="utf-8")
    return extraire_liens(contenu)


def lire_sources() -> list[str]:
    """
    Lit les URL du fichier bases-à-extraire.txt.

def lire_urls_extractions():
    """
    Lit les URL présentes dans bases-à-extraire.txt.

    Les URL peuvent être écrites sur plusieurs lignes.
    Les lignes commençant par # sont ignorées.
    """
    if not FICHIER_EXTRACTIONS.exists():
        return []

    sources = []
    source_en_cours = ""

    for ligne in FICHIER_EXTRACTIONS.read_text(
        encoding="utf-8"
    ).splitlines():

        ligne = ligne.strip()

        if not ligne or ligne.startswith("#"):
            continue

        urls = re.findall(
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
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
        },
    )

    response.raise_for_status()

    return response.text


def extraire_magnets_html(html):
    """
    Extrait les liens magnet présents dans les
    attributs HTML.
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

            source_en_cours = urls[-1]

        elif source_en_cours:
            source_en_cours += ligne

    if source_en_cours:
        sources.append(nettoyer_lien(source_en_cours))

    return supprimer_doublons(sources)


# ---------------------------------------------------------------------
# Identification des liens
# ---------------------------------------------------------------------

def identifier_lien(lien: str) -> tuple[str, str]:
    """
    Retourne un identifiant stable permettant de comparer deux liens.

    URL :
        https://example.com/page?id=5
    devient :
        ("https://example.com", "/page?id=5")

    Magnet :
        magnet:?xt=urn:btih:ABC123&dn=test
    devient :
        ("magnet:?xt=urn:btih:", "/ABC123")
    """
    lien = lien.strip()

    if lien.lower().startswith(MAGNET_PREFIX):
        partie = urlsplit(lien)
        valeurs_xt = parse_qs(partie.query).get("xt", [])

        if not valeurs_xt:
            correspondance = re.search(
                r"xt=urn:btih:([^&\s]+)",
                lien,
                flags=re.IGNORECASE,
            )

            if not correspondance:
                raise ValueError(
                    f"Hash magnet introuvable : {lien}"
                )

            hash_magnet = correspondance.group(1)

        else:
            hash_magnet = re.sub(
                r"^urn:btih:",
                "",
                valeurs_xt[0],
                flags=re.IGNORECASE,
            )

        if not hash_magnet:
            raise ValueError(f"Hash magnet vide : {lien}")

        return MAGNET_PREFIX, "/" + hash_magnet.upper()

    partie = urlsplit(lien)

    if partie.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"Type de lien non supporté : {lien}")

    if not partie.netloc:
        raise ValueError(f"URL invalide : {lien}")

    base = f"{partie.scheme.lower()}://{partie.netloc.lower()}"
    chemin = partie.path or "/"

    if partie.query:
        chemin += "?" + partie.query

    return base, chemin


# ---------------------------------------------------------------------
# Gestion des journaux
# ---------------------------------------------------------------------

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
    Lit tous les journaux présents dans log-url/.

    Aucun ancien fichier log-url.txt n'est utilisé.
    """
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
    """
    Retourne le nom du journal correspondant
    à un identifiant.

    Exemples :

        Magnet avec hash ABC123 :
            magnet-a.txt

        https://google.com/index :
            googlecom-i.txt
    """
    base, chemin = identifiant

    if base == MAGNET_PREFIX:
        prefixe = "magnet"

    else:
        partie = urlsplit(base)

        domaine = partie.netloc.lower()

        # example.com devient examplecom.
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
            caractere.lower()
            for caractere in chemin.lstrip("/")
            if caractere.isalnum()
        ),
        "autre",
    )

    return f"{prefixe}-{premier_caractere}.txt"


def lire_journaux() -> set[tuple[str, str]]:
    """Lit tous les identifiants déjà envoyés."""
    DOSSIER_LOG.mkdir(exist_ok=True)

    identifiants = set()
    base_en_cours = None

def ecrire_log(identifiants):
    """
    Écrit les identifiants dans les journaux.

    Les fichiers sont répartis par domaine ou par
    type de lien, puis par premier caractère du
    chemin ou du hash.
    """
    DOSSIER_LOG.mkdir(
        parents=True,
        exist_ok=True,
    )

            if not ligne:
                continue

            if ligne.startswith("/"):
                if base_en_cours:
                    identifiants.add((base_en_cours, ligne))
            else:
                base_en_cours = ligne

    return identifiants


def écrire_journaux(
    identifiants: set[tuple[str, str]],
) -> None:
    """Réécrit les journaux à partir des identifiants fournis."""
    DOSSIER_LOG.mkdir(exist_ok=True)

    groupes = defaultdict(lambda: defaultdict(list))

    for identifiant in sorted(identifiants):
        base, chemin = identifiant
        fichier = DOSSIER_LOG / nom_fichier_log(identifiant)

        if chemin not in groupes[fichier][base]:
            groupes[fichier][base].append(chemin)

    fichiers_utiles = set(groupes)

    for ancien_fichier in DOSSIER_LOG.glob("*.txt"):
        if ancien_fichier not in fichiers_utiles:
            ancien_fichier.unlink()

    for fichier, bases in groupes.items():
        lignes = []

        for base, chemins in bases.items():
            if lignes:
                lignes.append("")

            lignes.append(base)
            lignes.extend(chemins)

        fichier.write_text(
            "\n".join(lignes) + "\n",
            encoding="utf-8",
        )


def supprimer_liens_envoyes(identifiants_envoyes):
    """
    Supprime du fichier manuel les liens envoyés
    avec succès.
    """
    if not FICHIER_LIENS.exists():
        return

    texte_original = FICHIER_LIENS.read_text(
        encoding="utf-8"
    )

def créer_session() -> requests.Session:
    """Crée une session HTTP réutilisable."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    return session


def télécharger(
    session: requests.Session,
    url: str,
) -> str:
    """Télécharge une page avec plusieurs tentatives."""
    dernière_erreur = None

    for tentative in range(1, NOMBRE_TENTATIVES + 1):
        try:
            réponse = session.get(
                url,
                timeout=TIMEOUT,
            )
            réponse.raise_for_status()
            return réponse.text

        except requests.RequestException as erreur:
            dernière_erreur = erreur
            print(
                f"  Tentative {tentative}/"
                f"{NOMBRE_TENTATIVES} échouée : {erreur}"
            )

    raise dernière_erreur


def extraire_magnets(html: str) -> list[str]:
    """Extrait les magnets présents dans les attributs HTML."""
    soup = BeautifulSoup(html, "html.parser")
    magnets = []

    for élément in soup.find_all(True):
        for valeur in élément.attrs.values():
            valeurs = valeur if isinstance(valeur, list) else [valeur]

            for contenu in valeurs:
                if not isinstance(contenu, str):
                    continue

                contenu = contenu.strip()

def ajouter_liens_echoues(liens_echoues):
    """
    Ajoute les liens ayant échoué dans
    liens-à-envoyer.txt pour un nouvel essai.
    """
    if not liens_echoues:
        return

    return supprimer_doublons(magnets)


# ---------------------------------------------------------------------
# Gestion des plages de pages
# ---------------------------------------------------------------------

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

        contenu_final = (
            contenu_existant
            + lignes_nouvelles
        )

        if début == "*" and fin == "*":
            raise ValueError(
                f"Plage invalide : {plage.group(0)}"
            )

        print(
            f"{len(liens_a_ajouter)} lien(s) échoué(s) "
            "ajouté(s) à liens-à-envoyer.txt "
            "pour réessai."
        )

        if numéro_début > numéro_fin:
            raise ValueError(
                f"Plage invalide : {plage.group(0)}"
            )

        return list(range(numéro_début, numéro_fin + 1))

    return list(range(1, MAX_PAGES + 1))


def construire_url(
    modèle: str,
    numéro: int | None,
) -> str:
    """Remplace la plage ou l'astérisque par le numéro de page."""
    if numéro is None:
        return modèle

    résultat = RE_PLAGE_PAGES.sub(
        str(numéro),
        modèle,
        count=1,
    )

    return résultat.replace("*", str(numéro))


# ---------------------------------------------------------------------
# Scan des sources
# ---------------------------------------------------------------------

def scanner_sources(
    session: requests.Session,
    identifiants_connus: set[tuple[str, str]],
) -> list[str]:
    """Scanne toutes les sources et retourne les nouveaux magnets."""
    nouveaux_magnets = []

    for modèle in lire_sources():
        try:
            pages = numéros_de_pages(modèle)
        except ValueError as erreur:
            print(f"[ERREUR] {erreur}")
            continue

        for numéro in pages:
            url = construire_url(modèle, numéro)
            print(f"Analyse : {url}")

            try:
                html = télécharger(session, url)
            except requests.RequestException:
                print("  Arrêt du scan de cette source.")
                break

            magnets = extraire_magnets(html)

            if not magnets:
                print("  Aucun magnet trouvé. Arrêt du scan.")
                break

            ancien_trouvé = False

            for magnet in magnets:
                try:
                    identifiant = identifier_lien(magnet)
                except ValueError:
                    continue

                if identifiant in identifiants_connus:
                    ancien_trouvé = True
                else:
                    nouveaux_magnets.append(magnet)

            if ancien_trouvé:
                print(
                    "  Magnet déjà journalisé. "
                    "Arrêt du scan."
                )
                break

    return supprimer_doublons(nouveaux_magnets)


# ---------------------------------------------------------------------
# Modification du fichier manuel
# ---------------------------------------------------------------------

def supprimer_liens_envoyés(
    identifiants_envoyés: set[tuple[str, str]],
) -> None:
    """Supprime du fichier manuel les liens envoyés avec succès."""
    if not FICHIER_LIENS.exists():
        return

    texte = FICHIER_LIENS.read_text(encoding="utf-8")

def scanner_urls_extractions(deja_envoyes):
    """
    Scanne les pages définies dans
    bases-à-extraire.txt.
    """
    magnets = []

        try:
            identifiant = identifier_lien(lien)
        except ValueError:
            return lien_original

        return "" if identifiant in identifiants_envoyés else lien_original

    nouveau_texte = RE_LIEN.sub(remplacement, texte)

    if nouveau_texte != texte:
        FICHIER_LIENS.write_text(
            nouveau_texte,
            encoding="utf-8",
        )

            try:
                html = telecharger_page(
                    url_page
                )

                trouves = extraire_magnets_html(
                    html
                )

def ajouter_liens_échoués(liens: list[str]) -> None:
    """Ajoute les liens échoués au fichier manuel."""
    if not liens:
        return

    existants = set(lire_liens_manuels())
    à_ajouter = [
        lien for lien in liens
        if lien not in existants
    ]

    if not à_ajouter:
        return

    ancien_contenu = ""

    if FICHIER_LIENS.exists():
        ancien_contenu = FICHIER_LIENS.read_text(
            encoding="utf-8"
        )

    nouveau_contenu = ancien_contenu

            if magnet_deja_connu:
                print(
                    "Un magnet déjà présent dans les "
                    "journaux a été trouvé. "
                    "Arrêt du scan."
                )
                break

    nouveau_contenu += "\n".join(à_ajouter) + "\n"

    FICHIER_LIENS.write_text(
        nouveau_contenu,
        encoding="utf-8",
    )

    print(
        f"{len(à_ajouter)} lien(s) conservé(s) "
        "pour une nouvelle tentative."
    )


# ---------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------

def envoyer_lien(
    session: requests.Session,
    lien: str,
) -> int:
    """Envoie un lien au service distant."""
    destination = BASE_URL + quote(lien, safe="")

    réponse = session.get(
        destination,
        timeout=TIMEOUT,
        headers={
            "Referrer-Policy": "no-referrer",
        },
        allow_redirects=True,
    )

    return réponse.status_code


# ---------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------

def main() -> None:
    session = créer_session()

    magnets_extraits = scanner_urls_extractions(
        deja_envoyes
    )

    liens.extend(magnets_extraits)

    liens = lire_liens_manuels()
    liens += scanner_sources(
        session,
        identifiants_connus,
    )

    liens = supprimer_doublons(liens)

    nouveaux_liens = []
    identifiants_vus = set()

    for lien in liens:
        try:
            identifiant = identifier_lien(lien)
        except ValueError as erreur:
            print(f"[IGNORÉ] {erreur}")
            continue

        if identifiant in identifiants_connus:
            print(f"[DÉJÀ ENVOYÉ] {lien}")
            continue

        if identifiant in identifiants_vus:
            print(f"[DOUBLON] {lien}")
            continue

        identifiants_vus.add(identifiant)
        nouveaux_liens.append((lien, identifiant))

    if not nouveaux_liens:
        print("Aucun nouveau lien à envoyer.")
        return

    envoyés = set(identifiants_connus)
    échoués = []

    print(
        f"{len(nouveaux_liens)} nouveau(x) lien(s) "
        "à envoyer."
    )

    for numéro, (lien, identifiant) in enumerate(
        nouveaux_liens,
        start=1,
    ):
        try:
            code = envoyer_lien(session, lien)

            if 200 <= code < 400:
                print(
                    f"[OK] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )
                envoyés.add(identifiant)
            else:
                print(
                    f"[ERREUR] {index}/"
                    f"{len(nouveaux_liens)} - "
                    f"HTTP {status_code} - {lien}"
                )
                échoués.append(lien)

                liens_echoues.append(
                    lien
                )

        except requests.RequestException as error:
            print(
                f"[ERREUR] {index}/"
                f"{len(nouveaux_liens)} - "
                f"{lien} - {error}"
            )
            échoués.append(lien)

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

    print()
    print(
        "Les journaux dans log-url/ "
        "ont été mis à jour."
    )

    print(
        "Les liens envoyés avec succès "
        "ont été supprimés."
    )


if __name__ == "__main__":
    main()
