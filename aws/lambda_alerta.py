"""Lambda que transforma um evento do Auditix num e-mail, pelo SES.

O servidor da escola manda um POST para a URL desta função quando acontece algo
que merece acordar alguém. Ela não decide nada: quem decide o que é alerta é a
Sala, e quem decide o que vira e-mail é o servidor. Aqui só se escreve e envia.

Por que uma função separada, e não o servidor mandando o e-mail direto: a
máquina da escola fica atrás do roteador, sem porta aberta, e pode estar
desligada. Credencial de e-mail guardada nela é credencial na mão de quem
sentar naquele computador. Aqui a credencial é do papel da função, não existe
como arquivo, e a AWS cuida do resto.

Variáveis de ambiente (todas na configuração da função):
    REMETENTE    e-mail verificado no SES, de onde a mensagem sai
    DESTINO      para quem vai; separe por vírgula para mais de um
    SEGREDO      o mesmo valor de WEBHOOK_SEGREDO no servidor da escola
"""
import hmac
import json
import os

import boto3

REMETENTE = os.environ["REMETENTE"]
DESTINO = [x.strip() for x in os.environ["DESTINO"].split(",") if x.strip()]
SEGREDO = os.environ.get("SEGREDO", "")

ses = boto3.client("ses")

TITULO = {
    "queda": "Possível queda",
    "agitacao": "Agitação entre pessoas",
    "objeto_perigoso": "Objeto perigoso",
    "patrimonio_sumiu": "Patrimônio fora do lugar",
    "reconhecido": "Pessoa reconhecida",
    "entrada": "Alguém entrou na sala",
}


def cabecalho(evento, nome):
    """Cabeçalhos de HTTP chegam com maiúsculas imprevisíveis."""
    for chave, valor in (evento.get("headers") or {}).items():
        if chave.lower() == nome.lower():
            return valor
    return ""


def responder(codigo, texto):
    return {"statusCode": codigo, "body": json.dumps({"msg": texto})}


def handler(evento, _contexto):
    # A URL de uma função é PÚBLICA. Sem esta conferência, quem a descobrir
    # dispara e-mails em nome da escola — e a conta é de vocês.
    if SEGREDO and not hmac.compare_digest(cabecalho(evento, "X-Auditix-Segredo"), SEGREDO):
        return responder(403, "segredo não confere")

    try:
        corpo = json.loads(evento.get("body") or "{}")
    except json.JSONDecodeError:
        return responder(400, "corpo não é JSON")

    tipo = str(corpo.get("tipo_evento", "evento"))
    onde = str(corpo.get("localizacao", "sala"))
    quando = str(corpo.get("timestamp", ""))
    quem = corpo.get("aluno_id") or "não identificado"
    hash_atual = str(corpo.get("hash_atual", ""))

    assunto = f"[Auditix] {TITULO.get(tipo, tipo)} em {onde}"
    # A mensagem diz o que o sistema viu e o que ele NÃO afirma. Um alerta que
    # soa como acusação faz alguém agir errado com pressa.
    texto = f"""{TITULO.get(tipo, tipo)}

Onde:    {onde}
Quando:  {quando}
Corpo:   {quem}
Tipo:    {tipo}

Isto é um pedido de conferência humana, não uma afirmação. O sistema mede pose
e movimento; ele não sabe o que aconteceu nem quem tem razão.

Registro {hash_atual[:16] or "(sem hash)"} na trilha de auditoria. Qualquer
alteração nele quebra a corrente daquele ponto em diante.
"""

    ses.send_email(
        Source=REMETENTE,
        Destination={"ToAddresses": DESTINO},
        Message={"Subject": {"Data": assunto, "Charset": "UTF-8"},
                 "Body": {"Text": {"Data": texto, "Charset": "UTF-8"}}},
    )
    return responder(200, "enviado")
