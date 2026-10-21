"""Le e muda o fluxo principal da camera HAIZ (padrao Xiongmai) sem abrir a
pagina dela, pelo protocolo da propria camera (DVRIP, porta 34567).

    $P aibox/camera_haiz.py              mostra como esta
    $P aibox/camera_haiz.py --mudar      1920x1080 a 12 quadros/s (guarda o antes)
    $P aibox/camera_haiz.py --voltar     volta exatamente para o que estava

POR QUE. A HAIZ manda 2880x1620 a 30/s e a caixa decodifica tudo na CPU: na
versao NPU, depois que o YuNet foi para a NPU, isso e o que sobra de atraso.
1080p a 12/s e menos da metade dos pixels e menos da metade dos quadros.

USUARIO E SENHA: os do CAMERA_ARENA do .env (rtsp://.../user=X&password=Y...),
lidos e nunca impressos. Uma tentativa so: a camera bloqueia quem erra seguido.
O "antes" fica em haiz_antes.json, ao lado do .env, para o --voltar.
"""
import argparse
import hashlib
import json
import os
import re
import socket
import struct
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANTES = os.path.join(RAIZ, "haiz_antes.json")
PORTA = 34567


def credenciais():
    url = os.environ.get("CAMERA_ARENA", "")
    if not url:
        for linha in open(os.path.join(RAIZ, ".env"), encoding="utf-8", errors="replace"):
            if linha.startswith("CAMERA_ARENA="):
                url = linha.split("=", 1)[1].strip().strip('"').strip("'")
                break
    ip = re.search(r"(\d+\.\d+\.\d+\.\d+)", url)
    u = re.search(r"user=([^&]*)", url)
    s = re.search(r"password=([^&]*)", url)
    if not (ip and u and s):
        raise SystemExit("CAMERA_ARENA nao tem o formato Xiongmai (user=...&password=...)")
    return ip.group(1), u.group(1), s.group(1)


def sofia(senha):
    d = hashlib.md5(senha.encode()).digest()
    abc = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(abc[(a + b) % 62] for a, b in zip(d[::2], d[1::2]))


class Camera:
    def __init__(self, ip):
        self.s = socket.create_connection((ip, PORTA), timeout=8)
        self.sessao, self.seq = 0, 0

    def _ler(self, n):
        b = b""
        while len(b) < n:
            p = self.s.recv(n - len(b))
            if not p:
                raise ConnectionError("a camera fechou a conexao")
            b += p
        return b

    def pedir(self, msg, dados):
        corpo = json.dumps(dados).encode() + b"\x0a\x00"
        self.s.sendall(struct.pack("<BB2xII2xHI", 255, 0, self.sessao, self.seq, msg, len(corpo)) + corpo)
        self.seq += 1
        _, _, sessao, _, _, n = struct.unpack("<BB2xII2xHI", self._ler(20))
        resp = self._ler(n).rstrip(b"\x00\x0a").decode("utf-8", "replace")
        return sessao, (json.loads(resp) if resp else {})

    def entrar(self, usuario, senha):
        sessao, r = self.pedir(1000, {"EncryptType": "MD5", "LoginType": "DVRIP-Web",
                                      "PassWord": sofia(senha), "UserName": usuario})
        if r.get("Ret") not in (100, 101):
            raise SystemExit(f"a camera recusou o login (Ret {r.get('Ret')}). Nao vou tentar de novo.")
        self.sessao = int(r.get("SessionID", hex(sessao)), 16)

    def ler(self, nome):
        _, r = self.pedir(1042, {"Name": nome, "SessionID": "0x%08X" % self.sessao})
        if r.get("Ret") not in (100, None):
            raise SystemExit(f"nao li {nome} (Ret {r.get('Ret')})")
        return r[nome]

    def gravar(self, nome, valor):
        _, r = self.pedir(1040, {"Name": nome, "SessionID": "0x%08X" % self.sessao, nome: valor})
        return r.get("Ret")

    def capacidade(self):
        try:
            _, r = self.pedir(1360, {"Name": "EncodeCapability", "SessionID": "0x%08X" % self.sessao})
            return r.get("EncodeCapability")
        except Exception:
            return None


def resumo(enc):
    v = enc[0]["MainFormat"]["Video"]
    return f"{v.get('Resolution')} a {v.get('FPS')} quadros/s, {v.get('Compression')}, {v.get('BitRate')} kbps"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mudar", action="store_true")
    p.add_argument("--voltar", action="store_true")
    p.add_argument("--resolucao", default="1080P")
    p.add_argument("--fps", type=int, default=12)
    a = p.parse_args()
    ip, usuario, senha = credenciais()
    cam = Camera(ip)
    cam.entrar(usuario, senha)
    enc = cam.ler("Simplify.Encode")
    print(f"camera {ip}, fluxo principal agora: {resumo(enc)}")

    if a.voltar:
        if not os.path.exists(ANTES):
            raise SystemExit(f"nao achei {ANTES}: nada para voltar")
        antes = json.load(open(ANTES))
        ret = cam.gravar("Simplify.Encode", antes)
        print(f"voltei (Ret {ret}). Agora: {resumo(cam.ler('Simplify.Encode'))}")
        return 0

    if not a.mudar:
        cap = cam.capacidade()
        if cap:
            print("o que ela aceita:", json.dumps(cap)[:600])
        return 0

    if not os.path.exists(ANTES):
        json.dump(enc, open(ANTES, "w"), indent=1)
        print(f"guardei o antes em {ANTES}")
    novo = json.loads(json.dumps(enc))
    v = novo[0]["MainFormat"]["Video"]
    v["Resolution"], v["FPS"] = a.resolucao, a.fps
    v["BitRate"] = min(int(v.get("BitRate") or 4096), 4096)
    ret = cam.gravar("Simplify.Encode", novo)
    depois = cam.ler("Simplify.Encode")
    print(f"gravei (Ret {ret}). Agora: {resumo(depois)}")
    if depois[0]["MainFormat"]["Video"].get("Resolution") != a.resolucao:
        print("!! a camera nao aceitou essa resolucao. Rode sem --mudar para ver o que ela aceita.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
