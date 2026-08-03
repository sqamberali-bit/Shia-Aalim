"""Minimal OAuth provider for the MCP endpoint (auto-approve, public corpus).

The Shia-Aalim corpus is public data — there's nothing user-specific to gate.
This provider satisfies the MCP OAuth handshake so claude.ai Custom Connectors
can authenticate reliably, with or without dynamic client registration.

Configure via env:
  MCP_OAUTH_CLIENT_ID     — the client ID to register in the connector
                             (default: ``shia-aalim-mcp``)
  MCP_OAUTH_CLIENT_SECRET — optional shared secret; if set, the connector
                             must send it during the token exchange

The issuer URL is the public URL of your Space
(e.g. ``https://sqamberali-shia-aalim.hf.space``).

Implementation notes: the token/auth-code/refresh-token records subclass the
SDK's pydantic models (``AccessToken``/``AuthorizationCode``/``RefreshToken``)
rather than ad-hoc dataclasses — the SDK's bearer middleware and session
manager read fields like ``claims``/``subject``/``resource`` from them, so
custom types missing those fields crash the first authenticated request.
"""

from __future__ import annotations

import os
import secrets
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
_TOKEN_TTL = 3600 * 24 * 7  # 7 days


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
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = "dyn-" + secrets.token_hex(16)
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=params.scopes or [],
            expires_at=time.time() + 600,  # 10 min
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
        ac = self._auth_codes.get(authorization_code)
        if ac and ac.client_id == client.client_id:
            return ac
        return None

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = int(time.time())
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
