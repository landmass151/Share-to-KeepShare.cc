import base64
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests


FEED_URL = os.getenv(
    "FEED_URL",
    "https://tsundere.to/api/v1/feed.xml"
)

OUTPUT_DIR = Path("torrent")
TARGET_PROVIDER = "nyaa.si"

REQUEST_TIMEOUT = 120
USER_AGENT = "github-torrent-feed-downloader/1.0"


def local_name(element):
    """
    Retourne le nom XML sans namespace.

    Exemple :
    {http://www.w3.org/2005/Atom}title -> title
    """
    return element.tag.rsplit("}", 1)[-1]


def child_text(element, wanted_name):
    """
    Recherche récursivement le premier élément XML
    correspondant au nom demandé.
    """
    for child in element.iter():
        if local_name(child) == wanted_name:
            return (child.text or "").strip()

    return ""


def encode_url(url):
    """
    Encode l'URL dans un format compatible avec un nom de fichier.

    L'URL reste récupérable et ne contient pas de caractères
    problématiques comme /, ?, :, &, etc.
    """
    return (
        base64.urlsafe_b64encode(url.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def decode_url(encoded_url):
    """
    Décode une URL précédemment encodée.

    Cette fonction n'est pas indispensable au fonctionnement,
    mais elle permet de récupérer l'URL depuis un nom de fichier.
    """
    padding = "=" * (-len(encoded_url) % 4)

    return base64.urlsafe_b64decode(
        encoded_url + padding
    ).decode("utf-8")


def torrent_filename(download_url):
    """
    Génère le nom du fichier torrent à partir de son URL.

    Exemple :
    torrent/aHR0cHM6Ly9leGFtcGxlLmNvbQ.torrent
    """
    encoded_url = encode_url(download_url)

    return OUTPUT_DIR / f"{encoded_url}.torrent"


def is_valid_http_url(value):
    """
    Vérifie que l'URL utilise HTTP ou HTTPS.
    """
    parsed = urlparse(value)

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def fetch_feed():
    """
    Télécharge et analyse le flux XML.
    """
    response = requests.get(
        FEED_URL,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT
        }
    )

    response.raise_for_status()

    try:
        return ET.fromstring(response.content)
    except ET.ParseError as error:
        raise RuntimeError(
            f"Flux XML invalide : {error}"
        ) from error


def get_items(root):
    """
    Retourne tous les éléments <item> du flux.
    """
    return [
        element
        for element in root.iter()
        if local_name(element) == "item"
    ]


def download_torrent(download_url, destination):
    """
    Télécharge un torrent dans un fichier temporaire,
    puis le renomme une fois le téléchargement terminé.
    """
    temporary_file = destination.with_suffix(".part")

    print(f"Téléchargement : {download_url}")

    try:
        with requests.get(
            download_url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT
            }
        ) as response:
            response.raise_for_status()

            with temporary_file.open("wb") as output:
                for chunk in response.iter_content(
                    chunk_size=128 * 1024
                ):
                    if chunk:
                        output.write(chunk)

        temporary_file.replace(destination)

        print(f"Fichier enregistré : {destination}")

    except Exception:
        if temporary_file.exists():
            temporary_file.unlink()

        raise


def process_feed():
    """
    Parcourt le flux, télécharge les nouveaux torrents
    et s'arrête au premier torrent déjà existant.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Lecture du flux : {FEED_URL}")

    root = fetch_feed()
    items = get_items(root)

    print(f"{len(items)} élément(s) trouvé(s) dans le flux.")

    if not items:
        print("Aucun élément à traiter.")
        return

    downloaded_count = 0
    ignored_count = 0

    for item in items:
        provider = child_text(item, "provider")

        if provider != TARGET_PROVIDER:
            ignored_count += 1
            continue

        torrent_url = (
            child_text(item, "torrentUrl")
            or child_text(item, "torrentURL")
            or child_text(item, "torrent_url")
            or child_text(item, "url")
        )

        if not torrent_url:
            print(
                "Élément nyaa.si ignoré : "
                "aucune URL torrent trouvée."
            )
            continue

        if not is_valid_http_url(torrent_url):
            print(
                f"URL invalide ignorée : {torrent_url}"
            )
            continue

        destination = torrent_filename(torrent_url)

        print(f"Fichier attendu : {destination.name}")

        # Détection d'un torrent déjà téléchargé.
        # Comme le nom est calculé à partir de l'URL,
        # la comparaison est exacte.
        if destination.exists():
            print(
                f"Torrent déjà présent : {destination.name}"
            )
            print(
                "Arrêt : les éléments suivants sont considérés "
                "comme déjà traités."
            )
            break

        try:
            download_torrent(
                torrent_url,
                destination
            )

            downloaded_count += 1

            # Pause entre deux téléchargements.
            time.sleep(1)

        except requests.RequestException as error:
            print(
                f"Erreur HTTP pendant le téléchargement : {error}"
            )

        except OSError as error:
            print(
                f"Erreur d'écriture du fichier : {error}"
            )

        except Exception as error:
            print(
                f"Erreur inattendue : {error}"
            )

    print()
    print("Traitement terminé.")
    print(f"Nouveaux torrents téléchargés : {downloaded_count}")
    print(f"Éléments ignorés : {ignored_count}")


def main():
    try:
        process_feed()

    except requests.RequestException as error:
        print(
            f"Impossible de récupérer le flux : {error}"
        )
        sys.exit(1)

    except RuntimeError as error:
        print(error)
        sys.exit(1)

    except Exception as error:
        print(f"Erreur fatale : {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
