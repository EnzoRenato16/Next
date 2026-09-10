"""Ponte entre o EduVision e a cadeia de hash do Auditix.

O EduVision roda no aparelho da sala e grava no SQLite dele. O painel lê o
banco do servidor.py. Sem esta ponte, um objeto suspeito detectado aqui nunca
apareceria lá — e "detectou mas ninguem viu" nao vale nada.

Tres regras, e todas existem para o mesmo fim: o registro local NUNCA depende
da rede ter funcionado.

1. O evento ja foi gravado no SQLite local ANTES de chegar aqui. Isto e envio,
   nao gravacao.
2. Roda em thread, com timeout curto. A fila de video nao pode parar porque um
   servidor demorou a responder.
3. Falha em silencio (com aviso no log). Rede caida nao pode derrubar a camera.

Usa urllib da biblioteca padrao de proposito: nao vale acrescentar dependencia
ao requirements do AIBOX so para fazer um POST.
"""

import json
import threading
import urllib.error
import urllib.request

from . import config


def _postar(caminho: str, corpo: dict) -> None:
    dados = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        config.AUDITIX_URL.rstrip("/") + caminho,
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.AUDITIX_TIMEOUT) as r:
            r.read()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        # O evento ja esta no SQLite local. Perder o envio custa a visibilidade
        # no painel, nao o registro.
        print(f"[ponte] nao enviei para o Auditix ({e}). Evento gravado local.")


def enviar_evento(tipo: str, local: str, aluno_id: str = "-") -> None:
    """Manda um evento para a cadeia do Auditix, sem bloquear o pipeline.

    `aluno_id` fica em "-" por padrao e assim deve ficar para objeto suspeito:
    amarrar um alerta de arma a um nome, com a taxa de erro que esta tecnologia
    tem, e o tipo de dano que nao se desfaz com um pedido de desculpas.
    """
    if not config.AUDITIX_URL:
        return
    corpo = {"aluno_id": aluno_id, "tipo_evento": tipo, "localizacao": local}
    threading.Thread(target=_postar, args=("/api/evento", corpo), daemon=True).start()
