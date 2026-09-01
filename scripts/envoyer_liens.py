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

def nettoyer_lien(lien: str) -> str:
    """Supprime les espaces et la ponctuation autour d'un lien."""
    return lien.strip().strip(" \t\r\n.,;:)]}\"'")


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


# ---------------------------------------------------------------------
# Lecture des fichiers d'entrée
# ---------------------------------------------------------------------

def lire_liens_manuels() -> list[str]:
    """Lit les liens présents dans le fichier manuel."""
    if not FICHIER_LIENS.exists():
        return []

    contenu = FICHIER_LIENS.read_text(encoding="utf-8")
    return extraire_liens(contenu)


def lire_sources() -> list[str]:
    """
    Lit les URL du fichier bases-à-extraire.txt.

    Une URL peut être écrite sur plusieurs lignes.
    Les lignes vides et les commentaires commençant par # sont ignorés.
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

        if urls:
            if source_en_cours:
                sources.append(nettoyer_lien(source_en_cours))

            sources.extend(
                nettoyer_lien(url)
                for url in urls[:-1]
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

    if partie.fragment:
        chemin += "#" + partie.fragment

    return base, chemin


# ---------------------------------------------------------------------
# Gestion des journaux
# ---------------------------------------------------------------------

def nom_fichier_log(identifiant: tuple[str, str]) -> str:
    """Détermine le nom du fichier journal d'un lien."""
    base, chemin = identifiant

    if base == MAGNET_PREFIX:
        prefixe = "magnet"
    else:
        domaine = urlsplit(base).netloc
        prefixe = re.sub(r"[^a-z0-9]+", "", domaine.lower())
        prefixe = prefixe or "inconnu"

    premier_caractere = next(
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

    for fichier in DOSSIER_LOG.glob("*.txt"):
        for ligne in fichier.read_text(
            encoding="utf-8"
        ).splitlines():

            ligne = ligne.strip()

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


# ---------------------------------------------------------------------
# Téléchargement et extraction
# ---------------------------------------------------------------------

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

                if contenu.lower().startswith(MAGNET_PREFIX):
                    magnets.append(contenu)

    return supprimer_doublons(magnets)


# ---------------------------------------------------------------------
# Gestion des plages de pages
# ---------------------------------------------------------------------

def numéros_de_pages(modèle: str) -> list[int | None]:
    """Retourne les numéros de pages à parcourir."""
    plage = RE_PLAGE_PAGES.search(modèle)

    if not plage and "*" not in modèle:
        return [None]

    if plage:
        début, fin = plage.groups()

        if début == "*" and fin == "*":
            raise ValueError(
                f"Plage invalide : {plage.group(0)}"
            )

        numéro_début = 1 if début == "*" else int(début)
        numéro_fin = MAX_PAGES if fin == "*" else int(fin)

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

    def remplacement(match: re.Match) -> str:
        lien_original = match.group(0)
        lien = nettoyer_lien(lien_original)

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

    if nouveau_contenu and not nouveau_contenu.endswith("\n"):
        nouveau_contenu += "\n"

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

    identifiants_connus = lire_journaux()

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
                    f"[OK] {numéro}/{len(nouveaux_liens)} "
                    f"HTTP {code} - {lien}"
                )
                envoyés.add(identifiant)
            else:
                print(
                    f"[ERREUR] {numéro}/"
                    f"{len(nouveaux_liens)} "
                    f"HTTP {code} - {lien}"
                )
                échoués.append(lien)

        except requests.RequestException as erreur:
            print(
                f"[ERREUR] {numéro}/"
                f"{len(nouveaux_liens)} "
                f"{lien} - {erreur}"
            )
            échoués.append(lien)

    écrire_journaux(envoyés)
    supprimer_liens_envoyés(envoyés)
    ajouter_liens_échoués(échoués)

    print("Traitement terminé.")
    print("Les journaux ont été mis à jour.")


if __name__ == "__main__":
    main()
