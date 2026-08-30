import base64
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from datetime import datetime

import requests


FEED_URL = os.getenv(
    "FEED_URL",
    "https://tsundere.to/api/v1/feed.xml"
)

OUTPUT_DIR = Path("torrent")
TARGET_PROVIDER = "nyaa.si"

# Le script est appelé à 22:00 et 23:00 UTC.
# Cette vérification garantit qu'une seule des deux exécutions
# correspond à 00:00 en Europe/Paris.
PARIS_TZ = ZoneInfo("Europe/Paris")


def check_paris_midnight():
    now = datetime.now(PARIS_TZ)

    if now.hour != 0:
        print(
            f"Exécution ignorée : il est {now:%H:%M} "
            f"à Paris, pas minuit."
        )
        sys.exit(0)


def local_name(element):
    """
    Retourne le nom XML sans namespace.
    Exemple : {namespace}torrentUrl -> torrentUrl
    """
    return element.tag.rsplit("}", 1)[-1]


def child_text(element, wanted_name):
    """
    Cherche récursivement un élément XML par son nom local.
    """
    for child in element.iter():
        if local_name(child) == wanted_name:
            text = child.text or ""
            return text.strip()

    return ""


def encode_url(url):
    """
    Transforme l'URL en texte compatible avec un nom de fichier.
    L'URL reste réversible et est stockée dans le nom du fichier.
    """
    return (
        base64.urlsafe_b64encode(url.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def decode_url(encoded):
    """
    Décode une URL stockée dans un nom de fichier.
    """
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(
        encoded + padding
    ).decode("utf-8")


def torrent_filename(download_url):
    """
    Le nom contient l'URL de téléchargement encodée.
    Exemple :
    torrent/aHR0cHM6Ly9... .torrent
    """
    return OUTPUT_DIR / f"{encode_url(download_url)}.torrent"


def is_valid_http_url(value):
    parsed = urlparse(value)

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def fetch_feed():
    response = requests.get(
        FEED_URL,
        timeout=60,
        headers={
            "User-Agent": "github-torrent-feed-downloader/1.0"
        },
    )
    response.raise_for_status()

    return ET.fromstring(response.content)


def get_items(root):
    return [
        element
        for element in root.iter()
        if local_name(element) == "item"
    ]


def download_torrent(url, destination):
    print(f"Téléchargement : {url}")

    temporary_file = destination.with_suffix(".part")

    with requests.get(
        url,
        stream=True,
        timeout=120,
        headers={
            "User-Agent": "github-torrent-feed-downloader/1.0"
        },
    ) as response:
        response.raise_for_status()

        with temporary_file.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    output.write(chunk)

    temporary_file.replace(destination)

    print(f"Enregistré : {destination}")


def main():
    check_paris_midnight()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Lecture du flux : {FEED_URL}")

    root = fetch_feed()
    items = get_items(root)

    if not items:
        print("Aucun élément trouvé dans le flux.")
        return

    downloaded = 0

    for item in items:
        provider = child_text(item, "provider")

        if provider != TARGET_PROVIDER:
            continue

        torrent_url = (
            child_text(item, "torrentUrl")
            or child_text(item, "torrentURL")
            or child_text(item, "url")
        )

        if not torrent_url:
            print("Élément ignoré : aucune URL torrent.")
            continue

        if not is_valid_http_url(torrent_url):
            print(f"URL invalide ignorée : {torrent_url}")
            continue

        destination = torrent_filename(torrent_url)

        # Arrêt dès qu'un torrent déjà connu est rencontré.
        if destination.exists():
            print(
                "Torrent déjà présent rencontré : "
                f"{destination.name}"
            )
            print("Arrêt du téléchargement.")
            break

        try:
            download_torrent(torrent_url, destination)
            downloaded += 1

            # Petite pause pour éviter une succession trop rapide
            # de requêtes vers le serveur distant.
            time.sleep(1)

        except requests.RequestException as error:
            print(
                f"Échec du téléchargement de {torrent_url}: "
                f"{error}"
            )

    print(f"{downloaded} nouveau(x) torrent(s) téléchargé(s).")


if __name__ == "__main__":
    main()

