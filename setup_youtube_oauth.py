import argparse
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import YOUTUBE_TOKEN_URI, YOUTUBE_UPLOAD_SCOPE

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-time local CLI helper to generate your YOUTUBE_REFRESH_TOKEN."
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        help="Google OAuth2 Client ID (or set YOUTUBE_CLIENT_ID in environment/.env).",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        help="Google OAuth2 Client Secret (or set YOUTUBE_CLIENT_SECRET in environment/.env).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local redirect server port (default: 8080).",
    )
    args = parser.parse_args()

    client_id = args.client_id or input("Enter YOUTUBE_CLIENT_ID: ").strip()
    client_secret = args.client_secret or input("Enter YOUTUBE_CLIENT_SECRET: ").strip()

    if not client_id or not client_secret:
        raise SystemExit("Both YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are required.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": YOUTUBE_TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=YOUTUBE_UPLOAD_SCOPE,
    )
    credentials = flow.run_local_server(
        port=args.port,
        access_type="offline",
        prompt="consent",
    )

    print("\n" + "=" * 72)
    print("OAuth2 Authentication Successful!")
    print("=" * 72)
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    print("=" * 72)
    print("Copy the values above into your GitHub Actions Repository Secrets.")


if __name__ == "__main__":
    main()
