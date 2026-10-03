"""Interface do criador manual: python "Motor de regras/web.py"."""
import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from urllib.parse import parse_qs, urlsplit

from ficha import Ficha, DEFESAS
from armazenamento import carregar_ficha, listar_fichas, salvar
from poderes import (efeitos_poderes_dicionario, vantagens, pericias_por_habilidade,
    extras_dict_atualizado, falhas_dict_atualizado, VANTAGENS_GRADUADAS,
    LIMITES_VANTAGENS, PERICIAS_ESPECIALIZADAS)
from calculos import HABILIDADES
from regras_ficha import TAMANHOS_VEICULO, TAMANHOS_QG
from ficha_utilitarios import resumo_texto

STATIC = Path(__file__).resolve().parent / "static"
LOCK = RLock()


def catalogo():
    return {"habilidades": list(HABILIDADES), "defesas": DEFESAS,
        "pericias": pericias_por_habilidade, "vantagens": vantagens,
        "vantagens_graduadas": sorted(VANTAGENS_GRADUADAS),
        "limites_vantagens": LIMITES_VANTAGENS,
        "pericias_especializadas": sorted(PERICIAS_ESPECIALIZADAS),
        "efeitos": efeitos_poderes_dicionario, "extras": extras_dict_atualizado,
        "falhas": falhas_dict_atualizado, "veiculos": TAMANHOS_VEICULO, "qgs": TAMANHOS_QG}


class ManualHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def enviar(self, valor, status=200, tipo="application/json; charset=utf-8"):
        corpo = valor if isinstance(valor, bytes) else json.dumps(valor, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(corpo)

    def origem_permitida(self):
        hosts = {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}
        origem = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (origem is None or origem in {f"http://{host}" for host in hosts})

    def erro(self, erro):
        status = 404 if isinstance(erro, FileNotFoundError) else (
            400 if isinstance(erro, (ValueError, KeyError, TypeError, AttributeError)) else 500)
        self.enviar({"erro": str(erro) if status != 500 else "Não foi possível processar a ficha."}, status)

    def do_GET(self):
        if not self.origem_permitida():
            self.enviar({"erro": "Origem não permitida."}, 403)
            return
        url = urlsplit(self.path)
        try:
            arquivos = {"/": ("index.html", "text/html; charset=utf-8"),
                        "/app.css": ("app.css", "text/css; charset=utf-8"),
                        "/app.js": ("app.js", "text/javascript; charset=utf-8")}
            if url.path in arquivos:
                nome, tipo = arquivos[url.path]
                self.enviar((STATIC / nome).read_bytes(), tipo=tipo)
            elif url.path == "/api/catalogo":
                self.enviar(catalogo())
            elif url.path == "/api/fichas":
                self.enviar({"fichas": listar_fichas()})
            elif url.path == "/api/ficha":
                nome = parse_qs(url.query).get("arquivo", [""])[0]
                self.enviar({"ficha": carregar_ficha(nome).para_dict(), "arquivo": nome})
            else:
                self.enviar({"erro": "Página não encontrada."}, 404)
        except Exception as erro:
            self.erro(erro)

    def do_POST(self):
        if not self.origem_permitida():
            self.enviar({"erro": "Origem não permitida."}, 403)
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Envie os dados em JSON.")
            tamanho = int(self.headers.get("Content-Length", "0"))
            if not 0 < tamanho <= 1024 * 1024:
                raise ValueError("Tamanho de requisição inválido.")
            dados = json.loads(self.rfile.read(tamanho))
            if not isinstance(dados, dict):
                raise ValueError("Formato de dados inválido.")
            rota = urlsplit(self.path).path
            if rota == "/api/nova":
                self.enviar({"ficha": Ficha(dados.get("np", 10), dados.get("jogador", ""),
                    dados.get("nome", "Novo personagem")).para_dict()}, 201)
                return
            if rota not in ("/api/calcular", "/api/salvar", "/api/exportar"):
                self.enviar({"erro": "Operação não encontrada."}, 404)
                return
            ficha = Ficha.de_dict(dados.get("ficha"))
            resultado = {"ficha": ficha.para_dict()}
            if rota == "/api/salvar":
                with LOCK:
                    caminho = salvar(ficha, dados.get("arquivo", ficha.nomePersonagem))
                resultado["arquivo"] = caminho.name
            if rota == "/api/exportar":
                resultado["texto"] = resumo_texto(ficha)
            self.enviar(resultado)
        except Exception as erro:
            self.erro(erro)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    servidor = ThreadingHTTPServer(("127.0.0.1", args.port), ManualHandler)
    url = f"http://127.0.0.1:{servidor.server_port}/"
    print(f"Criador manual: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
