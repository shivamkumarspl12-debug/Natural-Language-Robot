import os
from pathlib import Path
from threading import Lock

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS_PATH = (
    PROJECT_ROOT / "config" / "firebase-service-account.json"
)


class FirebaseConfigurationError(RuntimeError):
    pass


_firestore_client = None
_firebase_app = None
_initialization_lock = Lock()


def _initialize_firebase_app():
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    configured_path = os.environ.get(
        "FIREBASE_CREDENTIALS_PATH",
        str(DEFAULT_CREDENTIALS_PATH),
    )
    credentials_path = Path(configured_path).expanduser()
    if not credentials_path.is_absolute():
        credentials_path = PROJECT_ROOT / credentials_path

    if not credentials_path.is_file():
        raise FirebaseConfigurationError(
            "Firebase service-account credentials were not found. Set "
            "FIREBASE_CREDENTIALS_PATH to the service-account JSON file "
            "or place it at config/firebase-service-account.json."
        )

    try:
        try:
            return firebase_admin.get_app()
        except ValueError:
            firebase_credential = credentials.Certificate(
                str(credentials_path)
            )
            return firebase_admin.initialize_app(firebase_credential)
    except (OSError, ValueError) as error:
        raise FirebaseConfigurationError(
            "Firebase credentials could not be loaded. Verify that "
            "FIREBASE_CREDENTIALS_PATH points to a valid service-account "
            "JSON file."
        ) from error


def get_firebase_app():
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    with _initialization_lock:
        if _firebase_app is None:
            _firebase_app = _initialize_firebase_app()
        return _firebase_app


def get_firestore_client():
    global _firebase_app, _firestore_client

    if _firestore_client is not None:
        return _firestore_client

    with _initialization_lock:
        if _firestore_client is None:
            if _firebase_app is None:
                _firebase_app = _initialize_firebase_app()
            _firestore_client = firestore.client(app=_firebase_app)
        return _firestore_client
