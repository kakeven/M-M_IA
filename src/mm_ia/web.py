"""Interface local de fichas: python -m mm_ia.web."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from mm_ia import chatgpt_plan
from mm_ia.creation import (
    CreationConflict, approve_stage, edit_creation_sheet, finish_creation, get_creation,
    list_creations, propose_stage, start_creation,
)
from mm_ia.sheets import (
    catalog_for_ui, generate_sheet, get_sheet, list_sheets,
    normalize_sheet, save_changes,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 1024 * 1024


class SheetHandler(BaseHTTPRequestHandler):
    server_version = "FichaLocal/1.0"

    def _headers(self, status: int, content_type: str, size: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()

    def log_message(self, format, *args):
        # O callback OAuth contém um código sensível na URL.
        return

    def _redirect(self, destination: str):
        self.send_response(303)
        self.send_header("Location", destination)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def _send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_file(self, filename: str, content_type: str):
        body = (STATIC_DIR / filename).read_bytes()
        self._headers(200, content_type, len(body))
        self.wfile.write(body)

    def _read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Envie JSON com Content-Type application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY:
            raise ValueError("Tamanho da requisição inválido")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("A requisição deve conter um objeto JSON")
        return value

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        allowed_host = host in {f"127.0.0.1:{self.server.server_port}",
                                f"localhost:{self.server.server_port}"}
        return allowed_host and (not origin or origin in {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        })

    def _handle_error(self, error: Exception):
        if isinstance(error, CreationConflict):
            status = 409
        elif isinstance(error, (ValueError, json.JSONDecodeError)):
            status = 400
        elif isinstance(error, FileNotFoundError):
            status = 404
        elif isinstance(error, RuntimeError):
            status = 503
        else:
            status = 500
        self._send_json({"erro": str(error) if status != 500 else "Falha interna ao processar a ficha."}, status)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        try:
            if path in ("/auth/start", "/auth/callback") and not self._origin_allowed():
                self._send_json({"erro": "Origem não permitida"}, 403)
                return
            if path == "/auth/start":
                if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                    self._send_json({"erro": "Origem não permitida"}, 403)
                    return
                callback = f"http://127.0.0.1:{self.server.server_port}/auth/callback"
                self._redirect(chatgpt_plan.start(callback))
                return
            if path == "/auth/callback":
                try:
                    chatgpt_plan.finish(parse_qs(parsed.query))
                    self._redirect("/?chatgpt=conectado")
                except Exception as error:
                    print(f"Login ChatGPT não concluído: {type(error).__name__}: {error}", flush=True)
                    self._redirect("/?chatgpt=erro")
                return
            if path == "/":
                self._send_file("index.html", "text/html; charset=utf-8")
            elif path == "/static/app.css":
                self._send_file("app.css", "text/css; charset=utf-8")
            elif path == "/static/app.js":
                self._send_file("app.js", "text/javascript; charset=utf-8")
            elif path == "/static/creation.js":
                self._send_file("creation.js", "text/javascript; charset=utf-8")
            elif path == "/api/catalog":
                self._send_json(catalog_for_ui())
            elif path == "/api/auth/status":
                self._send_json(chatgpt_plan.status())
            elif path == "/api/auth/models":
                self._send_json({"modelos": chatgpt_plan.models()})
            elif path == "/api/sheets":
                self._send_json({"fichas": list_sheets()})
            elif path == "/api/creations":
                self._send_json({"criacoes": list_creations()})
            elif path.startswith("/api/creations/"):
                self._send_json({"criacao": get_creation(path.removeprefix("/api/creations/"))})
            elif path.startswith("/api/sheets/"):
                self._send_json(get_sheet(path.removeprefix("/api/sheets/")))
            else:
                self._send_json({"erro": "Página não encontrada"}, 404)
        except Exception as error:
            self._handle_error(error)

    def _write(self, method: str):
        if not self._origin_allowed():
            self._send_json({"erro": "Origem não permitida"}, 403)
            return
        path = unquote(urlsplit(self.path).path)
        try:
            data = self._read_json()
            if method == "POST" and path == "/api/generate":
                self._send_json({"ficha": generate_sheet(data)}, 201)
            elif method == "POST" and path == "/api/creations":
                self._send_json({"criacao": start_creation(data)}, 201)
            elif method == "POST" and path.startswith("/api/creations/"):
                parts = path.removeprefix("/api/creations/").split("/")
                actions = {"propose": propose_stage, "approve": approve_stage,
                           "finish": finish_creation, "sheet": edit_creation_sheet}
                if len(parts) != 2 or parts[1] not in actions:
                    self._send_json({"erro": "Página não encontrada"}, 404)
                    return
                self._send_json({"criacao": actions[parts[1]](parts[0], data)})
            elif method == "POST" and path == "/api/auth/disconnect":
                self._send_json({"revogado": chatgpt_plan.disconnect()})
            elif method == "POST" and path == "/api/preview":
                previous = None
                if data.get("id"):
                    try:
                        previous = get_sheet(f"nova:{data['id']}")["ficha"]
                    except (FileNotFoundError, ValueError):
                        pass
                self._send_json({"ficha": normalize_sheet(data, previous)})
            elif method == "PUT" and path.startswith("/api/sheets/"):
                identifier = path.removeprefix("/api/sheets/")
                self._send_json({"ficha": save_changes(identifier, data)})
            else:
                self._send_json({"erro": "Operação não encontrada"}, 404)
        except Exception as error:
            self._handle_error(error)

    def do_POST(self):
        self._write("POST")

    def do_PUT(self):
        self._write("PUT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), SheetHandler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Interface local: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
