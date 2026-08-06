"""Minimal OAuth provider for the MCP endpoint (auto-approve, public corpus).

The Shia-Aalim corpus is public data — there's nothing user-specific to gate.
This provider satisfies the MCP OAuth handshake so claude.ai Custom Connectors
can authenticate reliably, with or without dynamic client registration.

Configure via env:
  MCP_OAUTH_CLIENT_ID     — the client ID to register in the connector
                             (default: ``shia-aalim-mcp``)
  MCP_OAUTH_CLIENT_SECRET — optional shared secret; if set, the connector
                             must send it during the token exchange
  MCP_OAUTH_SECRET        — RECOMMENDED: signing key for stateless,
                             restart-proof tokens (see _signing_secret).
                             Set it once (e.g. HF Space secret) and
                             connectors stay authenticated across restarts.

The issuer URL is the public URL of your Space
(e.g. ``https://sqamberali-shia-aalim.hf.space``).

Implementation notes: the token/auth-code/refresh-token records subclass the
SDK's pydantic models (``AccessToken``/``AuthorizationCode``/``RefreshToken``)
rather than ad-hoc dataclasses — the SDK's bearer middleware and session
manager read fields like ``claims``/``subject``/``resource`` from them, so
custom types missing those fields crash the first authenticated request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from typing import Optional

from pydantic import AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

_CLIENT_ID = os.environ.get("MCP_OAUTH_CLIENT_ID", "shia-aalim-mcp")
_CLIENT_SECRET = os.environ.get("MCP_OAUTH_CLIENT_SECRET") or None
_TOKEN_TTL = 3600 * 24 * 30  # 30 days; refresh tokens never expire
_CODE_TTL = 600  # authorization codes: 10 minutes


def _signing_secret() -> str:
    """MCP_OAUTH_SECRET enables restart-proof stateless tokens.

    With it set (e.g. as a Hugging Face Space secret), tokens are
    HMAC-signed, self-contained blobs any fresh server instance can verify —
    so connectors stay authenticated across restarts/rebuilds. Without it,
    tokens live in process memory and die with the process (a startup
    warning is printed by the provider). Rotating the secret revokes all
    outstanding tokens; individual stateless tokens cannot be revoked
    (acceptable trade-off for a public, read-only corpus).
    """
    return os.environ.get("MCP_OAUTH_SECRET", "").strip()


def _sign_blob(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    mac = hmac.new(_signing_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def _verify_blob(token: str) -> Optional[dict]:
    try:
        body, mac = token.rsplit(".", 1)
        expected = hmac.new(_signing_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
        exp = payload.get("exp")
        if exp is not None and exp < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 - any malformed token is simply invalid
        return None


class _OpenClient(OAuthClientInformationFull):
    """Client that accepts any redirect_uri and any scope.

    The corpus is public; the OAuth handshake exists so claude.ai connectors
    have a stable auth flow, not to protect private data. claude.ai's exact
    callback URL and requested scope vary by surface (web / desktop / mobile),
    so a strict allowlist just breaks the connector.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            return redirect_uri
        if self.redirect_uris and len(self.redirect_uris) == 1:
            return self.redirect_uris[0]
        raise ValueError("redirect_uri required")

    def validate_scope(self, requested_scope: str | None) -> list[str] | None:
        if requested_scope is None:
            return None
        return [s for s in requested_scope.split(" ") if s]


class ShiaAalimOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Auto-approving OAuth provider for the public corpus MCP endpoint."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

        self._register_default_client()
        if not _signing_secret():
            print(
                "[shia-aalim] MCP OAuth: MCP_OAUTH_SECRET is not set — tokens "
                "live in memory and every restart forces connectors to "
                "re-authenticate. Set a long random MCP_OAUTH_SECRET (e.g. a "
                "Space secret) for restart-proof sessions.",
                file=sys.stderr,
            )

    def _synth_client(self, client_id: str) -> OAuthClientInformationFull:
        """An open client for ids we no longer remember (post-restart DCR)."""
        return _OpenClient(
            client_id=client_id,
            client_secret=None,
            client_name="Shia-Aalim MCP Client",
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )

    def _register_default_client(self) -> None:
        self._clients[_CLIENT_ID] = _OpenClient(
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
            client_name="Shia-Aalim MCP Client",
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
            token_endpoint_auth_method="none" if not _CLIENT_SECRET else "client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        known = self._clients.get(client_id)
        if known is not None:
            return known
        if _signing_secret() and client_id:
            # A client this instance never saw (registered before a restart):
            # synthesize an equivalent open client so its tokens keep working.
            return self._synth_client(client_id)
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = "dyn-" + secrets.token_hex(16)
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if _signing_secret():
            code = _sign_blob({
                "typ": "code",
                "cid": client.client_id or "",
                "ch": params.code_challenge,
                "ru": str(params.redirect_uri),
                "rux": params.redirect_uri_provided_explicitly,
                "sc": params.scopes or [],
                "res": params.resource,
                "exp": int(time.time()) + _CODE_TTL,
            })
        else:
            code = secrets.token_urlsafe(32)
            self._auth_codes[code] = AuthorizationCode(
                code=code,
                client_id=client.client_id or "",
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                scopes=params.scopes or [],
                expires_at=time.time() + _CODE_TTL,
                resource=params.resource,
            )
        query = {"code": code}
        if params.state:
            query["state"] = params.state
        from urllib.parse import urlencode

        sep = "&" if "?" in str(params.redirect_uri) else "?"
        return f"{params.redirect_uri}{sep}{urlencode(query)}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        if _signing_secret():
            p = _verify_blob(authorization_code)
            if not p or p.get("typ") != "code" or p.get("cid") != client.client_id:
                return None
            return AuthorizationCode(
                code=authorization_code,
                client_id=p["cid"],
                code_challenge=p["ch"],
                redirect_uri=p["ru"],
                redirect_uri_provided_explicitly=bool(p.get("rux")),
                scopes=p.get("sc") or [],
                expires_at=float(p["exp"]),
                resource=p.get("res"),
            )
        ac = self._auth_codes.get(authorization_code)
        if ac and ac.client_id == client.client_id:
            return ac
        return None

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = int(time.time())
        if _signing_secret():
            access = _sign_blob({"typ": "access", "cid": client_id, "sc": scopes,
                                 "res": resource, "exp": now + _TOKEN_TTL})
            refresh = _sign_blob({"typ": "refresh", "cid": client_id, "sc": scopes,
                                  "res": resource, "exp": None})
        else:
            access = secrets.token_urlsafe(32)
            refresh = secrets.token_urlsafe(32)
            self._access_tokens[access] = AccessToken(
                token=access,
                client_id=client_id,
                scopes=scopes,
                expires_at=now + _TOKEN_TTL,
                resource=resource,
            )
            self._refresh_tokens[refresh] = RefreshToken(
                token=refresh,
                client_id=client_id,
                scopes=scopes,
                expires_at=None,  # refresh tokens don't expire; access tokens do
            )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_TOKEN_TTL,
            refresh_token=refresh,
            scope=" ".join(scopes) if scopes else None,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._auth_codes.pop(authorization_code.code, None)
        return self._issue(
            client.client_id or "", authorization_code.scopes, authorization_code.resource
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        if _signing_secret():
            p = _verify_blob(refresh_token)
            if not p or p.get("typ") != "refresh" or p.get("cid") != client.client_id:
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=p["cid"],
                scopes=p.get("sc") or [],
                expires_at=None,
            )
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self._refresh_tokens.pop(refresh_token.token, None)
        return self._issue(client.client_id or "", scopes or refresh_token.scopes, None)

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        if _signing_secret():
            p = _verify_blob(token)
            if not p or p.get("typ") != "access":
                return None
            return AccessToken(
                token=token,
                client_id=p.get("cid") or "",
                scopes=p.get("sc") or [],
                expires_at=int(p["exp"]) if p.get("exp") else None,
                resource=p.get("res"),
            )
        at = self._access_tokens.get(token)
        if at is None:
            return None
        if at.expires_at is not None and at.expires_at < time.time():
            del self._access_tokens[token]
            return None
        return at

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)
