"""Minimal OAuth provider for the MCP endpoint (auto-approve, public corpus).

The Shia-Aalim corpus is public data — there's nothing user-specific to gate.
This provider satisfies the MCP OAuth handshake so claude.ai Custom Connectors
can authenticate reliably without dynamic client registration.

Configure via env:
  MCP_OAUTH_CLIENT_ID     — the client ID to register in the connector
                             (default: ``shia-aalim-mcp``)
  MCP_OAUTH_CLIENT_SECRET — optional shared secret; if set, the connector
                             must send it during the token exchange

The issuer URL is the public URL of your Space
(e.g. ``https://sqamberali-shia-aalim.hf.space``).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

_CLIENT_ID = os.environ.get("MCP_OAUTH_CLIENT_ID", "shia-aalim-mcp")
_CLIENT_SECRET = os.environ.get("MCP_OAUTH_CLIENT_SECRET") or None
_TOKEN_TTL = 3600 * 24 * 7  # 7 days


@dataclass
class _AuthCode:
    client_id: str
    code_challenge: str
    redirect_uri: str
    scopes: list[str]
    created: float = field(default_factory=time.time)


@dataclass
class _AccessToken:
    client_id: str
    scopes: list[str]
    created: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = self.created + _TOKEN_TTL


@dataclass
class _RefreshToken:
    client_id: str
    scopes: list[str]
    created: float = field(default_factory=time.time)


class ShiaAalimOAuthProvider(
    OAuthAuthorizationServerProvider[_AuthCode, _RefreshToken, _AccessToken]
):
    """Auto-approving OAuth provider for the public corpus MCP endpoint."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, _AuthCode] = {}
        self._access_tokens: dict[str, _AccessToken] = {}
        self._refresh_tokens: dict[str, _RefreshToken] = {}

        self._register_default_client()

    def _register_default_client(self) -> None:
        self._clients[_CLIENT_ID] = OAuthClientInformationFull(
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
            client_name="Shia-Aalim MCP Client",
            redirect_uris=["https://claude.ai/oauth/callback", "http://localhost/callback"],
            token_endpoint_auth_method="none" if not _CLIENT_SECRET else "client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        )

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._clients.get(client_id)

    async def register_client(
        self, client_info: OAuthClientInformationFull
    ) -> None:
        if not client_info.client_id:
            client_info.client_id = "dyn-" + secrets.token_hex(16)
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = _AuthCode(
            client_id=client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=str(params.redirect_uri),
            scopes=params.scopes or [],
        )
        query = {"code": code}
        if params.state:
            query["state"] = params.state
        sep = "&" if "?" in str(params.redirect_uri) else "?"
        return f"{params.redirect_uri}{sep}{urlencode(query)}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[_AuthCode]:
        ac = self._auth_codes.get(authorization_code)
        if ac and ac.client_id == client.client_id:
            return ac
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: _AuthCode
    ) -> OAuthToken:
        for k, v in list(self._auth_codes.items()):
            if v is authorization_code:
                del self._auth_codes[k]
                break

        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = time.time()
        self._access_tokens[access] = _AccessToken(
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            created=now,
        )
        self._refresh_tokens[refresh] = _RefreshToken(
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            created=now,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_TOKEN_TTL,
            refresh_token=refresh,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[_RefreshToken]:
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: _RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        for k, v in list(self._refresh_tokens.items()):
            if v is refresh_token:
                del self._refresh_tokens[k]
                break

        access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        now = time.time()
        use_scopes = scopes or refresh_token.scopes
        self._access_tokens[access] = _AccessToken(
            client_id=client.client_id or "",
            scopes=use_scopes,
            created=now,
        )
        self._refresh_tokens[new_refresh] = _RefreshToken(
            client_id=client.client_id or "",
            scopes=use_scopes,
            created=now,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_TOKEN_TTL,
            refresh_token=new_refresh,
            scope=" ".join(use_scopes) if use_scopes else None,
        )

    async def load_access_token(self, token: str) -> Optional[_AccessToken]:
        at = self._access_tokens.get(token)
        if at and at.expires_at > time.time():
            return at
        if at:
            del self._access_tokens[token]
        return None

    async def revoke_token(
        self, token: _AccessToken | _RefreshToken
    ) -> None:
        if isinstance(token, _AccessToken):
            self._access_tokens = {
                k: v for k, v in self._access_tokens.items() if v is not token
            }
        elif isinstance(token, _RefreshToken):
            self._refresh_tokens = {
                k: v for k, v in self._refresh_tokens.items() if v is not token
            }
