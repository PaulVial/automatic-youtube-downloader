"""Autorise l'app à écrire dans ton Google Drive et génère token.json (à faire une seule fois).

Usage :
    pip install google-auth-oauthlib
    python scripts/get_drive_token.py client_secret.json

Un navigateur s'ouvre : connecte-toi avec le compte Google dont tu veux utiliser le Drive.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    client_secret = Path(sys.argv[1] if len(sys.argv) > 1 else "client_secret.json")
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "token.json")
    if not client_secret.exists():
        sys.exit(f"{client_secret} introuvable. Télécharge le client OAuth (type « Desktop app ») "
                 "depuis la console Google Cloud. Voir le README, étape 3.")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    # prompt=consent + access_type=offline : garantit la présence d'un refresh token.
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not credentials.refresh_token:
        sys.exit("Aucun refresh token reçu. Révoque l'accès sur myaccount.google.com/permissions "
                 "puis relance le script.")

    output.write_text(credentials.to_json(), encoding="utf-8")
    print(f"OK : {output} créé pour le client {json.loads(credentials.to_json())['client_id'][:20]}…")
    print("Ce fichier donne accès à ton Drive : ne le partage pas et ne le commite pas.")


if __name__ == "__main__":
    main()
