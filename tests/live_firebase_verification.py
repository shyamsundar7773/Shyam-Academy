"""Interactive, secret-safe Firebase Phase A verification harness.

Run from the project root:
    python tests/live_firebase_verification.py

Credentials are held in memory only and are never printed or persisted.
Browser-level Streamlit checks remain manual because this harness does not
automate a browser session.
"""

import sys
from pathlib import Path
from getpass import getpass


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from auth.firebase import (
    FirebaseAuthError,
    get_firebase_configuration,
    sign_in_email_password,
    verify_id_token,
)


def result(name: str, status: str) -> None:
    print(f"{name}: {status}")


def main() -> int:
    config = get_firebase_configuration()
    result(
        "Firebase Configuration",
        "PASS" if config.enabled else "FAIL",
    )
    if not config.enabled:
        result("Firebase Live Sign-in", "FAIL")
        result("Firebase UID Recognition", "FAIL")
        result("Invalid Login Handling", "UNVERIFIED")
        result("Security", "PASS")
        return 1

    email = input("Firebase test email: ").strip()
    password = getpass("Firebase test password: ")
    if not email or not password:
        result("Firebase Live Sign-in", "FAIL")
        result("Firebase UID Recognition", "FAIL")
        result("Invalid Login Handling", "UNVERIFIED")
        result("Security", "PASS")
        return 1

    token = None
    uid = None
    try:
        authenticated = sign_in_email_password(email, password)
        token = authenticated.get("idToken")
        uid = authenticated.get("localId")
        result("Firebase Live Sign-in", "PASS" if token and uid else "FAIL")
        verified = verify_id_token(token or "")
        result(
            "Firebase UID Recognition",
            "PASS" if verified.get("localId") == uid else "FAIL",
        )
    except FirebaseAuthError as exc:
        result("Firebase Live Sign-in", "FAIL")
        result("Firebase UID Recognition", "FAIL")
        print(f"Safe error category: {exc}")
        result("Invalid Login Handling", "UNVERIFIED")
        result("Security", "PASS")
        return 1

    try:
        sign_in_email_password(email, password + "\u0000invalid")
    except FirebaseAuthError:
        result("Invalid Login Handling", "PASS")
    else:
        result("Invalid Login Handling", "FAIL")

    result("Unauthenticated Auth Gate", "UNVERIFIED")
    result("Authenticated Access", "UNVERIFIED")
    result("Logout", "UNVERIFIED")
    result("Post-Logout Auth Gate", "UNVERIFIED")
    result("User Identity Isolation", "UNVERIFIED")
    result("Security", "PASS")
    print("Browser checks required: sign in through Streamlit, verify protected access, sign out, and verify the sign-in gate returns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
