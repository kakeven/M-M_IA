"""Sign in with ChatGPT para uso do plano em uma instalação local."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from urllib.parse import urlencode

import jwt
import keyring
import requests
from openai import OpenAI

from mm_ia.config import PROJECT_ROOT

AUTH_BASE = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = f"{AUTH_BASE}/api/accounts/oauth/token"
AUTHORIZE_URL = f"{AUTH_BASE}/api/accounts/authorize"
JWKS_URL = f"{AUTH_BASE}/.well-known/jwks.json"
HOST_FILE = PROJECT_ROOT / ".local" / "chatgpt-host.json"
KEYRING_SERVICE = "mm_ia_chatgpt_plan"
KEYRING_USER = "active"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"

_lock = threading.RLock()
_pending: dict[str, object] | None = None


def _host_id() -> str:
    HOST_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HOST_FILE.exists():
        value = json.loads(HOST_FILE.read_text(encoding="utf-8"))["ext_agent_host_id"]
        if isinstance(value, str) and value.startswith("urn:uuid:"):
            return value
        raise RuntimeError("Identificador local do ChatGPT inválido.")
    value = f"urn:uuid:{uuid.uuid4()}"
    HOST_FILE.write_text(json.dumps({"ext_agent_host_id": value}), encoding="utf-8")
    return value


def _load() -> dict | None:
    try:
        saved = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if not saved:
            return None
        pointer = json.loads(saved)
        pieces = [
            keyring.get_password(KEYRING_SERVICE, f"{pointer['id']}:{index}")
            for index in range(pointer["count"])
        ]
        if any(piece is None for piece in pieces):
            raise RuntimeError("Credenciais locais do ChatGPT incompletas.")
        return json.loads("".join(pieces))
    except Exception as error:
        raise RuntimeError("Gerenciador de credenciais do sistema indisponível.") from error


def _save(profile: dict) -> None:
    try:
        old = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        serialized = json.dumps(profile)
        identifier = uuid.uuid4().hex
        pieces = [serialized[index:index + 1000] for index in range(0, len(serialized), 1000)]
        for index, piece in enumerate(pieces):
            keyring.set_password(KEYRING_SERVICE, f"{identifier}:{index}", piece)
        keyring.set_password(
            KEYRING_SERVICE, KEYRING_USER,
            json.dumps({"id": identifier, "count": len(pieces)}),
        )
    except Exception as error:
        raise RuntimeError("Não foi possível guardar a conexão no gerenciador de credenciais.") from error
    if old:
        try:
            pointer = json.loads(old)
            for index in range(pointer["count"]):
                keyring.delete_password(KEYRING_SERVICE, f"{pointer['id']}:{index}")
        except (ValueError, KeyError, keyring.errors.KeyringError):
            pass


def status() -> dict:
    with _lock:
        profile = _load()
        return {
            "conectado": bool(profile and "chatgpt.tokens.use.direct" in profile.get("scopes", [])),
            "email": profile.get("email") if profile else None,
            "nome": profile.get("name") if profile else None,
            "uso_url": "https://chatgpt.com/#settings/Usage",
        }


def start(redirect_uri: str) -> str:
    """Cria uma transação OAuth com PKCE e retorna a URL oficial de autorização."""
    global _pending
    with _lock:
        profile = _load()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        client_id = profile["client_id"] if profile else "dynamic_agent_client"
        _pending = {
            "state": state, "nonce": nonce, "verifier": verifier,
            "redirect_uri": redirect_uri, "client_id": client_id,
            "subject": profile.get("subject") if profile else None,
            "expires_at": time.time() + 600,
        }
        params = {
            "client_id": client_id, "ext_agent_host_id": _host_id(),
            "response_type": "code", "redirect_uri": redirect_uri,
            "scope": SCOPE, "resource": RESOURCE,
            "state": state, "nonce": nonce,
            "code_challenge_method": "S256", "code_challenge": challenge,
        }
        if profile:
            if profile.get("id_token"):
                params["id_token_hint"] = profile["id_token"]
            if profile.get("email"):
                params["login_hint"] = profile["email"]
        else:
            params["agent_name_hint"] = "Fichas M&M IA"
        return f"{AUTHORIZE_URL}?{urlencode(params)}"


def finish(query: dict[str, list[str]]) -> None:
    """Consome uma única vez o callback, verifica a identidade e salva a concessão."""
    global _pending
    with _lock:
        pending, _pending = _pending, None
        if not pending or time.time() > pending["expires_at"]:
            raise RuntimeError("Conexão expirada. Inicie o login novamente.")
        if not secrets.compare_digest(query.get("state", [""])[0], pending["state"]):
            raise RuntimeError("Estado do login inválido.")
        if query.get("error"):
            raise RuntimeError("O acesso ao plano não foi autorizado.")
        code = query.get("code", [""])[0]
        issued = query.get("client_id", [""])[0]
        if not code:
            raise RuntimeError("Código de autorização ausente.")
        client_id = issued if pending["client_id"] == "dynamic_agent_client" else pending["client_id"]
        if not client_id or client_id == "dynamic_agent_client":
            raise RuntimeError("O ChatGPT não retornou o identificador da conexão.")
        if issued and issued != client_id:
            raise RuntimeError("Identificador da conexão não corresponde ao login iniciado.")
        response = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "client_id": client_id,
            "code": code, "code_verifier": pending["verifier"],
            "redirect_uri": pending["redirect_uri"], "resource": RESOURCE,
        }, timeout=25)
        response.raise_for_status()
        token = response.json()
        id_token = token.get("id_token", "")
        if not id_token:
            raise RuntimeError("O ChatGPT não retornou uma identidade verificável.")
        signing_key = jwt.PyJWKClient(JWKS_URL).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, signing_key.key, algorithms=["RS256", "ES256"],
            audience=client_id, issuer=AUTH_BASE,
            options={"require": ["sub", "exp", "iat"]}, leeway=5,
        )
        if (
            claims.get("nonce") != pending["nonce"]
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
        ):
            raise RuntimeError("A identidade do ChatGPT não corresponde ao login iniciado.")
        if pending["subject"] and claims["sub"] != pending["subject"]:
            raise RuntimeError("A conta retornada é diferente da conexão anterior.")
        scopes = token.get("scope", "").split()
        if "chatgpt.tokens.use.direct" not in scopes:
            raise RuntimeError("O uso do plano não foi autorizado nesta conexão.")
        if not token.get("access_token") or not token.get("refresh_token"):
            raise RuntimeError("Credenciais incompletas retornadas pelo ChatGPT.")
        _save({
            "client_id": client_id, "subject": claims["sub"],
            "email": claims.get("email"), "name": claims.get("name"),
            "id_token": id_token, "access_token": token["access_token"],
            "refresh_token": token["refresh_token"], "scopes": scopes,
            "expires_at": time.time() + int(token.get("expires_in", 3600)),
        })


def _access_token() -> str:
    with _lock:
        profile = _load()
        if not profile or "chatgpt.tokens.use.direct" not in profile.get("scopes", []):
            raise RuntimeError("Conecte seu ChatGPT Plus antes de gerar a ficha.")
        if time.time() < profile["expires_at"] - 60:
            return profile["access_token"]
        response = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "client_id": profile["client_id"],
            "refresh_token": profile["refresh_token"], "resource": RESOURCE,
        }, timeout=25)
        response.raise_for_status()
        renewed = response.json()
        if not renewed.get("access_token") or not renewed.get("refresh_token"):
            raise RuntimeError("Sessão do ChatGPT expirada. Conecte novamente.")
        profile.update({
            "access_token": renewed["access_token"],
            "refresh_token": renewed["refresh_token"],
            "expires_at": time.time() + int(renewed.get("expires_in", 3600)),
            "scopes": renewed.get("scope", "").split() or profile["scopes"],
        })
        if "chatgpt.tokens.use.direct" not in profile["scopes"]:
            raise RuntimeError("O uso do plano foi revogado. Conecte novamente.")
        _save(profile)
        return profile["access_token"]


def models() -> list[dict[str, str]]:
    try:
        response = requests.get(
            f"{RESOURCE}/models", headers={"Authorization": f"Bearer {_access_token()}"},
            timeout=25,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError("Não foi possível consultar os modelos do seu plano ChatGPT.") from error
    return [
        {"id": item["slug"], "nome": item.get("display_name", item["slug"])}
        for item in response.json().get("models", [])
        if isinstance(item, dict) and item.get("visibility") == "list" and item.get("slug")
    ]


def ask_json(prompt: str, request: str, model: str, effort: str | None = None) -> dict:
    if not model:
        raise ValueError("Escolha um modelo disponível na sua conta ChatGPT.")
    if effort not in (None, "none", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("Esforço de raciocínio inválido.")
    if effort == "none" and model.startswith(("gpt-6-astra", "gpt-6.1-sol")):
        raise ValueError("Esse modelo não aceita esforço de raciocínio 'nenhum'.")
    if effort == "max" and model.startswith("gpt-5.5"):
        raise ValueError("Esse modelo não aceita esforço de raciocínio 'máximo'.")
    client = OpenAI(api_key=_access_token(), base_url=RESOURCE, max_retries=0)
    output: list[str] = []
    completed = False
    try:
        options = {"reasoning": {"effort": effort}} if effort else {}
        with client.responses.create(
            model=model,
            instructions=prompt + "\nResponda somente um objeto JSON válido, sem markdown.",
            # O modo json_object exige a palavra JSON na própria entrada, não
            # apenas em instructions. O conteúdo original continua intacto.
            input=[{"role": "user", "content": f"{request}\n\nResponda somente em JSON."}],
            text={"format": {"type": "json_object"}},
            store=False, stream=True,
            **options,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    output.append(event.delta)
                elif event.type == "response.failed":
                    code = getattr(getattr(event.response, "error", None), "code", None)
                    if code in ("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"):
                        raise RuntimeError("Limite do ChatGPT Plus atingido. Consulte Gerenciar uso do plano.")
                    raise RuntimeError("A geração pelo ChatGPT falhou.")
                elif event.type == "response.incomplete":
                    raise RuntimeError("A resposta do ChatGPT ficou incompleta.")
                elif event.type == "response.completed":
                    completed = True
    except RuntimeError:
        raise
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        body = getattr(error, "body", None)
        detail = body.get("error", body) if isinstance(body, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else None
        if code in ("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"):
            raise RuntimeError("Limite do ChatGPT Plus atingido. Consulte Gerenciar uso do plano.") from error
        if status_code == 429:
            raise RuntimeError("Limite do ChatGPT Plus atingido. Consulte Gerenciar uso do plano.") from error
        if status_code in (401, 403):
            raise RuntimeError("A conexão com o ChatGPT perdeu a autorização. Conecte novamente.") from error
        if status_code == 400:
            parameter = str(detail.get("param") or "") if isinstance(detail, dict) else ""
            if parameter.startswith("reasoning"):
                raise RuntimeError("O modelo não aceitou o esforço escolhido. Selecione o padrão ou outro nível.") from error
            if parameter == "model":
                raise RuntimeError("O modelo selecionado não está disponível para esta conexão.") from error
            if parameter in ("input", "text.format"):
                raise RuntimeError("O ChatGPT rejeitou o formato da mensagem. Verifique a entrada e tente novamente.") from error
            raise RuntimeError("O ChatGPT rejeitou a requisição. Confira o modelo e tente novamente.") from error
        raise RuntimeError("Falha de conexão com o ChatGPT. Tente novamente.") from error
    if not completed:
        raise RuntimeError("A conexão com o ChatGPT terminou antes de concluir a resposta.")
    try:
        value = json.loads("".join(output))
    except json.JSONDecodeError as error:
        raise RuntimeError("O ChatGPT retornou uma resposta que não é JSON válido.") from error
    if not isinstance(value, dict):
        raise RuntimeError("O ChatGPT retornou um formato de resposta inesperado.")
    return value


def disconnect() -> bool:
    """Revoga a sessão renovável e elimina as credenciais locais."""
    global _pending
    with _lock:
        _pending = None
        profile = _load()
        revoked = True
        if profile and profile.get("refresh_token"):
            try:
                discovery = requests.get(
                    f"{AUTH_BASE}/.well-known/openid-configuration", timeout=15
                ).json()
                endpoint = discovery["revocation_endpoint"]
                response = requests.post(endpoint, data={
                    "token": profile["refresh_token"],
                    "token_type_hint": "refresh_token",
                    "client_id": profile["client_id"],
                }, timeout=15)
                revoked = response.status_code == 200
            except (requests.RequestException, KeyError, ValueError):
                revoked = False
        try:
            pointer_raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if pointer_raw:
                pointer = json.loads(pointer_raw)
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
                for index in range(pointer["count"]):
                    keyring.delete_password(KEYRING_SERVICE, f"{pointer['id']}:{index}")
        except keyring.errors.PasswordDeleteError:
            pass
        return revoked
