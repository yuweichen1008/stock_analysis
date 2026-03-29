"""
Authentication helpers for the Streamlit trading dashboard.

Uses streamlit-authenticator with a bcrypt-hashed password stored in
dashboard/config.yaml (kept out of version control).

Quick setup:
    python3 -c "
    import bcrypt, getpass
    pw = getpass.getpass('Password: ')
    print(bcrypt.hashpw(pw.encode(), bcrypt.gensalt(12)).decode())
    "
Then paste the hash into dashboard/config.yaml under credentials.
"""

import os
import yaml
import streamlit as st
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _default_config() -> dict:
    """
    Return a default config when config.yaml doesn't exist yet.
    This lets the app boot; the user sees a prompt to create the file.
    """
    return {
        "credentials": {
            "usernames": {
                "admin": {
                    "email":    "admin@localhost",
                    "name":     "Admin",
                    # bcrypt hash of "changeme" — replace this in config.yaml
                    "password": "$2b$12$KIXTSmCo7GcD0dWpTMfm4.pjDHBzmHoFM7.x5BTYgvB9Tb7PvXxiO",
                }
            }
        },
        "cookie": {
            "expiry_days": 7,
            "key":         "trading_dashboard_secret_key_change_me",
            "name":        "trading_dashboard_token",
        },
    }


def load_authenticator():
    """Load config.yaml and return a configured Authenticate instance."""
    try:
        import streamlit_authenticator as stauth

        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                config = yaml.safe_load(f)
        else:
            config = _default_config()
            st.warning(
                "⚠️ `dashboard/config.yaml` not found — using default credentials "
                "(`admin` / `changeme`). "
                "Create the file and set a strong password before exposing this app."
            )

        return stauth.Authenticate(
            config["credentials"],
            config["cookie"]["name"],
            config["cookie"]["key"],
            config["cookie"]["expiry_days"],
        )
    except ImportError:
        st.error("streamlit-authenticator is not installed. Run: pip install streamlit-authenticator")
        st.stop()


def require_login(authenticator) -> tuple:
    """
    Render the login form if the user is not authenticated.
    Returns (name, True) on success; calls st.stop() otherwise.
    """
    name, auth_status, username = authenticator.login("Login", "main")

    if auth_status is False:
        st.error("Incorrect username or password.")
        st.stop()
    elif auth_status is None:
        st.info("Please enter your credentials to access the trading dashboard.")
        st.stop()

    return name, True
