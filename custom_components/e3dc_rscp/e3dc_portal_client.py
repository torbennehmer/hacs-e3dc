"""E3DC Portal REST client for the my.e3dc.com web portal."""

from __future__ import annotations

from functools import wraps
import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

_LOGGER = logging.getLogger(__name__)

TOKEN_LIFETIME_SECONDS = 600

_KC_CONTEXT_RE = re.compile(r"const\s+kcContext\s*=\s*(\{.*?\})\s*;", re.DOTALL)
_LOGIN_ACTION_RE = re.compile(r'"loginAction"\s*:\s*"([^"]+)"')
_SAML_RESPONSE_KC_RE = re.compile(r'"SAMLResponse"\s*:\s*"([^"]+)"')
_SAML_POST_URL_KC_RE = re.compile(
    r'"samlPost"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', re.DOTALL
)
_SAML_FORM_ACTION_RE = re.compile(
    r'<form[^>]*action="([^"]+)"', re.IGNORECASE
)
_SAML_INPUT_RE = re.compile(
    r'<input[^>]*name="SAMLResponse"[^>]*value="([^"]*)"', re.IGNORECASE
)


class PortalAuthenticationError(Exception):
    """Raised when portal authentication fails."""


class PortalRequestError(Exception):
    """Raised when a portal API request fails unexpectedly."""


def e3dc_portal_call(func):
    """Wrap portal calls in exception handling matching e3dc_proxy style."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except PortalAuthenticationError as ex:
            _LOGGER.debug("Portal authentication failed: %s", ex, exc_info=True)
            raise ConfigEntryAuthFailed(
                "Portal authentication failed"
            ) from ex
        except PortalRequestError as ex:
            _LOGGER.debug("Portal request failed: %s", ex, exc_info=True)
            raise HomeAssistantError(
                f"Portal request failed: {ex}"
            ) from ex
        except (HomeAssistantError, ConfigEntryAuthFailed):
            raise
        except Exception as ex:
            _LOGGER.debug("Unexpected portal error: %s", ex, exc_info=True)
            raise HomeAssistantError(
                f"Unexpected portal error: {ex}"
            ) from ex

    return wrapper


def _merge_charging_prio(
    current: dict,
    is_battery: bool | None = None,
    in_sun_mode: bool | None = None,
    in_mix_mode: bool | None = None,
    till_soc: int | None = None,
) -> dict:
    """Merge desired changes into the current charging priorisation state."""
    if till_soc is not None and not (0 <= till_soc <= 100):
        raise ValueError(f"till_soc must be between 0 and 100, got {till_soc}")

    result = {
        "isBattery": current["isBattery"],
        "inSunMode": current["inSunMode"],
        "inMixMode": current["inMixMode"],
        "tillSoc": current["tillSoc"],
    }

    if is_battery is not None:
        result["isBattery"] = is_battery
        # Semantic rule: battery-first forces sunMode off unless explicitly set
        if is_battery and in_sun_mode is None:
            result["inSunMode"] = False

    if in_sun_mode is not None:
        result["inSunMode"] = in_sun_mode
    if in_mix_mode is not None:
        result["inMixMode"] = in_mix_mode
    if till_soc is not None:
        result["tillSoc"] = till_soc

    return result


def _encode_charging_prio_body(payload: dict) -> str:
    """Double-encode payload as JSON-string-in-JSON for the Portal API."""
    return json.dumps(json.dumps(payload))


def _extract_kccontext_login_action(html: str) -> str:
    """Extract the loginAction URL from a Keycloakify login page."""
    m = _KC_CONTEXT_RE.search(html)
    if not m:
        raise PortalAuthenticationError(
            "Could not find kcContext in Keycloak login page."
        )
    m_action = _LOGIN_ACTION_RE.search(m.group(1))
    if not m_action:
        raise PortalAuthenticationError(
            "Could not find loginAction URL in kcContext."
        )
    return m_action.group(1).replace("\\/", "/")


def _extract_saml_response(html: str) -> tuple[str, str]:
    """Extract (assert_url, SAMLResponse) from the authenticate response.

    Tries Keycloakify kcContext first, then falls back to standard HTML form.
    Returns (action_url, saml_response_value).
    """
    # Try kcContext approach (Keycloakify saml-post-form)
    kc_match = _KC_CONTEXT_RE.search(html)
    if kc_match:
        kc_body = kc_match.group(1)
        saml_m = _SAML_RESPONSE_KC_RE.search(kc_body)
        url_m = _SAML_POST_URL_KC_RE.search(kc_body)
        if saml_m:
            url = url_m.group(1).replace("\\/", "/") if url_m else ""
            if not url:
                # Try loginAction as fallback URL
                action_m = _LOGIN_ACTION_RE.search(kc_body)
                if action_m:
                    url = action_m.group(1).replace("\\/", "/")
            return url, saml_m.group(1)

    # Fallback: standard HTML form
    form_m = _SAML_FORM_ACTION_RE.search(html)
    input_m = _SAML_INPUT_RE.search(html)
    if input_m:
        url = form_m.group(1) if form_m else ""
        return url, input_m.group(1)

    raise PortalAuthenticationError(
        "Could not extract SAMLResponse from authenticate response."
    )


class E3DCPortalClient:
    """REST client for the E3DC portal (e3dc.e3dc.com)."""

    BASE_URL = "https://e3dc.e3dc.com"

    def __init__(self, username: str, password: str, serial_number: str) -> None:
        """Initialize the portal client."""
        self.username = username
        self.password = password
        self.serial_number = serial_number
        self.session = requests.Session()
        self.access_token: str | None = None
        self.re_auth_token: str | None = None
        self.token_expires_at: float = 0

    def get_token_state(self) -> dict[str, Any]:
        """Export token state for persistence across HA restarts."""
        return {
            "re_auth_token": self.re_auth_token,
            "token_expires_at": self.token_expires_at,
            "access_token": self.access_token,
        }

    def set_token_state(self, state: dict[str, Any]) -> None:
        """Restore token state from persisted data."""
        self.re_auth_token = state.get("re_auth_token")
        self.access_token = state.get("access_token")
        self.token_expires_at = state.get("token_expires_at", 0)

    @property
    def is_authenticated(self) -> bool:
        """Return True if a valid token is available or can be refreshed."""
        return self.re_auth_token is not None or (
            self.access_token is not None
            and time.time() < self.token_expires_at
        )

    def _re_auth(self) -> None:
        """Obtain a fresh access token using the long-lived reAuthToken."""
        response = self.session.post(
            f"{self.BASE_URL}/auth-saml/re-auth",
            data={"reAuthToken": self.re_auth_token},
        )
        if response.status_code != 200:
            raise PortalAuthenticationError(
                f"re-auth failed with status {response.status_code}: {response.text}"
            )
        data = response.json()
        self.access_token = data["token"]
        self.re_auth_token = data["reAuthToken"]
        self.token_expires_at = time.time() + TOKEN_LIFETIME_SECONDS

    def _ensure_token(self) -> None:
        """Ensure a valid access token is available, refreshing if needed."""
        if time.time() < self.token_expires_at and self.access_token is not None:
            return
        if self.re_auth_token is None:
            self.login()
            return
        self._re_auth()

    def _perform_initial_login(self) -> None:
        """Execute the full SAML/Keycloak login chain.

        Steps:
        1. GET /auth-saml/.../login?app=e3dc -> 302 to Keycloak
        2. GET Keycloak URL -> HTML with kcContext containing loginAction
        3. POST credentials to loginAction -> HTML with SAMLResponse
        4. POST SAMLResponse to assert URL -> 302 with token + reAuthToken
        """
        # Step 1: initiate login, get redirect to Keycloak
        resp1 = self.session.get(
            f"{self.BASE_URL}/auth-saml/service-providers/customer/login",
            params={"app": "e3dc"},
            allow_redirects=False,
        )
        location = resp1.headers.get("Location", "")
        if resp1.status_code != 302 or not location:
            raise PortalAuthenticationError(
                f"Expected 302 redirect from login endpoint, "
                f"got {resp1.status_code}."
            )

        # Step 2: fetch Keycloak login page
        resp2 = self.session.get(location)
        login_action = _extract_kccontext_login_action(resp2.text)

        # Step 3: POST credentials
        resp3 = self.session.post(
            login_action,
            data={
                "username": self.username,
                "password": self.password,
                "credentialId": "",
            },
            allow_redirects=False,
        )
        assert_url, saml_response = _extract_saml_response(resp3.text)

        # Step 4: POST SAMLResponse to assert endpoint
        resp4 = self.session.post(
            assert_url,
            data={"SAMLResponse": saml_response},
            allow_redirects=False,
        )
        redirect_url = resp4.headers.get("Location", "")
        parsed = urlparse(redirect_url)
        qs = parse_qs(parsed.query)
        token_list = qs.get("token", [])
        re_auth_list = qs.get("reAuthToken", [])
        if not token_list or not re_auth_list:
            raise PortalAuthenticationError(
                "Login redirect did not contain token and reAuthToken."
            )
        self.access_token = token_list[0]
        self.re_auth_token = re_auth_list[0]

    @e3dc_portal_call
    def login(self) -> None:
        """Perform initial login via SAML/Keycloak and set tokens."""
        self._perform_initial_login()
        self.token_expires_at = time.time() + TOKEN_LIFETIME_SECONDS

    def _request(
        self,
        method: str,
        path: str,
        expected_status: tuple[int, ...] = (200, 204),
        **kwargs,
    ) -> requests.Response:
        """Send an authenticated request to the portal API."""
        self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        response = self.session.request(
            method, f"{self.BASE_URL}{path}", headers=headers, **kwargs
        )
        if response.status_code not in expected_status:
            raise PortalRequestError(
                f"{method} {path} returned {response.status_code}: {response.text}"
            )
        return response

    @e3dc_portal_call
    def get_charging_priorisation(
        self, wallbox_serial: str | None = None
    ) -> dict:
        """Read the current charging priorisation state."""
        serial = wallbox_serial or self.serial_number
        response = self._request(
            "GET", f"/wallboxes/{serial}/loading-priorisation"
        )
        return response.json()

    @e3dc_portal_call
    def set_charging_priorisation(
        self,
        wallbox_serial: str | None = None,
        *,
        is_battery: bool | None = None,
        in_sun_mode: bool | None = None,
        in_mix_mode: bool | None = None,
        till_soc: int | None = None,
    ) -> bool:
        """Write the charging priorisation state using full-state-write."""
        serial = wallbox_serial or self.serial_number
        current = self.get_charging_priorisation(wallbox_serial=serial)
        target = _merge_charging_prio(
            current,
            is_battery=is_battery,
            in_sun_mode=in_sun_mode,
            in_mix_mode=in_mix_mode,
            till_soc=till_soc,
        )
        body = _encode_charging_prio_body(target)
        self._request(
            "PUT",
            f"/wallboxes/{serial}/loading-priorisation",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        return True
