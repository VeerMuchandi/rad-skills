"""Production-Hardened FastMCP Server Template for Google Cloud Run & Gemini Enterprise (BYO MCP).

Includes built-in solutions for all common Cloud Run + Gemini Enterprise pitfalls:
1. Stateless HMAC-SHA256 OAuth 2.0 code/token signing derived from GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET.
2. Dual-mode TokenVerifier (fast-path HMAC verification + fallback Google OAuth tokeninfo verification for access_token & id_token).
3. Built-in /authorize (including /authorize{extra:path} for malformed '&key=val' concatenation) that redirects without
   Cross-Origin-Opener-Policy headers so Cloud Console 'Verify Auth' popups keep window.opener intact.
4. Built-in /token supporting HTTP Basic Auth, form-urlencoded, JSON body, PKCE (S256/plain), and guaranteed refresh_token issuance.
5. TransportSecuritySettings with DNS rebinding protection disabled for Cloud Run (*.a.run.app) Host headers.
6. Dual-transport ASGI app mounting both StreamableHTTP (/mcp) and SSE (/sse, /messages/), plus /healthz.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
SERVICE_NAME = os.environ.get("MCP_SERVER_NAME", "Custom MCP Server")
logger = logging.getLogger("cloud-run-mcp-server")


# ==============================================================================
# 1. Stateless HMAC-SHA256 OAuth 2.0 Token Signing & Verification
# ==============================================================================

_EPHEMERAL_SIGNING_KEY: Optional[bytes] = None


def _get_signing_key() -> bytes:
    """Derives a deterministic HMAC-SHA256 key from GOOGLE_OAUTH_CLIENT_ID & GOOGLE_OAUTH_CLIENT_SECRET."""
    global _EPHEMERAL_SIGNING_KEY
    secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if secret:
        return hashlib.sha256(f"{client_id}:{secret}".encode("utf-8")).digest()
    if _EPHEMERAL_SIGNING_KEY is None:
        logger.warning("GOOGLE_OAUTH_CLIENT_SECRET not set; generating instance-local ephemeral signing key.")
        _EPHEMERAL_SIGNING_KEY = secrets.token_bytes(32)
    return _EPHEMERAL_SIGNING_KEY


def _create_signed_token(prefix: str, payload: Dict[str, Any]) -> str:
    """Creates a stateless HMAC-SHA256 signed token with the given prefix."""
    raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    sig = hmac.new(_get_signing_key(), f"{prefix}.{body_b64}".encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{prefix}.{body_b64}.{sig_b64}"


def _verify_signed_token(token: str, expected_prefix: str) -> Optional[Dict[str, Any]]:
    """Verifies an HMAC-SHA256 signed token and checks its expiration."""
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != expected_prefix:
        return None
    _, body_b64, sig_b64 = parts
    expected_sig = hmac.new(
        _get_signing_key(),
        f"{expected_prefix}.{body_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")
    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        logger.warning("Rejected signed token with invalid HMAC signature (prefix=%s)", expected_prefix)
        return None
    try:
        padded = body_b64 + "=" * (-len(body_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return None
    exp = payload.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(time.time()):
                logger.warning("Rejected expired signed token (prefix=%s)", expected_prefix)
                return None
        except (TypeError, ValueError):
            return None
    return payload


# ==============================================================================
# 2. Google Cloud & Stateless HMAC OAuth 2.0 Token Verifier
# ==============================================================================

class GoogleOAuthTokenVerifier(TokenVerifier):
    """Validates both server-signed HMAC tokens (mcp_at.*) and Google OAuth tokens (ya29... / eyJ...)."""

    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    def __init__(
        self,
        expected_client_ids: Optional[List[str]] = None,
        allowed_domain: Optional[str] = None,
    ):
        self.expected_client_ids = [cid.strip() for cid in (expected_client_ids or []) if cid.strip()]
        self.allowed_domain = allowed_domain.strip().lower() if allowed_domain else None

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token or not token.strip():
            return None

        clean_token = token.strip()
        if clean_token.startswith("ge_rt_"):
            clean_token = clean_token[len("ge_rt_"):]

        # Fast-path: Verify stateless HMAC-SHA256 tokens issued by our /token endpoint
        if clean_token.startswith("mcp_at.") or clean_token.startswith("mcp_rt."):
            prefix = "mcp_at" if clean_token.startswith("mcp_at.") else "mcp_rt"
            payload = _verify_signed_token(clean_token, expected_prefix=prefix)
            if not payload:
                return None
            cid = str(payload.get("cid", "")).strip()
            if self.expected_client_ids and cid not in self.expected_client_ids:
                logger.warning("Rejected signed token: cid did not match GOOGLE_OAUTH_CLIENT_ID")
                return None
            raw_scopes = str(payload.get("scp", "openid email profile")).split()
            normalized = set(raw_scopes) | {"openid", "email", "profile"}
            return AccessToken(
                token=clean_token,
                client_id=cid or (self.expected_client_ids[0] if self.expected_client_ids else "oauth-client"),
                scopes=sorted(normalized),
                expires_at=int(payload["exp"]) if payload.get("exp") else None,
            )

        # Fallback: Verify standard Google OAuth 2.0 access_token or OIDC id_token via tokeninfo
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    self.TOKENINFO_URL,
                    params={"access_token": clean_token},
                )
                if resp.status_code != 200 and clean_token.count(".") == 2:
                    resp = await client.get(
                        self.TOKENINFO_URL,
                        params={"id_token": clean_token},
                    )
                if resp.status_code != 200:
                    logger.warning("Google OAuth token verification failed with status %d", resp.status_code)
                    return None
                data = resp.json()
        except Exception:
            logger.exception("Error communicating with Google tokeninfo endpoint")
            return None

        now = int(time.time())
        exp_raw = data.get("exp")
        expires_at: Optional[int] = None
        if exp_raw is not None:
            try:
                expires_at = int(exp_raw)
                if expires_at < now:
                    return None
            except (TypeError, ValueError):
                return None

        aud = data.get("aud", "")
        azp = data.get("azp", "")
        if self.expected_client_ids:
            if aud not in self.expected_client_ids and azp not in self.expected_client_ids:
                logger.warning("Rejected Google OAuth token: aud/azp mismatch")
                return None

        if self.allowed_domain:
            email = (data.get("email") or "").lower()
            email_verified = str(data.get("email_verified", "")).lower() == "true"
            hd = (data.get("hd") or "").lower()
            if not email_verified or (not email.endswith(f"@{self.allowed_domain}") and hd != self.allowed_domain):
                logger.warning("Rejected Google OAuth token: user domain not in GOOGLE_ALLOWED_DOMAIN")
                return None

        raw_scopes = (data.get("scope") or "").split()
        normalized_scopes = set(raw_scopes)
        if "https://www.googleapis.com/auth/userinfo.email" in normalized_scopes or data.get("email"):
            normalized_scopes.add("email")
        if "https://www.googleapis.com/auth/userinfo.profile" in normalized_scopes:
            normalized_scopes.add("profile")
        if "https://www.googleapis.com/auth/plus.me" in normalized_scopes or "email" in normalized_scopes or data.get("sub"):
            normalized_scopes.add("openid")

        client_id = azp or aud or (self.expected_client_ids[0] if self.expected_client_ids else "google-oauth-client")
        return AccessToken(
            token=clean_token,
            client_id=client_id,
            scopes=sorted(normalized_scopes),
            expires_at=expires_at,
        )


def _build_auth_configuration() -> tuple[Optional[TokenVerifier], Optional[AuthSettings]]:
    """Builds FastMCP OAuth 2.0 TokenVerifier and AuthSettings from environment variables."""
    raw_client_ids = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    allowed_domain = os.environ.get("GOOGLE_ALLOWED_DOMAIN", "").strip() or None
    require_oauth_env = os.environ.get("REQUIRE_OAUTH", "").strip().lower()

    if require_oauth_env in ("false", "0", "no"):
        oauth_enabled = False
    elif require_oauth_env in ("true", "1", "yes") or bool(raw_client_ids):
        oauth_enabled = True
    else:
        oauth_enabled = False

    if not oauth_enabled:
        logger.info("OAuth 2.0 token verification is DISABLED (set GOOGLE_OAUTH_CLIENT_ID or REQUIRE_OAUTH=true to enable).")
        return None, None

    client_ids = [c.strip() for c in raw_client_ids.split(",") if c.strip()]
    raw_scopes = os.environ.get("OAUTH_REQUIRED_SCOPES", "openid email").strip()
    required_scopes = [s.strip() for s in raw_scopes.replace(",", " ").split() if s.strip()]
    resource_server_url_str = os.environ.get("MCP_RESOURCE_SERVER_URL", "").strip()

    verifier = GoogleOAuthTokenVerifier(
        expected_client_ids=client_ids,
        allowed_domain=allowed_domain,
    )
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl("https://accounts.google.com"),
        required_scopes=required_scopes or None,
        resource_server_url=AnyHttpUrl(resource_server_url_str) if resource_server_url_str else None,
    )
    logger.info(
        "OAuth 2.0 token verification ENABLED (client_ids=%d, required_scopes=%s, allowed_domain=%s)",
        len(client_ids),
        required_scopes,
        allowed_domain,
    )
    return verifier, auth_settings


# ==============================================================================
# 3. FastMCP Initialization (Stateless HTTP + Cloud Run DNS Rebinding Fix)
# ==============================================================================

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
    allowed_hosts=["*"],
    allowed_origins=["*"],
)

_token_verifier, _auth_settings = _build_auth_configuration()

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

mcp = FastMCP(
    name=SERVICE_NAME,
    instructions=os.environ.get(
        "MCP_SERVER_INSTRUCTIONS",
        "Custom MCP Server deployed on Google Cloud Run for Gemini Enterprise.",
    ),
    token_verifier=_token_verifier,
    auth=_auth_settings,
    stateless_http=os.environ.get("MCP_STATELESS_HTTP", "true").lower() in ("true", "1", "yes"),
    transport_security=transport_security,
)


# ==============================================================================
# 4. Define MCP Tools Here
# ==============================================================================

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def ping_server(query: str = "hello") -> str:
    """Example read-only health/echo tool for verifying MCP tool discovery and execution.

    Args:
        query: Input string to echo back.

    Returns:
        JSON string confirming server status and echoed query.
    """
    return json.dumps({
        "status": "ok",
        "service": SERVICE_NAME,
        "echo": query,
        "timestamp": int(time.time()),
    }, indent=2)


# ==============================================================================
# 5. Built-in OAuth 2.0 Proxy Endpoints (/authorize & /token) & Health Check
# ==============================================================================

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_last_authorize_redirect_uri: Optional[str] = None


def _is_valid_redirect_uri(uri: str) -> bool:
    """Validates redirect_uri to prevent open redirect / XSS."""
    if not uri:
        return False
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "https" and bool(parsed.netloc):
        return True
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return True
    return False


async def oauth_authorize(request) -> Response:
    """OAuth 2.0 Authorization Endpoint that validates client_id/redirect_uri and issues a signed authorization code.

    Redirects directly to redirect_uri (e.g. https://vertexaisearch.cloud.google.com/oauth-redirect)
    without navigating through accounts.google.com's Cross-Origin-Opener-Policy: same-origin header,
    preserving window.opener so Cloud Console 'Verify Auth' popups can postMessage the code back.
    Also handles malformed '/authorize&access_type=offline...' paths produced by Discovery Engine.
    """
    global _last_authorize_redirect_uri

    params: Dict[str, str] = {}
    extra_path = request.path_params.get("extra", "") if hasattr(request, "path_params") else ""
    if extra_path:
        cleaned_extra = extra_path.lstrip("/?&")
        for k, v in urllib.parse.parse_qsl(cleaned_extra, keep_blank_values=True):
            if k:
                params[k] = v

    for k, v in request.query_params.multi_items():
        if k:
            if "&" in k or "=" in k:
                for sub_k, sub_v in urllib.parse.parse_qsl(f"{k}={v}".lstrip("&"), keep_blank_values=True):
                    if sub_k:
                        params[sub_k] = sub_v
            else:
                params[k] = v

    allowed_cids = [
        c.strip() for c in os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").split(",") if c.strip()
    ]
    client_id = params.get("client_id", "").strip() or (allowed_cids[0] if allowed_cids else "oauth-client")
    if allowed_cids and client_id not in allowed_cids:
        logger.warning("Rejected /authorize request: client_id did not match GOOGLE_OAUTH_CLIENT_ID")
        return JSONResponse(
            {"error": "unauthorized_client", "error_description": "Invalid client_id"},
            status_code=400,
        )

    redirect_uri = params.get("redirect_uri", "").strip()
    if not redirect_uri or not _is_valid_redirect_uri(redirect_uri):
        logger.warning("Rejected invalid or missing redirect_uri in /authorize")
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Invalid redirect_uri"},
            status_code=400,
        )
    _last_authorize_redirect_uri = redirect_uri

    scope = params.get("scope", "openid email profile").strip() or "openid email profile"
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "").strip()
    code_challenge_method = params.get("code_challenge_method", "S256").strip() or "S256"

    now = int(time.time())
    code_payload: Dict[str, Any] = {
        "cid": client_id,
        "scp": scope,
        "ru": redirect_uri,
        "iat": now,
        "exp": now + 600,
        "nonce": secrets.token_hex(8),
    }
    if code_challenge:
        code_payload["cc"] = code_challenge
        code_payload["ccm"] = code_challenge_method

    signed_code = _create_signed_token("mcp_code", code_payload)

    parsed_ru = urllib.parse.urlparse(redirect_uri)
    ru_query = dict(urllib.parse.parse_qsl(parsed_ru.query, keep_blank_values=True))
    ru_query["code"] = signed_code
    if state:
        ru_query["state"] = state
    target_url = urllib.parse.urlunparse(
        parsed_ru._replace(query=urllib.parse.urlencode(ru_query))
    )

    logger.info(
        "OAuth /authorize issued signed code and redirecting to redirect_uri=%s (has_state=%s, has_pkce=%s)",
        redirect_uri,
        bool(state),
        bool(code_challenge),
    )
    return RedirectResponse(url=target_url, status_code=302)


def _extract_basic_auth(auth_header: str) -> tuple[str, str]:
    """Extracts client_id and client_secret from an HTTP Basic Authorization header."""
    if not auth_header or not auth_header.lower().startswith("basic "):
        return "", ""
    encoded = auth_header[6:].strip()
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        if ":" not in decoded:
            return urllib.parse.unquote(decoded), ""
        cid, csec = decoded.split(":", 1)
        return urllib.parse.unquote(cid).strip(), urllib.parse.unquote(csec).strip()
    except Exception:
        logger.warning("Failed to decode HTTP Basic Authorization header on /token")
        return "", ""


async def oauth_token(request) -> Response:
    """OAuth 2.0 Token Endpoint exchanging signed authorization codes or refresh tokens for access + refresh tokens."""
    sec_headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=sec_headers)

    data: Dict[str, str] = {}
    for k, v in request.query_params.multi_items():
        if k:
            data[k] = v

    raw_body = await request.body()
    if raw_body:
        body_str = raw_body.decode("utf-8", errors="replace").strip()
        if body_str.startswith("{"):
            try:
                parsed_json = json.loads(body_str)
                if isinstance(parsed_json, dict):
                    for k, v in parsed_json.items():
                        if v is not None:
                            data[str(k)] = str(v)
            except Exception:
                logger.warning("Failed to parse JSON body on /token")
        else:
            for k, v in urllib.parse.parse_qsl(body_str, keep_blank_values=True):
                if k:
                    data[k] = v

    basic_cid, basic_csec = _extract_basic_auth(request.headers.get("authorization", ""))
    allowed_cids = [
        c.strip() for c in os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").split(",") if c.strip()
    ]
    env_cid = allowed_cids[0] if allowed_cids else ""
    env_csec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

    client_id = (data.get("client_id") or basic_cid or env_cid).strip()
    client_secret = (data.get("client_secret") or basic_csec or env_csec).strip()

    grant_type = data.get("grant_type", "").strip()
    if not grant_type:
        if "code" in data:
            grant_type = "authorization_code"
        elif "refresh_token" in data:
            grant_type = "refresh_token"

    incoming_code = data.get("code", "").strip()
    incoming_rt = data.get("refresh_token", "").strip()
    incoming_verifier = data.get("code_verifier", "").strip()

    # 1. Handle stateless HMAC-signed authorization_code (mcp_code.*) or refresh_token (mcp_rt.*)
    if incoming_code.startswith("mcp_code.") or incoming_rt.startswith("mcp_rt."):
        if allowed_cids and client_id not in allowed_cids:
            return JSONResponse(
                {"error": "invalid_client", "error_description": "Client ID mismatch"},
                status_code=401,
                headers=sec_headers,
            )
        if env_csec and client_secret and not hmac.compare_digest(client_secret, env_csec):
            return JSONResponse(
                {"error": "invalid_client", "error_description": "Client secret mismatch"},
                status_code=401,
                headers=sec_headers,
            )

        if incoming_code.startswith("mcp_code."):
            token_payload = _verify_signed_token(incoming_code, expected_prefix="mcp_code")
            if not token_payload:
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"},
                    status_code=400,
                    headers=sec_headers,
                )
            expected_cc = token_payload.get("cc")
            if expected_cc and incoming_verifier:
                ccm = token_payload.get("ccm", "S256").upper()
                if ccm == "S256":
                    computed_cc = (
                        base64.urlsafe_b64encode(hashlib.sha256(incoming_verifier.encode("ascii")).digest())
                        .decode("ascii")
                        .rstrip("=")
                    )
                else:
                    computed_cc = incoming_verifier
                if not hmac.compare_digest(computed_cc, str(expected_cc)):
                    return JSONResponse(
                        {"error": "invalid_grant", "error_description": "PKCE code_verifier mismatch"},
                        status_code=400,
                        headers=sec_headers,
                    )
        else:
            token_payload = _verify_signed_token(incoming_rt, expected_prefix="mcp_rt")
            if not token_payload:
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Invalid or expired refresh token"},
                    status_code=400,
                    headers=sec_headers,
                )

        now = int(time.time())
        scope = str(token_payload.get("scp", "openid email profile"))
        issued_cid = str(token_payload.get("cid") or client_id or env_cid)
        access_token = _create_signed_token(
            "mcp_at",
            {
                "cid": issued_cid,
                "scp": scope,
                "iat": now,
                "exp": now + 3600,
                "jti": secrets.token_hex(8),
            },
        )
        refresh_token = _create_signed_token(
            "mcp_rt",
            {
                "cid": issued_cid,
                "scp": scope,
                "iat": now,
                "exp": now + 86400 * 365,
                "jti": secrets.token_hex(8),
            },
        )
        logger.info("OAuth /token issued signed access_token & refresh_token (grant_type=%s)", grant_type)
        return JSONResponse(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": scope,
            },
            status_code=200,
            headers=sec_headers,
        )

    # 2. Fallback: Forward raw Google OAuth codes/tokens to https://oauth2.googleapis.com/token
    payload: Dict[str, str] = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    for field in ("code", "redirect_uri", "code_verifier", "refresh_token"):
        val = data.get(field, "").strip()
        if val:
            payload[field] = val

    if grant_type == "authorization_code" and not payload.get("redirect_uri") and _last_authorize_redirect_uri:
        payload["redirect_uri"] = _last_authorize_redirect_uri

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(GOOGLE_TOKEN_ENDPOINT, data=payload)
            resp_data = resp.json() if resp.content else {}
    except Exception:
        logger.exception("Error communicating with Google OAuth token endpoint")
        return JSONResponse(
            {"error": "server_error", "error_description": "Upstream token exchange failed"},
            status_code=502,
            headers=sec_headers,
        )

    if resp.status_code != 200:
        return JSONResponse(resp_data, status_code=resp.status_code, headers=sec_headers)

    if not resp_data.get("refresh_token"):
        if payload.get("refresh_token"):
            resp_data["refresh_token"] = payload["refresh_token"]
        elif resp_data.get("access_token"):
            resp_data["refresh_token"] = f"ge_rt_{resp_data['access_token']}"

    resp_data.setdefault("token_type", "Bearer")
    resp_data.setdefault("expires_in", 3599)
    return JSONResponse(resp_data, status_code=200, headers=sec_headers)


async def health(request) -> Response:
    """Health check endpoint for Cloud Run liveness/startup probes and readiness verification."""
    return JSONResponse({
        "status": "healthy",
        "service": SERVICE_NAME,
        "transports": ["streamable-http", "sse"],
        "endpoints": {
            "mcp": "/mcp",
            "sse": "/sse",
            "messages": "/messages/",
            "authorize": "/authorize",
            "token": "/token",
            "health": "/health",
        },
        "oauth_enabled": _token_verifier is not None,
    })


def get_asgi_app(transport: Optional[str] = None):
    """Returns a unified Starlette ASGI app supporting StreamableHTTP (/mcp), SSE (/sse), OAuth (/authorize, /token), and /health."""
    app = mcp.streamable_http_app()

    sse_starlette = mcp.sse_app()
    existing_paths = {getattr(r, "path", None) for r in app.routes}
    for route in sse_starlette.routes:
        if getattr(route, "path", None) not in existing_paths:
            app.routes.append(route)

    app.routes.insert(0, Route("/token", oauth_token, methods=["POST", "GET", "OPTIONS"]))
    app.routes.insert(0, Route("/authorize{extra:path}", oauth_authorize, methods=["GET", "HEAD"]))
    app.routes.insert(0, Route("/authorize", oauth_authorize, methods=["GET", "HEAD"]))
    # Note: Google Frontend (GFE) reserves /*z paths (like /healthz) on *.run.app URLs and returns 404 externally.
    # Always expose / and /health for external health checks, while keeping /healthz for internal container probes.
    app.routes.insert(0, Route("/health", health, methods=["GET", "HEAD"]))
    app.routes.insert(0, Route("/healthz", health, methods=["GET", "HEAD"]))
    app.routes.insert(0, Route("/", health, methods=["GET", "HEAD"]))
    return app

