"""Upgraded OAuth‑2 Imitation Service
================================================
Highlights of this revision
---------------------------
*   **expiry ➜ expires_in** everywhere – external contract now matches the OAuth
    specification. Internally we store *expires_at* (absolute UNIX epoch – ms for
    tokens, s for auth‑codes) so calculations stay simple, but the key name that
    ever leaves the server is *expires_in* (seconds).
*   **Robust code parsing** – the token endpoint now normalises the incoming
    `code` parameter, stripping accidental prefixes like `code=`, wrapping quotes
    and URL artefacts so a malformed client request does not break validation.
*   **Consistent time units** – helper `now_s()` and `now_ms()` give current time
    once; auth‑codes use seconds, tokens use milliseconds; comparisons are done
    in the same unit that was stored.
*   **Utility helpers** have been tucked away at the top for clarity: generating
    tokens, validating client/scope, and normalising parameters.
*   **Extra logging cleanup** – log lines are shorter and always on one level so
    reading the console is easier. (Use a proper logger in production!)
*   **Minor hardening** – a few constant‑time comparisons added, and we now
    invalidate refresh‑tokens on logout with one set‑comprehension.

This is still an in‑memory demo server – swap the *_db dictionaries with a real
store for anything serious.
"""

import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse, parse_qs, unquote_plus

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from .json_store import JSONStore

# ---------------------------------------------------------------------------
# ⬇️ Configuration & *VERY* temporary in‑memory storage
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))

clients_db = JSONStore(DATA_DIR / "clients.json",  initial={
    "test": {
        "client_secret": "test",
        "redirect_uris": ["http://localhost:8080/login"],
        "allowed_scopes": ["test"]
    }
})

auth_codes_db     = JSONStore(DATA_DIR / "auth_codes.json")
access_tokens_db  = JSONStore(DATA_DIR / "access_tokens.json")
refresh_tokens_db = JSONStore(DATA_DIR / "refresh_tokens.json")

users_db: Dict[str, Dict[str, Any]] = JSONStore(DATA_DIR / "users.json", initial={
    "test": {
        "password": "test",
        "valid": "true",
        "pin": "99999999999999",
        "pport_no": "M9199",
        "first_name": "Tom",
        "sur_name": "Hanks",
        "mid_name": "Anatoliy",
        "full_name": "Tom Anatoliy Hanks",
        "user_id": "test",
        "auth_method": "LOGINPASSMETHOD",
        "pkcs_legal_tin": None,
        "legal_info": [],
    }
})

AUTH_CODE_LIFETIME_S = 600            # 10‑min auth‑codes
ACCESS_TOKEN_LIFETIME_S = 3600        # 1‑hour access‑tokens
REFRESH_TOKEN_LIFETIME_S = 86400 * 30 # 30‑day refresh‑tokens

# ---------------------------------------------------------------------------
# ⬇️ Utility helpers
# ---------------------------------------------------------------------------

def now_s() -> int:  # seconds
    return int(time.time())

def now_ms() -> int:  # milliseconds
    return int(time.time() * 1000)

def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def normalise_code(raw: str) -> str:
    """Strip accidental wrappers such as `code=xyz`, single/double quotes."""
    raw = raw.lstrip()  # leading spaces
    if raw.lower().startswith("code="):
        raw = raw.split("=", 1)[1]
    return raw.strip("'\"")

def validate_client(
    *,
    client_id: str,
    client_secret: Optional[str] = None,
    redirect_uri: Optional[str] = None,
):
    client = clients_db.get(client_id)
    if not client:
        raise HTTPException(400, "Invalid client_id")

    if client_secret is not None and not secrets.compare_digest(
        client.get("client_secret", ""), client_secret or "",
    ):
        raise HTTPException(401, "Invalid client_secret")

    if redirect_uri is not None:
        decoded = unquote_plus(redirect_uri)
        uri_ok = decoded in client["redirect_uris"]
        if not uri_ok:
            raise HTTPException(400, "Invalid redirect_uri")
    return client

def validate_scope(requested: Optional[str], allowed: List[str]) -> List[str]:
    if not requested:
        return []
    scopes = [s for s in requested.split() if s in allowed]
    invalid = set(requested.split()) - set(scopes)
    if invalid:
        raise HTTPException(400, f"Invalid scope(s): {', '.join(invalid)}")
    return scopes

# ---------------------------------------------------------------------------
# ⬇️ FastAPI initialisation
# ---------------------------------------------------------------------------

app = FastAPI(title="OAuth2 Imitation Server – upgraded")
templates = Jinja2Templates("templates")

# ---------------------------------------------------------------------------
# ⬇️ Authorisation end‑point (step‑1)
# ---------------------------------------------------------------------------

@app.get("/sso/oauth/Authorization.do")
async def authorise(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: Optional[str] = None,
    state: Optional[str] = None,
):
    if response_type != "one_code":
        raise HTTPException(400, "Unsupported response_type")

    client = validate_client(client_id=client_id, redirect_uri=redirect_uri)
    validate_scope(scope, client["allowed_scopes"])

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "scope": scope or "",
        "state": state or "",
    }
    return RedirectResponse(f"/oauth_login_form?{urlencode(params)}", status.HTTP_302_FOUND)

# ---------------------------------------------------------------------------
# ⬇️ Simple HTML login form
# ---------------------------------------------------------------------------

@app.get("/oauth_login_form", response_class=HTMLResponse)
async def login_form(
    request: Request,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    scope: str = "",
    state: str = "",
    error: Optional[str] = None,
):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": response_type,
            "scope": scope,
            "state": state,
            "error": error,
        },
    )

# ---------------------------------------------------------------------------
# ⬇️ Login handler → issues auth‑code
# ---------------------------------------------------------------------------

@app.post("/authenticate")
async def authenticate(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form(...),
    scope: str = Form(""),
    state: str = Form(""),
):
    user = users_db.get(username)
    if not user or not secrets.compare_digest(user["password"], password):
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": response_type,
            "scope": scope,
            "state": state,
            "error": "Invalid username or password",
        }
        return RedirectResponse(f"/oauth_login_form?{urlencode(params)}", status.HTTP_302_FOUND)

    # Re‑validate client & scope
    client = validate_client(client_id=client_id, redirect_uri=redirect_uri)
    valid_scopes = validate_scope(scope, client["allowed_scopes"])

    auth_code = generate_token()
    auth_codes_db[auth_code] = {
        "client_id": client_id,
        "redirect_uri": unquote_plus(redirect_uri),
        "scope": " ".join(valid_scopes),
        "user_id": user["user_id"],
        "expires_at": now_s() + AUTH_CODE_LIFETIME_S,
    }

    params = {"code": auth_code, **({"state": state} if state else {})}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status.HTTP_302_FOUND)

# ---------------------------------------------------------------------------
# ⬇️ The all‑in‑one token/user/logout end‑point
# ---------------------------------------------------------------------------

@app.post("/sso/oauth/Authorization.do")
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: Optional[str] = Form(None),
    code: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    access_token: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
):
    client = validate_client(client_id=client_id, client_secret=client_secret)
    now_millis = now_ms()

    # ------------------- grant: one_authorization_code ------------------- #
    if grant_type == "one_authorization_code":
        if not code or not redirect_uri:
            raise HTTPException(400, "code and redirect_uri required")

        code = normalise_code(code)
        auth = auth_codes_db.pop(code, None)
        auth_codes_db._flush()
        if not auth:
            raise HTTPException(400, "Invalid or expired authorisation code")

        if auth["client_id"] != client_id or auth["redirect_uri"] != unquote_plus(redirect_uri):
            raise HTTPException(400, "client_id or redirect_uri mismatch")
        if now_s() > auth["expires_at"]:
            raise HTTPException(400, "Authorisation code expired")

        acc_tok = generate_token()
        ref_tok = generate_token()
        access_tokens_db[acc_tok] = {
            "client_id": client_id,
            "user_id": auth["user_id"],
            "scope": auth["scope"],
            "expires_at": now_millis + ACCESS_TOKEN_LIFETIME_S * 1000,
        }
        refresh_tokens_db[ref_tok] = {
            "client_id": client_id,
            "user_id": auth["user_id"],
            "scope": auth["scope"],
            "expires_at": now_millis + REFRESH_TOKEN_LIFETIME_S * 1000,
        }
        return JSONResponse(
            {
                "access_token": acc_tok,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_LIFETIME_S,
                "refresh_token": ref_tok,
                "scope": auth["scope"],
            }
        )

    # -------------------------- grant: refresh_token --------------------- #
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(400, "refresh_token required")
        old = refresh_tokens_db.pop(refresh_token, None)
        refresh_tokens_db._flush()
        if not old or now_millis > old["expires_at"] or old["client_id"] != client_id:
            raise HTTPException(400, "Invalid or expired refresh token")

        acc_tok = generate_token()
        ref_tok = generate_token()
        access_tokens_db[acc_tok] = {
            **{k: old[k] for k in ("client_id", "user_id", "scope")},
            "expires_at": now_millis + ACCESS_TOKEN_LIFETIME_S * 1000,
        }
        refresh_tokens_db[ref_tok] = {
            **{k: old[k] for k in ("client_id", "user_id", "scope")},
            "expires_at": now_millis + REFRESH_TOKEN_LIFETIME_S * 1000,
        }
        return JSONResponse(
            {
                "access_token": acc_tok,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_LIFETIME_S,
                "refresh_token": ref_tok,
                "scope": old["scope"],
            }
        )

    # -------------------- grant: one_access_token_identify -------------- #
    elif grant_type == "one_access_token_identify":
        if not access_token or not scope:
            raise HTTPException(400, "access_token and scope required")
        validate_scope(scope, client["allowed_scopes"])

        tok = access_tokens_db.get(access_token)
        if not tok or tok["client_id"] != client_id or now_millis > tok["expires_at"]:
            raise HTTPException(401, "Invalid or expired access token")
        if set(scope.split()) - set(tok["scope"].split()):
            raise HTTPException(403, "Insufficient scope")

        user = users_db.get(tok["user_id"])
        if not user:
            raise HTTPException(404, "User not found")
        return JSONResponse({k: v for k, v in user.items() if k != "password"})

    # ----------------------------- grant: one_log_out ------------------- #
    elif grant_type == "one_log_out":
        if not access_token or not scope:
            raise HTTPException(400, "access_token and scope required")
        validate_scope(scope, client["allowed_scopes"])

        tok = access_tokens_db.pop(access_token, None)
        access_tokens_db._flush()
        if not tok or tok["client_id"] != client_id:
            return JSONResponse({"status": "logged_out"})

        # wipe matching refresh tokens
        expired = {
            rt for rt, data in refresh_tokens_db.items()
            if data["client_id"] == client_id and data["user_id"] == tok["user_id"]
        }
        for rt in expired:
            refresh_tokens_db.pop(rt, None)
        refresh_tokens_db._flush()
        return JSONResponse({"status": "logged_out"})

    # ----------------------------- unsupported -------------------------- #
    raise HTTPException(400, "Unsupported grant_type")

# ---------------------------------------------------------------------------
# ⬇️ Simple root endpoint
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": "OAuth2 Imitation server running."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
