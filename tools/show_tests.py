"""Web-окно реального запуска unittest. Не рисует и не подменяет результаты."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
output=[]
finished=False


def run():
    global finished
    p=subprocess.Popen([sys.executable,str(ROOT/'tools/run_tests.py')],cwd=ROOT,
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
    for line in p.stdout:output.append(line)
    p.wait();output.append(f'\nКод завершения: {p.returncode}\n');finished=True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/log':
            content=''.join(output).encode('utf-8');kind='text/plain; charset=utf-8'
        else:
            content=b'''<!doctype html><meta charset="utf-8"><title>unittest C# cluster</title><style>body{margin:40px;background:#f8f8f6;color:#18251d;font:15px Segoe UI}h1{font-size:26px;font-weight:500}pre{border:1px solid #ccd4c7;border-radius:8px;padding:24px;background:white;font:12px/1.6 Consolas,monospace;white-space:pre-wrap}span{font:12px Segoe UI;color:#677463}</style><h1>unittest / C# master-worker</h1><span>py -3.12 tools/run_tests.py \xe2\x80\xa2 real TCP processes</span><pre id="log"></pre><script>async function read(){document.getElementById('log').textContent=await(await fetch('/log')).text()}read();setInterval(read,500)</script>''';kind='text/html; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def log_message(self,*args):pass


if __name__=='__main__':
    threading.Thread(target=run,daemon=True).start()
    print('Live unittest http://127.0.0.1:8096/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8096),Handler).serve_forever()
