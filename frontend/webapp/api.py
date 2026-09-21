"""Cliente HTTP da API REST do backend.

Único ponto do front que fala com o backend. Guarda os tokens na sessão (cookie assinado e HttpOnly),
envia `Authorization: Bearer`, renova o access token e traduz erros da API em `ApiError`.
"""

import asyncio
import base64
import json
import time
from collections.abc import MutableMapping
from typing import Any

import httpx


class ApiError(Exception):
    """Erro devolvido pela API (envelope `{"error": {...}}`) ou falha de comunicação."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []
        self.request_id = request_id

    @property
    def field_errors(self) -> dict[str, str]:
        """`{campo: mensagem}` a partir de `details` (só o primeiro erro de cada campo)."""
        out: dict[str, str] = {}
        for d in self.details:
            campo = d.get("field")
            if campo and campo not in out:
                out[campo] = d.get("issue", "")
        return out


class SessionExpired(Exception):
    """Sessão inválida/expirada: o usuário precisa entrar novamente."""


# Refresh tokens são de uso único e o reuso derruba todas as sessões. Requisições simultâneas do mesmo
# navegador (mesmo cookie) que tentem renovar juntas compartilham o resultado por alguns segundos.
_refresh_lock = asyncio.Lock()
_refresh_cache: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_TTL = 30.0
_MARGEM_EXPIRACAO = 30  # segundos: renova antes de expirar


def _jwt_exp(token: str | None) -> float | None:
    """Lê o `exp` do JWT sem validar assinatura (só para decidir quando renovar)."""
    try:
        payload = token.split(".")[1]  # type: ignore[union-attr]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


def _limpar(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None or v == "":
            continue
        out[k] = "true" if v is True else "false" if v is False else v
    return out


class Api:
    def __init__(self, client: httpx.AsyncClient, session: MutableMapping[str, Any], prefix: str) -> None:
        self.client = client
        self.session = session
        self.prefix = prefix

    def _encerrar_sessao(self) -> None:
        self.session.clear()
        self.session["_expirou"] = True  # o handler de SessionExpired avisa o usuário

    # ---------- tokens ----------
    def _headers(self) -> dict[str, str]:
        token = self.session.get("access")
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def ensure_fresh(self) -> None:
        """Renova proativamente se o access token está perto de expirar (evita corridas em chamadas paralelas)."""
        exp = _jwt_exp(self.session.get("access"))
        if self.session.get("refresh") and (exp is None or exp - time.time() < _MARGEM_EXPIRACAO):
            await self._refresh()

    async def _refresh(self) -> None:
        antigo = self.session.get("refresh")
        if not antigo:
            raise SessionExpired()
        async with _refresh_lock:
            agora = time.time()
            for k in [k for k, (t, _) in _refresh_cache.items() if agora - t > _CACHE_TTL]:
                del _refresh_cache[k]
            if antigo in _refresh_cache:
                par = _refresh_cache[antigo][1]
            else:
                try:
                    resp = await self.client.post(f"{self.prefix}/auth/refresh", json={"refresh_token": antigo})
                except httpx.HTTPError as exc:
                    raise ApiError(503, "API_INDISPONIVEL", "Não foi possível conectar à API.") from exc
                if resp.status_code != 200:
                    self._encerrar_sessao()
                    raise SessionExpired()
                dados = resp.json()
                par = {"access": dados["access_token"], "refresh": dados["refresh_token"]}
                _refresh_cache[antigo] = (agora, par)
        self.session["access"], self.session["refresh"] = par["access"], par["refresh"]

    # ---------- requisições ----------
    async def _send(self, method: str, path: str, *, stream: bool = False, **kw: Any) -> httpx.Response:
        kw["params"] = _limpar(kw.get("params"))
        req = self.client.build_request(method, f"{self.prefix}{path}", headers=self._headers(), **kw)
        try:
            return await self.client.send(req, stream=stream)
        except httpx.HTTPError as exc:
            raise ApiError(503, "API_INDISPONIVEL", "Não foi possível conectar à API. Tente novamente.") from exc

    async def _request(self, method: str, path: str, *, stream: bool = False, **kw: Any) -> httpx.Response:
        resp = await self._send(method, path, stream=stream, **kw)
        if resp.status_code == 401 and self.session.get("refresh") and not path.startswith("/auth/"):
            if stream:
                await resp.aclose()
            await self._refresh()
            for _, arquivo, *_ in (kw.get("files") or {}).values():  # reenvio: volta ao início dos arquivos
                if hasattr(arquivo, "seek"):
                    arquivo.seek(0)
            resp = await self._send(method, path, stream=stream, **kw)
        if resp.status_code >= 400:
            if stream:
                await resp.aread()
                await resp.aclose()
            if resp.status_code == 401 and not path.startswith("/auth/login"):
                self._encerrar_sessao()
                raise SessionExpired()
            raise self._erro(resp)
        return resp

    @staticmethod
    def _erro(resp: httpx.Response) -> ApiError:
        try:
            e = resp.json()["error"]
            return ApiError(resp.status_code, e["code"], e["message"], e.get("details"), e.get("request_id"))
        except Exception:
            return ApiError(resp.status_code, "ERRO_API", f"Erro inesperado da API (HTTP {resp.status_code}).")

    async def call(self, method: str, path: str, **kw: Any) -> Any:
        resp = await self._request(method, path, **kw)
        return None if resp.status_code == 204 or not resp.content else resp.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.call("GET", path, params=params)

    async def post(self, path: str, json: Any = None, **kw: Any) -> Any:
        return await self.call("POST", path, json=json, **kw)

    async def patch(self, path: str, json: Any = None) -> Any:
        return await self.call("PATCH", path, json=json)

    async def delete(self, path: str, **params: Any) -> Any:
        return await self.call("DELETE", path, params=params)

    async def stream(self, path: str) -> httpx.Response:
        """GET com corpo em streaming (downloads). O chamador deve fechar a resposta (`aclose`)."""
        return await self._request("GET", path, stream=True)
