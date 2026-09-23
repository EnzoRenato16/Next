"""A fila de entrega da AIBOX — roda pelo testes/entrega.mjs.

Sobe um servidor de mentira que se comporta mal DE PROPOSITO — fica mudo, fica
lento, recusa — e cobra da caixa o que importa quando a rede do laboratorio
falha: a analise nao espera, nenhum alerta se perde, e reenviar nao inventa
queda nova.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from aibox import entrega  # noqa: E402

entrega.ESPERA_INICIAL = 0.05   # o teste nao pode levar minutos esperando
entrega.ESPERA_MAX = 0.2

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


class Falso(BaseHTTPRequestHandler):
    modo = "bem"        # bem | fora | lento | recusa | calib403
    fora_por = 0        # quantas requisicoes responder 503 antes de voltar
    recebidos = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Falso.recebidos.append((self.path, corpo))
        if Falso.fora_por > 0:
            Falso.fora_por -= 1
            self.send_response(503); self.end_headers(); return
        if Falso.modo == "lento":
            time.sleep(1.5)
        if Falso.modo == "recusa" and self.path == "/api/evento":
            self.send_response(403); self.end_headers()
            self.wfile.write(b'{"detail":"origem nao autorizada"}'); return
        if Falso.modo == "calib403" and self.path == "/api/calibracao":
            self.send_response(403); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'{"id":1,"repetido":false}')


srv = HTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


def esperar(cond, prazo=5.0):
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ---- 1. A ANALISE NAO ESPERA A REDE ---------------------------------------
# O ponto inteiro. Com o servidor levando 1,5 s para responder, entregar o
# alerta tem que custar o mesmo que com ele rapido: nada.
Falso.modo, Falso.recebidos = "lento", []
f = entrega.Fala(BASE, "sala-teste")
t0 = time.perf_counter()
f.evento("queda", 7)
gasto = (time.perf_counter() - t0) * 1000
ok("entregar um alerta com o servidor LENTO nao segura o laco", gasto < 20,
   f"{gasto:.2f} ms")
ok("e ele chega mesmo assim", esperar(lambda: f.enviados == 1), f"{f.enviados}")
f.fechar()

# ---- 2. SERVIDOR FORA: GUARDA E REENVIA ------------------------------------
Falso.modo, Falso.recebidos, Falso.fora_por = "bem", [], 3
f = entrega.Fala(BASE, "sala-teste")
f.evento("queda", 3)
ok("com o servidor fora, o alerta fica guardado, e nao perdido",
   esperar(lambda: f.enviados == 1), f"enviados {f.enviados}, falhas {f.falhas}")
ok("e conta como entregue com atraso", f.atrasados == 1, f"{f.atrasados}")
tentativas = [c for p, c in Falso.recebidos if p == "/api/evento"]
ok("foram 4 tentativas: 3 recusadas pela rede e a que entrou",
   len(tentativas) == 4, f"{len(tentativas)}")
# A asserção que protege a cadeia: todas as tentativas levam a MESMA chave. Uma
# chave nova por tentativa faria o servidor gravar a mesma queda varias vezes.
chaves = {c["chave"] for c in tentativas}
ok("TODAS as tentativas levam a MESMA chave", len(chaves) == 1, f"{len(chaves)} chave(s)")
ha = [c["ocorreu_ha_ms"] for c in tentativas]
ok("e o 'ha quantos ms' cresce a cada tentativa, medido na hora de mandar",
   ha == sorted(ha) and ha[-1] > ha[0], str(ha))
ok("depois de entregar, a fila esvazia", f.pendentes == 0, str(f.pendentes))
f.fechar()

# ---- 3. ORDEM: A FILA NAO EMBARALHA ----------------------------------------
# A cadeia e uma sequencia. Dois alertas represados tem que chegar na ordem em
# que aconteceram.
Falso.modo, Falso.recebidos, Falso.fora_por = "bem", [], 2
f = entrega.Fala(BASE, "sala-teste")
f.evento("queda", 1)
f.evento("corrida", 2)
esperar(lambda: f.enviados == 2)
chegada = []
for p, c in Falso.recebidos:
    if p == "/api/evento" and (not chegada or chegada[-1] != c["aluno_id"]):
        chegada.append(c["aluno_id"])
ok("dois alertas represados chegam na ordem em que aconteceram",
   chegada == ["corpo-1", "corpo-2"], str(chegada))
f.fechar()

# ---- 4. RECUSA NAO SE REPETE ------------------------------------------------
Falso.modo, Falso.recebidos = "recusa", []
f = entrega.Fala(BASE, "sala-teste")
f.evento("queda", 9)
esperar(lambda: f.falhas == 1)
time.sleep(0.3)
n = len([1 for p, _ in Falso.recebidos if p == "/api/evento"])
ok("um alerta RECUSADO (403) nao e reenviado para sempre", n == 1, f"{n} envio(s)")
ok("e conta como falha, com o motivo guardado",
   f.falhas == 1 and "403" in (f.ultimo_erro or ""), f.ultimo_erro)
f.fechar()

# ---- 5. CALIBRACAO NAO PRENDE ALERTA ---------------------------------------
Falso.modo, Falso.recebidos, Falso.fora_por = "calib403", [], 0
f = entrega.Fala(BASE, "sala-teste")
f.calibracao([{"x": 1}])
ok("calibracao desligada no servidor (403) desliga a medicao na caixa",
   esperar(lambda: f.calib_recusada))
f.calibracao([{"x": 2}])
time.sleep(0.2)
n = len([1 for p, _ in Falso.recebidos if p == "/api/calibracao"])
ok("e depois disso ela para de mandar", n == 1, f"{n} lote(s)")
f.fechar()

Falso.modo, Falso.recebidos, Falso.fora_por = "bem", [], 1
f = entrega.Fala(BASE, "sala-teste")
f.calibracao([{"x": 3}])
f.evento("queda", 4)
esperar(lambda: f.enviados == 1)
n = len([1 for p, _ in Falso.recebidos if p == "/api/calibracao"])
ok("lote de calibracao que falha e DESCARTADO, e nao fica na frente da queda",
   f.enviados == 1 and n == 1, f"calib {n}, alertas {f.enviados}")
f.fechar()

# ---- 6. ENCERRAR COM O SERVIDOR FORA DIZ O QUE SOBROU -----------------------
Falso.modo, Falso.recebidos, Falso.fora_por = "bem", [], 10 ** 6
f = entrega.Fala(BASE, "sala-teste")
f.evento("queda", 5)
f.evento("queda", 6)
time.sleep(0.2)
sobrou = f.fechar(prazo=2.0)
ok("encerrar com o servidor fora devolve quantos alertas ficaram sem entregar",
   sobrou == 2, f"{sobrou}")
Falso.fora_por = 0

# ---- 7. AS POSES VAO JUNTO -------------------------------------------------
Falso.modo, Falso.recebidos = "bem", []
f = entrega.Fala(BASE, "sala-teste")
poses = [[[0.5, 0.5, 0.9]] * 17] * 3
f.evento("queda", 8, poses=poses)
esperar(lambda: f.enviados == 1)
c = [c for p, c in Falso.recebidos if p == "/api/evento"][0]
ok("as poses do corpo seguem junto com o alerta", c.get("poses") == poses,
   f"{len(c.get('poses') or [])} quadro(s)")
ok("e o tempo do quadro ao registro fica medido",
   f.ultimo_ms is not None and f.ultimo_ms >= 0, f"{f.ultimo_ms}")
f.fechar()

srv.shutdown()
print(f"\n{'FALHOU' if falhas else 'a fila de entrega passou'}")
sys.exit(1 if falhas else 0)
