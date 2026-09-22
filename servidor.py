# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn[standard]", "psycopg[binary]", "httpx"]
# ///
"""
Auditix, servidor da sala auditada.

Roda com:   uv run servidor.py
Abre em:    http://127.0.0.1:8000

Faz três coisas:

1. Serve a página. O navegador não fala com PostgreSQL, e localhost é contexto
   seguro, então servir a página daqui resolve o banco E a permissão de câmera
   de uma vez só.

2. Guarda os eventos numa CADEIA DE HASH SHA-256, na tabela
   logs_seguranca_escola. Cada linha carrega o hash da anterior, então mexer
   numa linha antiga quebra a cadeia dali para a frente e o ponto exato da
   adulteração aparece.

3. Guarda o mapa de calor agregado e entrega as visões para o Power BI.

4. Serve o painel de leitura em /painel, que consome estes mesmos endpoints.
   A página da sala GRAVA; o painel só LÊ.

Sobre o banco: leia DATABASE_URL do arquivo .env ao lado deste. Se não houver,
ou se o Postgres não responder, cai para SQLite local sozinho. Isso é de
propósito: demonstração que morre porque a nuvem caiu é demonstração perdida.
"""

import hashlib
import json
import math
import os
import secrets
import sqlite3
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

AQUI = Path(__file__).parent
PAGINA = AQUI / "auditix-sala.html"
PAINEL = AQUI / "auditix-painel.html"
# Os modelos de rosto e de corpo moram aqui, versionados junto do projeto. Vinham
# de CDN, e uma rede que bloqueie jsdelivr ou googleapis deixava a tela presa em
# "Carregando o detector de corpo..." para sempre. Numa apresentacao isso e o
# projeto inteiro nao abrindo.
ESTATICOS = AQUI / "vendor"
# O tipo de cada arquivo, decidido AQUI e nao pelo sistema operacional. O
# mimetypes do Python consulta o registro do Windows, que nao conhece .mjs: o
# arquivo ia como "binario qualquer", o Chrome recusava executar um modulo com
# tipo errado, e a tela ficava presa em "Carregando o detector de corpo..." sem
# nenhum erro. No Linux passava, porque la a extensao e conhecida — foi assim
# que escapou dos testes.
TIPOS = {
    ".mjs":  "text/javascript",
    ".js":   "text/javascript",
    ".wasm": "application/wasm",     # instantiateStreaming exige exatamente este
    ".json": "application/json",
    ".css":  "text/css",
    ".woff2": "font/woff2",
    ".task": "application/octet-stream",
    ".bin":  "application/octet-stream",
}
# O caminho do SQLite é trocável para que teste não escreva no banco de quem
# está usando o sistema: sem isso, cada rodada de teste enche a sala de quedas
# que nunca aconteceram.
SQLITE = Path(os.environ["SQLITE_ARQUIVO"]) if os.environ.get("SQLITE_ARQUIVO") \
    else AQUI / "auditix.db"
GENESE = "0" * 64

# eventos que merecem acordar alguem na hora: e-mail e foto do momento.
#
# CORRIDA NAO ESTA AQUI, e a ausencia dela e uma decisao, nao um esquecimento.
# Correr em corredor de escola acontece no intervalo inteiro, todo dia. Se cada
# corrida virasse e-mail, a coordenacao receberia dezenas por recreio e em uma
# semana criaria um filtro para a caixa — e a queda de verdade morreria nesse
# filtro junto com o resto. Corrida aparece no painel, entra no banco, conta no
# mapa de calor, e nao acorda ninguem.
GRAVES = {"queda", "briga", "pedido_ajuda", "agitacao", "objeto_perigoso",
          "patrimonio_sumiu"}

# Eventos graves que mesmo assim NAO recebem imagem, e a regra e imposta aqui e
# nao combinada na tela.
#
# Um pedido de ajuda e alguem pedindo socorro, nao um incidente que a camera
# entendeu. Guardar a imagem de quem aperta o botao fotografa exatamente a
# pessoa que menos precisa ter a imagem guardada: quem passou mal, quem estava
# sofrendo bullying, quem so queria que um adulto viesse. E o sistema nao sabe
# sequer se o motivo esta dentro do enquadramento.
#
# Isto mora no servidor porque combinar com o navegador nao vale nada: qualquer
# um com o endereco poderia mandar a foto assim mesmo.
SEM_FOTO = {"pedido_ajuda"}

# O que o painel MOSTRA. A Sala mede tres coisas hoje: queda (rede treinada em
# 4.509 clipes), corrida (regra geometrica) e briga (regra sobre as features do
# DIFEM). O banco ainda guarda eventos de versoes anteriores e os
# reconhecimentos de rosto, que continuam gravados e continuam sendo conferidos
# pela cadeia de hash — apagar linha nenhuma, isso quebraria a corrente de
# proposito. O filtro e so de leitura. Vazio mostra tudo.
TIPOS_PAINEL = {x.strip() for x in
                os.environ.get("PAINEL_TIPOS",
                               "queda,corrida,briga,pedido_ajuda").split(",")
                if x.strip()}

# Foto do momento do alerta, so em evento GRAVE. Nao e vigilancia continua: e o
# recorte de um instante que ja virou registro, para que a conferencia humana
# que o alerta pede possa acontecer sem ninguem ter de correr ate a sala.
FOTOS = os.environ.get("FOTOS", "1").strip().lower() not in ("0", "nao", "não", "false", "")
# Depois disto a imagem se apaga sozinha. O registro do evento fica; a imagem
# nao — ela e a parte que identifica uma pessoa, e nao precisa durar.
FOTO_DIAS = float(os.environ.get("FOTO_DIAS", "7"))
# Um recorte de 320px em JPEG da uns 20 KB. O teto existe para o endpoint nao
# virar porta de entrada de arquivo grande.
FOTO_MAX = 400_000

# ---- registro de calibracao ------------------------------------------------
# O que o sistema VIU, e nao so o que ele ACUSOU.
#
# Hoje o Auditix so deixa rastro quando dispara. Isso responde "quantos alertas
# houve" e nao responde a pergunta que decide se o produto serve numa escola:
# QUANTAS VEZES ELE QUASE DISPAROU SEM MOTIVO. O botao "foi engano" tambem nao
# responde, porque so captura o erro que alguem percebeu e teve paciencia de
# marcar.
#
# Com isto ligado, cada corpo firme deposita uma amostra por segundo com os
# numeros crus da analise — nota da rede, distancia ao treino, velocidade,
# inclinacao — mesmo quando nada acontece. Uma hora de aula vira a distribuicao
# completa do que o sistema enxergou, e dali sai a margem real: o quao perto do
# limiar as coisas chegaram num dia comum.
#
# DESLIGADO por padrao. E ferramenta de medicao, nao de operacao: ligar sozinho
# um processo que escreve continuamente no banco de alguem seria surpresa ruim.
CALIBRACAO = os.environ.get("CALIBRACAO", "0").strip().lower() in ("1", "sim", "true")
# Amostra e dado descartavel, ao contrario de evento. A tabela de eventos nunca
# perde linha porque isso quebraria a corrente de hash; esta aqui NAO entra na
# corrente, entao pode e deve ser podada — senao cresce para sempre.
CALIBRACAO_DIAS = float(os.environ.get("CALIBRACAO_DIAS", "30"))
# Teto por requisicao. O navegador manda em lote a cada 15s; com 6 pessoas na
# sala isso da ~90 amostras. 500 e folga larga e fecha a porta para abuso.
CALIBRACAO_LOTE = 500

# Prazo do consentimento biometrico, o mesmo VALIDADE_DIAS do auditix-sala.html.
# Dois lugares com o mesmo numero e ruim; ficam iguais de proposito ate o dia em
# que a Sala passar a ler o prazo do servidor.
CADASTRO_DIAS = float(os.environ.get("CADASTRO_DIAS", "365"))
# Um descritor de rosto tem 128 numeros, e o cadastro guarda ate 6 amostras.
# O teto existe para o endpoint nao virar porta de entrada de payload grande.
CADASTRO_MAX = 12


# ---- biometria cancelavel --------------------------------------------------
# O PEDIDO ERA "nao guardar a imagem". Ela ja nao e guardada: o que o cadastro
# grava sao 128 numeros medidos do rosto, e a foto de alerta sobe com a cabeca
# em mosaico. Mas 128 numeros AINDA SAO dado biometrico — quem tiver o banco
# pode comparar esses numeros com outro banco e descobrir que a mesma pessoa
# esta nos dois. Isso e o que esta tabela protege daqui em diante.
#
# A IDEIA DO HASH NAO SERVE, e vale registrar por que: hash muda inteiro quando
# a entrada muda um fio. Dois rostos da MESMA pessoa nunca dao os mesmos 128
# numeros — dao numeros parecidos, e reconhecer e justamente medir esse
# "parecido". Hash apaga a semelhanca junto com o resto, e nada mais reconhece.
#
# O QUE SERVE: girar os 128 numeros com uma chave secreta. Um giro no espaco de
# 128 dimensoes NAO MUDA DISTANCIA NENHUMA — e por isso o reconhecimento sai
# exatamente igual, numero por numero. Mas o banco passa a guardar os rostos num
# sistema de eixos que so a chave conhece:
#
#   * quem copiar o banco nao consegue cruzar com outro banco de rostos;
#   * quem quiser voltar a uma cara precisa dos eixos, que nao estao no banco;
#   * se vazar, troca-se a chave e os cadastros antigos viram lixo — que e a
#     unica coisa que biometria nao tem de nascenca: rosto nao se troca.
#
# O LIMITE, dito na cara: isto protege contra o BANCO vazar. Quem tiver o
# servidor inteiro tem a chave junto, e ai nao protege nada. E honesto porque e
# exatamente o mesmo limite de qualquer coisa cifrada em disco.
#
# O giro e feito por reflexoes de Householder: x -> x - 2(v.x)v, com v tirado da
# chave. Cada reflexao e exata, a composicao de varias tambem, e nao precisa de
# biblioteca de algebra nenhuma.
REFLEXOES = 8


def _chave_bio() -> str:
    """A chave do giro. Fica FORA do banco, que e o que da sentido a ela."""
    c = os.environ.get("CHAVE_BIO", "").strip()
    if c:
        return c
    # Sem chave configurada o servidor faz uma e guarda ao lado do banco. Nao e
    # o ideal — o ideal e no .env, longe do arquivo que ela protege — mas exigir
    # configuracao aqui seria o servidor nao subir na maquina do laboratorio, e
    # ai ninguem protege coisa nenhuma.
    arq = SQLITE.with_name("chave-bio.txt")
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    nova = secrets.token_hex(32)
    arq.write_text(nova, encoding="utf-8")
    try:
        os.chmod(arq, 0o600)
    except OSError:
        pass
    print(f"[bio] chave nova em {arq} — mova para CHAVE_BIO no .env", flush=True)
    return nova


def _refletores() -> list[list[float]]:
    """Os eixos do giro, deduzidos da chave. Mesma chave, mesmos eixos."""
    global _EIXOS
    if _EIXOS is not None:
        return _EIXOS
    chave = _chave_bio()
    eixos = []
    for i in range(REFLEXOES):
        bruto = b""
        j = 0
        while len(bruto) < 128 * 4:
            bruto += hashlib.sha256(f"{chave}:{i}:{j}".encode()).digest()
            j += 1
        v = [int.from_bytes(bruto[k * 4:k * 4 + 4], "big") / 2**32 - 0.5
             for k in range(128)]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        eixos.append([x / n for x in v])
    _EIXOS = eixos
    return eixos


_EIXOS: list[list[float]] | None = None


def proteger(d: list[float]) -> list[float]:
    """Gira um descritor para o sistema de eixos da chave."""
    x = list(d)
    for v in _refletores():
        s = 2.0 * sum(a * b for a, b in zip(v, x))
        x = [a - s * b for a, b in zip(x, v)]
    return x


def distancia(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b)))


# Limiar do reconhecimento. 0.5 e conservador de proposito; a literatura usa
# 0.6. O mesmo numero vive em auditix-sala.html como LIMIAR_ROSTO.
LIMIAR_ROSTO = float(os.environ.get("LIMIAR_ROSTO", "0.50"))


def carregar_env() -> None:
    """Lê um .env simples ao lado do script. Sem dependência extra para isso."""
    env = AQUI / ".env"
    if not env.exists():
        return
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


carregar_env()
URL_BANCO = os.environ.get("DATABASE_URL", "").strip()
WEBHOOK = os.environ.get("WEBHOOK_URL", "").strip()
# Segredo combinado com o outro lado. Uma URL de Lambda e publica: sem isto,
# qualquer um que a descubra dispara e-mails em nome de voces — e paga.
WEBHOOK_SEGREDO = os.environ.get("WEBHOOK_SEGREDO", "").strip()
# Quais eventos viram e-mail. "graves" e o padrao; "todos" manda tudo, inclusive
# cada pessoa que entra — util para testar, insuportavel em uso normal.
ALERTA_TIPOS = os.environ.get("ALERTA_TIPOS", "graves").strip().lower()
# Segundos de silencio por TIPO antes de mandar outro e-mail. Um alerta a cada
# poucos segundos e a forma mais rapida de a caixa de entrada virar lixo e
# ninguem mais ler nenhum.
ALERTA_ESPERA = float(os.environ.get("ALERTA_ESPERA", "60"))
_ultimo_alerta: dict[str, float] = {}

# ---------------------------------------------------------------- banco -----
# Postgres usa %s e SQLite usa ?. Em vez de espalhar if pelo código todo, o
# adaptador troca o marcador na hora de executar.

USANDO_PG = False
_pg = None

if URL_BANCO:
    try:
        import psycopg

        _pg = psycopg.connect(URL_BANCO, autocommit=False, connect_timeout=8)
        USANDO_PG = True
        print(f"[auditix] PostgreSQL conectado: {URL_BANCO.split('@')[-1]}")
    except Exception as erro:  # noqa: BLE001
        print(f"[auditix] Postgres não respondeu ({erro.__class__.__name__}: {erro}).")
        print("[auditix] Caindo para SQLite local. A demonstração continua de pé.")

if not USANDO_PG:
    print(f"[auditix] SQLite em {SQLITE}")


@contextmanager
def cursor(escrita: bool = False):
    """Um cursor, com transação, funcione onde funcionar."""
    if USANDO_PG:
        try:
            with _pg.cursor() as cur:
                yield cur, "%s"
            _pg.commit() if escrita else _pg.rollback()
        except Exception:
            _pg.rollback()
            raise
    else:
        con = sqlite3.connect(SQLITE, timeout=10, isolation_level=None)
        try:
            cur = con.cursor()
            cur.execute("BEGIN IMMEDIATE" if escrita else "BEGIN")
            yield cur, "?"
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def criar_tabelas() -> None:
    serial = "SERIAL PRIMARY KEY" if USANDO_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP" if USANDO_PG else "TEXT"
    with cursor(escrita=True) as (cur, _):
        # Mesma forma da tabela que já existe no db-fiap. CREATE IF NOT EXISTS
        # para não encostar na que você criou no pgAdmin.
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS logs_seguranca_escola (
                   id {serial},
                   timestamp {ts} DEFAULT CURRENT_TIMESTAMP,
                   aluno_id VARCHAR(50) NOT NULL,
                   tipo_evento VARCHAR(100) NOT NULL,
                   localizacao VARCHAR(100) NOT NULL,
                   hash_anterior VARCHAR(64) NOT NULL,
                   hash_atual VARCHAR(64) NOT NULL)"""
        )
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS mapa_calor (
                   id {serial},
                   momento {ts} DEFAULT CURRENT_TIMESTAMP,
                   camera VARCHAR(60) NOT NULL,
                   celula_x INTEGER NOT NULL,
                   celula_y INTEGER NOT NULL,
                   contagem INTEGER NOT NULL)"""
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_calor_camera ON mapa_calor (camera)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_logs_tipo ON logs_seguranca_escola (tipo_evento)"
        )
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS fotos_evento (
                   evento_id INTEGER PRIMARY KEY,
                   momento {ts} DEFAULT CURRENT_TIMESTAMP,
                   imagem TEXT NOT NULL)"""
        )
        # Quem olhou a imagem de quem, e quando. Sem login o servidor conhece a
        # maquina, nao a pessoa — o registro diz de onde veio a consulta, e isso
        # e o que ele pode honestamente afirmar.
        # Amostras de diagnostico. NAO tem hash e NAO entra na cadeia: sao
        # medidas do que o sistema viu, nao afirmacoes sobre o que aconteceu.
        # E por isso que esta tabela pode ser podada e a de eventos nao.
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS calibracao (
                   id {serial},
                   momento {ts} DEFAULT CURRENT_TIMESTAMP,
                   camera VARCHAR(60) NOT NULL,
                   corpo INTEGER NOT NULL,
                   fps REAL NOT NULL,
                   analisavel INTEGER NOT NULL,
                   nota REAL NOT NULL,
                   fora REAL NOT NULL,
                   geo INTEGER NOT NULL,
                   vel REAL NOT NULL,
                   ang REAL NOT NULL,
                   baixo REAL NOT NULL,
                   prop REAL NOT NULL,
                   alertou VARCHAR(20) NOT NULL,
                   ms_rede REAL NOT NULL DEFAULT 0,
                   ms_analise REAL NOT NULL DEFAULT 0,
                   heap REAL NOT NULL DEFAULT 0,
                   cpu REAL NOT NULL DEFAULT 0)"""
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_calib_momento ON calibracao (momento)"
        )
        # QUEM FOI CADASTRADO DE PROPRIO PUNHO, com os descritores de rosto.
        #
        # Isto sai do localStorage do navegador e vem para ca por um motivo
        # pratico: no navegador, o cadastro existe em UMA maquina, UM navegador
        # e some com a limpeza de cache. Numa escola, quem cadastra na secretaria
        # e quem assiste na coordenacao nao sao a mesma tela.
        #
        # NAO entra na cadeia de hash, e por isso pode ser podada — a mesma
        # razao da tabela de calibracao. A cadeia afirma o que ACONTECEU; um
        # cadastro e um consentimento, que tem prazo e pode ser retirado.
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS cadastros (
                   id {serial},
                   nome VARCHAR(80) NOT NULL,
                   descritores TEXT NOT NULL,
                   criado {ts} DEFAULT CURRENT_TIMESTAMP,
                   vence {ts},
                   ativo INTEGER NOT NULL DEFAULT 1,
                   protegido INTEGER NOT NULL DEFAULT 0)"""
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_cad_nome ON cadastros (nome)"
        )
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS acessos_foto (
                   id {serial},
                   momento {ts} DEFAULT CURRENT_TIMESTAMP,
                   evento_id INTEGER NOT NULL,
                   origem VARCHAR(60) NOT NULL,
                   agente VARCHAR(200) NOT NULL)"""
        )


def migrar_calibracao() -> None:
    """As tres colunas de custo nasceram depois da tabela, e CREATE IF NOT EXISTS
    nao mexe em tabela que ja existe. Sem isto, quem ja tinha rodado a calibracao
    antes desta versao ganharia um erro de coluna faltando na primeira amostra.

    Cada ALTER vai na sua propria transacao de proposito: no Postgres um comando
    que falha aborta a transacao inteira, entao agrupa-los faria a segunda
    coluna morrer por causa da primeira ja existir."""
    for coluna in ("ms_rede", "ms_analise", "heap", "cpu"):
        try:
            with cursor(escrita=True) as (cur, _):
                cur.execute(
                    f"ALTER TABLE calibracao ADD COLUMN {coluna} REAL NOT NULL DEFAULT 0"
                )
        except Exception:
            # Ja existe. E o caso comum, e nao e problema.
            pass



def migrar_cadastros() -> None:
    """Quem ja tinha cadastro antes do giro tem os 128 numeros crus no banco.

    Este passo gira o que ja esta la e marca a linha. E UPDATE, nunca DELETE: a
    ficha continua a mesma, so muda o sistema de eixos em que ela esta escrita.
    Rodar duas vezes nao gira duas vezes — quem ja esta marcado fica de fora."""
    try:
        with cursor(escrita=True) as (cur, _):
            cur.execute(
                "ALTER TABLE cadastros ADD COLUMN protegido INTEGER NOT NULL DEFAULT 0"
            )
    except Exception:
        pass  # ja existe, que e o caso comum

    try:
        with cursor() as (cur, m):
            cur.execute("SELECT id, descritores FROM cadastros WHERE protegido = 0")
            pendentes = cur.fetchall()
    except Exception:
        return
    if not pendentes:
        return
    for linha in pendentes:
        ident, cru = linha[0], linha[1]
        try:
            amostras = json.loads(cru)
            girados = [proteger(d) for d in amostras if len(d) == 128]
        except Exception:
            continue
        if not girados:
            continue
        with cursor(escrita=True) as (cur, m):
            cur.execute(
                f"UPDATE cadastros SET descritores = {m}, protegido = 1 WHERE id = {m}",
                (json.dumps(girados), ident),
            )
    print(f"[bio] {len(pendentes)} cadastro(s) protegido(s) com a chave", flush=True)

# ------------------------------------------------------------ cadeia --------

def hash_linha(momento: str, aluno: str, tipo: str, local: str, anterior: str) -> str:
    """
    O hash cobre os DADOS da linha mais o hash da anterior. O id fica de fora de
    propósito: ele só existe depois do INSERT, e um hash que depende de algo que
    ainda não existe não fecha.

    O separador '|' com os campos em ordem fixa é o que torna isto reproduzível:
    qualquer um com a linha na mão recalcula e confere.
    """
    cru = f"{momento}|{aluno}|{tipo}|{local}|{anterior}"
    return hashlib.sha256(cru.encode("utf-8")).hexdigest()


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat(sep=" ")


def travar(cur, marcador) -> None:
    """
    Duas gravações ao mesmo tempo podem ler a MESMA ponta da cadeia e gravar dois
    elos irmãos, o que quebra a corrente sem ninguém ter adulterado nada. O
    cadeado resolve. No SQLite o BEGIN IMMEDIATE já serializa.
    """
    if USANDO_PG:
        cur.execute("SELECT pg_advisory_xact_lock(823641)")


def ponta(cur, marcador) -> str:
    cur.execute(
        "SELECT hash_atual FROM logs_seguranca_escola ORDER BY id DESC LIMIT 1"
    )
    linha = cur.fetchone()
    return linha[0] if linha else GENESE


# ------------------------------------------------------------- modelos ------

class Evento(BaseModel):
    aluno_id: str = Field(max_length=50)
    tipo_evento: str = Field(max_length=100)
    localizacao: str = Field(max_length=100)


class Foto(BaseModel):
    evento_id: int
    imagem: str = Field(max_length=FOTO_MAX)


class Celula(BaseModel):
    x: int
    y: int
    n: int


class Calor(BaseModel):
    camera: str = Field(default="sala-12", max_length=60)
    celulas: list[Celula]


class Amostra(BaseModel):
    corpo: int
    fps: float
    analisavel: int
    nota: float
    fora: float
    geo: int
    vel: float
    ang: float
    baixo: float
    prop: float
    alertou: str = Field(default="", max_length=20)
    # O custo de rodar o modelo, em milissegundos por quadro. Com default zero
    # porque uma pagina antiga nao manda estes campos, e uma amostra sem medida
    # de custo continua valendo pela margem — que e o motivo original da tabela.
    ms_rede: float = 0.0
    ms_analise: float = 0.0
    # A memoria que o processo de analise ocupa, em MB. No navegador e o monte
    # do JavaScript, que e o mais perto que ele deixa chegar; na AIBOX e a
    # memoria residente do processo, que e a coisa de verdade. As duas
    # respondem a mesma pergunta util: isto cresce sem parar ao longo da aula?
    heap: float = 0.0
    # Uso de CPU em porcento. Fica ZERO no navegador, e de proposito: pagina
    # nenhuma consegue ler isso, e um numero inventado seria pior que nenhum.
    # A AIBOX consegue, e e la que ele vale.
    cpu: float = 0.0


class Cadastro(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    # Lista de amostras; cada amostra e um descritor de 128 numeros. Varias
    # amostras existem porque um rosto visto de dois angulos da dois pontos
    # diferentes, e comparar contra o mais proximo erra menos que contra a media.
    descritores: list[list[float]]


class Remocao(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


class Rosto(BaseModel):
    # Um rosto visto AGORA, para o servidor dizer de quem e. Chega cru, e girado
    # aqui dentro, comparado girado-contra-girado e descartado no fim da
    # requisicao. Nao e gravado em lugar nenhum.
    descritor: list[float]


class Calibracao(BaseModel):
    camera: str = Field(default="sala-12", max_length=60)
    amostras: list[Amostra]


@asynccontextmanager
async def ciclo(_app: FastAPI):
    criar_tabelas()
    migrar_calibracao()
    migrar_cadastros()
    podar_calibracao()
    podar_cadastros()
    yield


app = FastAPI(title="Auditix, sala auditada", lifespan=ciclo)


@app.get("/")
def pagina() -> FileResponse:
    if not PAGINA.exists():
        raise HTTPException(404, f"não achei {PAGINA.name} ao lado do servidor")
    # no-store porque a página muda o tempo todo enquanto se mexe nela. Sem isso
    # o Chrome serve a versão velha e some com a correção que acabou de ser feita,
    # o que já custou uma sessão inteira de depuração do bug errado.
    return FileResponse(PAGINA, headers={"Cache-Control": "no-store, must-revalidate"})


class QuadroAmostra(BaseModel):
    corpo: int
    t: float
    qx: float; qy: float
    ang: float; altura: float; eixo: float; ombro: float; prop: float
    pxx: float; pxy: float; pdx: float; pdy: float


class Amostra(BaseModel):
    """Uma gravacao rotulada da camera desta sala.

    Guarda a geometria do esqueleto, ja normalizada, e NADA de imagem: sem
    quadro, sem rosto, sem nome. O arquivo fica fora do git — sao dados da casa
    de alguem, com outras pessoas dentro."""
    rotulo: str = Field(max_length=40)
    sessao: int
    fps: int = 30
    quadros: list[QuadroAmostra] = Field(max_length=200000)


AMOSTRAS = AQUI / "treino" / "local" / "amostras.jsonl"


@app.post("/api/amostras")
def gravar_amostra(a: Amostra) -> dict:
    AMOSTRAS.parent.mkdir(parents=True, exist_ok=True)
    with AMOSTRAS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"rotulo": a.rotulo, "sessao": a.sessao, "fps": a.fps,
                            "gravada": agora_iso(),
                            "quadros": [q.model_dump() for q in a.quadros]},
                           ensure_ascii=False) + "\n")
    with AMOSTRAS.open(encoding="utf-8") as f:
        total = sum(1 for _ in f)
    return {"ok": True, "quadros": len(a.quadros), "total": total}


@app.get("/cadastro")
def pagina_cadastro() -> FileResponse:
    """A plataforma de cadastro de rostos.

    Pagina propria, e nao um canto da Sala, porque as duas coisas sao feitas por
    pessoas diferentes em momentos diferentes: quem cadastra faz isso uma vez,
    na secretaria; quem assiste a sala fica olhando o dia todo."""
    alvo = AQUI / "auditix-cadastro.html"
    if not alvo.exists():
        raise HTTPException(404, "nao achei auditix-cadastro.html")
    return FileResponse(alvo, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/vendor/{caminho:path}")
def estatico(caminho: str) -> FileResponse:
    """Serve os modelos locais. So de dentro de vendor/, e so arquivo que existe."""
    alvo = (ESTATICOS / caminho).resolve()
    # Sem isto, um caminho com .. sairia da pasta e serviria qualquer arquivo da
    # maquina. O navegador nunca faria isso; quem faria e quem quer ler o disco.
    if not alvo.is_file() or ESTATICOS.resolve() not in alvo.parents:
        raise HTTPException(404, "não encontrado")
    tipo = TIPOS.get(alvo.suffix.lower())
    if tipo is None:
        raise HTTPException(404, "tipo de arquivo não servido daqui")
    # Sao arquivos que so mudam quando a gente troca a versao da biblioteca.
    return FileResponse(alvo, media_type=tipo,
                        headers={"Cache-Control": "public, max-age=604800"})


@app.post("/api/evento")
def gravar_evento(ev: Evento) -> dict:
    momento = agora_iso()
    with cursor(escrita=True) as (cur, m):
        travar(cur, m)
        anterior = ponta(cur, m)
        atual = hash_linha(momento, ev.aluno_id, ev.tipo_evento, ev.localizacao, anterior)
        cur.execute(
            f"""INSERT INTO logs_seguranca_escola
                (timestamp, aluno_id, tipo_evento, localizacao, hash_anterior, hash_atual)
                VALUES ({m}, {m}, {m}, {m}, {m}, {m})"""
            + (" RETURNING id" if USANDO_PG else ""),
            (momento, ev.aluno_id, ev.tipo_evento, ev.localizacao, anterior, atual),
        )
        novo_id = cur.fetchone()[0] if USANDO_PG else cur.lastrowid

    if WEBHOOK and deve_alertar(ev.tipo_evento):
        disparar_webhook(novo_id, momento, ev, atual)

    return {"id": novo_id, "timestamp": momento, "hash_anterior": anterior,
            "hash_atual": atual, "banco": "postgres" if USANDO_PG else "sqlite"}


def deve_alertar(tipo: str) -> bool:
    """Vale a pena acordar alguem por este evento, agora?"""
    if ALERTA_TIPOS == "todos":
        pass
    elif tipo not in GRAVES:
        return False
    agora = time.monotonic()
    ultimo = _ultimo_alerta.get(tipo)
    if ultimo is not None and agora - ultimo < ALERTA_ESPERA:
        return False
    _ultimo_alerta[tipo] = agora
    return True


def disparar_webhook(novo_id, momento, ev: Evento, hash_atual: str) -> None:
    """Alerta. Se o webhook cair, o evento JÁ está gravado: o registro nunca
    depende da notificação ter dado certo. Síncrono de propósito: o endpoint
    inteiro roda no threadpool do FastAPI (é `def`, não `async def`), então
    não há event loop aqui para um cliente assíncrono usar."""
    import httpx

    corpo = {"id": novo_id, "timestamp": momento, "aluno_id": ev.aluno_id,
             "tipo_evento": ev.tipo_evento, "localizacao": ev.localizacao,
             "hash_atual": hash_atual,
             "texto": f"{ev.tipo_evento} em {ev.localizacao}, pendente de validação humana"}
    cabecalhos = {"X-Auditix-Segredo": WEBHOOK_SEGREDO} if WEBHOOK_SEGREDO else {}
    try:
        with httpx.Client(timeout=5) as cli:
            r = cli.post(WEBHOOK, json=corpo, headers=cabecalhos)
        # Uma resposta 403 ou 500 nao levanta excecao: sem esta conferencia a
        # recusa passaria calada e a tela nao daria pista nenhuma de por que o
        # e-mail nao chegou.
        if r.status_code >= 400:
            print(f"[auditix] webhook recusou ({r.status_code}): {r.text[:200]}")
    except Exception as erro:  # noqa: BLE001
        print(f"[auditix] webhook falhou, evento gravado mesmo assim: {erro}")


@app.get("/api/verificar")
def verificar() -> dict:
    """
    Recalcula a cadeia inteira desde a gênese.

    O detalhe que faz isto valer: a linha seguinte é conferida contra o hash
    RECALCULADO, não contra o que está gravado. Sem isso, adulterar uma linha
    acenderia só ela, e o resto da cadeia continuaria parecendo válido. Com isso,
    a quebra se propaga e o ponto exato aparece.
    """
    with cursor() as (cur, m):
        cur.execute(
            """SELECT id, timestamp, aluno_id, tipo_evento, localizacao,
                      hash_anterior, hash_atual
               FROM logs_seguranca_escola ORDER BY id"""
        )
        linhas = cur.fetchall()

    anterior_real = GENESE
    quebrou_em, motivo = None, None
    for (id_, ts, aluno, tipo, local, h_ant, h_at) in linhas:
        momento = ts if isinstance(ts, str) else ts.isoformat(sep=" ")
        recalculado = hash_linha(momento, aluno, tipo, local, anterior_real)
        if quebrou_em is None:
            if h_ant != anterior_real:
                quebrou_em, motivo = id_, "o elo com a linha anterior não bate"
            elif recalculado != h_at:
                quebrou_em, motivo = id_, "o conteúdo da linha foi alterado"
        anterior_real = recalculado

    return {"integra": quebrou_em is None, "total": len(linhas),
            "quebrou_em": quebrou_em, "motivo": motivo,
            "banco": "postgres" if USANDO_PG else "sqlite"}


def filtro_tipos(m: str) -> tuple[str, tuple]:
    """Cláusula WHERE do filtro do painel, ou nada quando ele está vazio."""
    if not TIPOS_PAINEL:
        return "", ()
    tipos = sorted(TIPOS_PAINEL)
    return f"WHERE tipo_evento IN ({', '.join([m] * len(tipos))})", tuple(tipos)


@app.get("/api/eventos")
def listar(limite: int = 50) -> list[dict]:
    with cursor() as (cur, m):
        # O filtro vai no WHERE, nao depois: filtrar em Python devolveria menos
        # linhas do que o limite pedido sempre que houvesse evento escondido.
        onde, vals = filtro_tipos(m)
        cur.execute(
            f"""SELECT id, timestamp, aluno_id, tipo_evento, localizacao, hash_atual
                FROM logs_seguranca_escola {onde} ORDER BY id DESC LIMIT {m}""",
            (*vals, max(1, min(limite, 500))),
        )
        linhas = cur.fetchall()
        # Quais destes têm imagem guardada — o painel precisa saber para mostrar
        # o botão só onde ele funciona.
        ids = [r[0] for r in linhas]
        com_foto: set[int] = set()
        if ids:
            cur.execute(
                f"""SELECT evento_id FROM fotos_evento
                    WHERE evento_id IN ({', '.join([m] * len(ids))})""",
                tuple(ids),
            )
            com_foto = {r[0] for r in cur.fetchall()}
        return [
            {"id": r[0], "timestamp": str(r[1]), "aluno_id": r[2],
             "tipo_evento": r[3], "localizacao": r[4], "hash_atual": r[5],
             "tem_foto": r[0] in com_foto}
            for r in linhas
        ]


def limpar_fotos() -> int:
    """Apaga as imagens vencidas. A comparacao sai em Python porque TIMESTAMP no
    Postgres e TEXT no SQLite nao se comparam com a mesma sintaxe, e uma consulta
    que so roda num dos dois falharia justamente no fallback."""
    if FOTO_DIAS <= 0:
        return 0
    corte = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=FOTO_DIAS)
    with cursor(escrita=True) as (cur, m):
        cur.execute("SELECT evento_id, momento FROM fotos_evento")
        velhas = []
        for eid, mom in cur.fetchall():
            q = mom if not isinstance(mom, str) else _ler_momento(mom)
            if q is None or q < corte:
                velhas.append(eid)
        for eid in velhas:
            cur.execute(f"DELETE FROM fotos_evento WHERE evento_id = {m}", (eid,))
    return len(velhas)


@app.post("/api/foto")
def guardar_foto(f: Foto) -> dict:
    """A imagem do instante do alerta. So entra se o evento existir E for grave:
    sem esta conferencia o endpoint viraria um album de qualquer quadro que
    alguem quisesse mandar, que e exatamente o que este projeto nao faz."""
    if not FOTOS:
        raise HTTPException(403, "guarda de imagem desligada (FOTOS=0)")
    if not f.imagem.startswith("data:image/jpeg;base64,"):
        raise HTTPException(400, "só JPEG em data URL")
    with cursor(escrita=True) as (cur, m):
        cur.execute(
            f"SELECT tipo_evento FROM logs_seguranca_escola WHERE id = {m}",
            (f.evento_id,),
        )
        linha = cur.fetchone()
        if not linha:
            raise HTTPException(404, "evento não existe")
        if linha[0] not in GRAVES:
            raise HTTPException(403, f"'{linha[0]}' não é evento grave")
        if linha[0] in SEM_FOTO:
            raise HTTPException(403, f"'{linha[0]}' não guarda imagem, por decisão")
        cur.execute(f"DELETE FROM fotos_evento WHERE evento_id = {m}", (f.evento_id,))
        cur.execute(
            f"INSERT INTO fotos_evento (evento_id, momento, imagem) VALUES ({m}, {m}, {m})",
            (f.evento_id, agora_iso(), f.imagem),
        )
    limpar_fotos()
    return {"guardada": f.evento_id, "apaga_em_dias": FOTO_DIAS}


@app.get("/api/foto/{evento_id}")
def ler_foto(evento_id: int, req: Request) -> dict:
    """Devolve a imagem E registra a consulta. Ver quem caiu e um ato que deixa
    rastro: sem isso, 'acesso registrado' seria so uma frase bonita na tela."""
    limpar_fotos()
    with cursor(escrita=True) as (cur, m):
        cur.execute(f"SELECT imagem, momento FROM fotos_evento WHERE evento_id = {m}",
                    (evento_id,))
        linha = cur.fetchone()
        if not linha:
            raise HTTPException(404, "sem imagem para este evento (ou já venceu)")
        cur.execute(
            f"""INSERT INTO acessos_foto (momento, evento_id, origem, agente)
                VALUES ({m}, {m}, {m}, {m})""",
            (agora_iso(), evento_id,
             (req.client.host if req.client else "?")[:60],
             req.headers.get("user-agent", "?")[:200]),
        )
        cur.execute(f"SELECT COUNT(*) FROM acessos_foto WHERE evento_id = {m}",
                    (evento_id,))
        vistas = cur.fetchone()[0]
    return {"evento_id": evento_id, "imagem": linha[0],
            "momento": str(linha[1]), "consultas": vistas,
            "apaga_em_dias": FOTO_DIAS}


@app.get("/api/pessoas")
def pessoas() -> dict:
    """Quem foi reconhecido, quando pela ultima vez e ha quanto tempo sumiu.

    So aparece aqui quem foi cadastrado na Portaria, de proprio punho. Nao ha
    descoberta de gente nova: o painel conta o que ja foi consentido."""
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT aluno_id, timestamp, localizacao FROM logs_seguranca_escola
                WHERE tipo_evento = {m} ORDER BY id""",
            ("reconhecido",),
        )
        linhas = cur.fetchall()

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    quem: dict[str, dict] = {}
    for nome, ts, local in linhas:
        # "corpo-3" e o anonimo que a Sala mandava antes de o nome vir junto.
        # Nao e pessoa: e o numero de uma trilha que morreu no fim daquele dia.
        if not nome or nome.startswith("corpo-"):
            continue
        momento = ts if not isinstance(ts, str) else _ler_momento(ts)
        if momento is None:
            continue
        a = quem.setdefault(nome, {"nome": nome, "vezes": 0,
                                   "ultima": None, "onde": None})
        a["vezes"] += 1
        if a["ultima"] is None or momento > a["ultima"]:
            a["ultima"] = momento
            a["onde"] = local

    saida = []
    for a in quem.values():
        horas = (agora - a["ultima"]).total_seconds() / 3600
        saida.append({"nome": a["nome"], "vezes": a["vezes"],
                      "onde": a["onde"], "ultima": a["ultima"].isoformat(sep=" "),
                      "horas": round(horas, 1), "dias": int(horas // 24)})
    saida.sort(key=lambda x: x["horas"])
    return {"pessoas": saida, "total": len(saida)}


@app.post("/api/calor")
def gravar_calor(c: Calor) -> dict:
    """O navegador manda a grade agregada, não posições de pessoa a pessoa. São
    contagens por célula: dá para ver onde a sala aperta sem saber quem passou."""
    with cursor(escrita=True) as (cur, m):
        for cel in c.celulas:
            if cel.n <= 0:
                continue
            cur.execute(
                f"""INSERT INTO mapa_calor (momento, camera, celula_x, celula_y, contagem)
                    VALUES ({m}, {m}, {m}, {m}, {m})""",
                (agora_iso(), c.camera, cel.x, cel.y, cel.n),
            )
    return {"gravadas": len(c.celulas)}


def podar_calibracao() -> None:
    """Amostra velha nao serve para nada e cresce para sempre. Podar aqui e
    seguro exatamente porque esta tabela NAO participa da cadeia de hash — a de
    eventos nunca perde linha, e a diferenca e proposital."""
    if CALIBRACAO_DIAS <= 0:
        return
    corte = (datetime.now(timezone.utc)
             - timedelta(days=CALIBRACAO_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    with cursor(escrita=True) as (cur, m):
        cur.execute(f"DELETE FROM calibracao WHERE momento < {m}", (corte,))


def podar_cadastros() -> None:
    """Cadastro vencido some. O consentimento tinha prazo, e prazo que nao e
    cumprido sozinho nao e prazo — e promessa. Como esta tabela NAO participa da
    cadeia de hash, apagar aqui e seguro: a de eventos e que nunca perde linha."""
    if CADASTRO_DIAS <= 0:
        return
    corte = (datetime.now(timezone.utc)
             - timedelta(days=CADASTRO_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    with cursor(escrita=True) as (cur, m):
        cur.execute(f"DELETE FROM cadastros WHERE criado < {m}", (corte,))


@app.post("/api/cadastro")
def gravar_cadastro(c: Cadastro) -> dict:
    """Um rosto cadastrado de proprio punho, com os descritores medidos no
    navegador durante a prova de vida."""
    if not c.descritores:
        raise HTTPException(400, "nenhuma amostra de rosto")
    if len(c.descritores) > CADASTRO_MAX:
        raise HTTPException(413, f"acima de {CADASTRO_MAX} amostras")
    # O TAMANHO E COBRADO. Um descritor de tamanho errado nao da erro na hora de
    # comparar: da uma distancia qualquer, e a pessoa simplesmente nunca e
    # reconhecida — falha silenciosa, que e a pior de diagnosticar.
    for d in c.descritores:
        if len(d) != 128:
            raise HTTPException(400,
                                f"descritor com {len(d)} numeros; o esperado e 128")
    nome = c.nome.strip()
    agora = agora_iso()
    vence = (datetime.now(timezone.utc)
             + timedelta(days=CADASTRO_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    with cursor(escrita=True) as (cur, m):
        # Recadastrar o mesmo nome SUBSTITUI. Sem isto, uma pessoa que refaz o
        # cadastro por ter mudado o cabelo passaria a ter duas fichas, e a
        # antiga continuaria valendo — com o rosto que ela nao tem mais.
        cur.execute(f"UPDATE cadastros SET ativo = 0 WHERE nome = {m}", (nome,))
        cur.execute(
            f"""INSERT INTO cadastros (nome, descritores, criado, vence, ativo,
                                      protegido)
                VALUES ({m}, {m}, {m}, {m}, 1, 1)""",
            # GIRADOS ANTES DE ENCOSTAR NO DISCO. O descritor cru existe na
            # memoria desta requisicao e acaba com ela; o que fica gravado esta
            # no sistema de eixos da chave, que nao mora no banco.
            (nome, json.dumps([proteger(d) for d in c.descritores]), agora, vence),
        )
    return {"nome": nome, "amostras": len(c.descritores), "vence": vence}


@app.get("/api/cadastros")
def listar_cadastros(descritores: int = 0) -> dict:
    """A lista de quem esta cadastrado.

    Os DESCRITORES SO SAEM SE PEDIDOS, e isso nao e burocracia: eles sao o dado
    biometrico. Quem quer montar a tela de gerenciamento precisa de nomes e
    prazos; so quem vai RECONHECER precisa dos numeros do rosto."""
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT nome, descritores, criado, vence FROM cadastros
                WHERE ativo = 1 ORDER BY nome"""
        )
        linhas = cur.fetchall()
    saida = []
    for nome, desc, criado, vence in linhas:
        try:
            amostras = json.loads(desc)
        except Exception:
            amostras = []
        ficha = {"nome": nome, "amostras": len(amostras),
                 "criado": str(criado)[:19], "vence": str(vence)[:19]}
        if descritores:
            # GIRADOS. Sao 128 numeros num sistema de eixos que so a chave
            # conhece: servem para conferir formato e quantidade, e nao servem
            # para cruzar com outro banco de rostos.
            ficha["descritores"] = amostras
        saida.append(ficha)
    return {"cadastros": saida, "total": len(saida),
            "prazo_dias": CADASTRO_DIAS, "protegidos": True}


@app.post("/api/reconhecer")
def reconhecer(r: Rosto) -> dict:
    """De quem e este rosto? Responde um nome, ou nenhum.

    A COMPARACAO ACONTECE AQUI, e nao no navegador, por um motivo so: assim a
    chave do giro nunca sai do servidor. Se o navegador comparasse, ele
    precisaria dos descritores guardados e da chave para girar o rosto de agora
    — e ai bastaria abrir o console da pagina para levar o banco inteiro.

    O que sobe e um rosto avulso de quem esta na frente da camera neste
    instante. O que desce e um nome. A imagem nao passa por aqui em nenhum
    momento, e o descritor recebido morre com a requisicao."""
    if len(r.descritor) != 128:
        raise HTTPException(400,
                            f"descritor com {len(r.descritor)} numeros; "
                            "o esperado e 128")
    alvo = proteger(r.descritor)
    with cursor() as (cur, m):
        cur.execute("SELECT nome, descritores FROM cadastros WHERE ativo = 1")
        linhas = cur.fetchall()

    melhor, perto = None, float("inf")
    for nome, desc in linhas:
        try:
            amostras = json.loads(desc)
        except Exception:
            continue
        # A MENOR distancia entre as amostras da pessoa, nao a media. Um rosto
        # cadastrado de frente, de lado e olhando para baixo da tres pontos
        # diferentes; a media deles nao e cara de ninguem.
        for d in amostras:
            if len(d) != 128:
                continue
            v = distancia(alvo, d)
            if v < perto:
                perto, melhor = v, nome

    if melhor is None or perto >= LIMIAR_ROSTO:
        # A DISTANCIA EXATA DE QUEM NAO FOI RECONHECIDO E UM ORACULO. Com ela,
        # quem estiver na rede manda um rosto qualquer, le o quanto errou,
        # corrige, manda de novo — e em algumas milhares de tentativas chega a
        # um descritor que casa com alguem cadastrado, sem nunca ter visto a
        # cara dessa pessoa. E ataque conhecido contra API de comparacao facial.
        #
        # Com CALIBRACAO=1 ela sai inteira, porque ai o numero serve para
        # escolher o limiar olhando dado. Fora disso sai arredondada: da para
        # ver que passou longe, nao da para subir a ladeira.
        bruta = None if melhor is None else round(perto, 4)
        return {"nome": None,
                "distancia": bruta if CALIBRACAO else (
                    None if bruta is None else round(bruta, 1)),
                "limiar": LIMIAR_ROSTO, "cadastrados": len(linhas)}
    return {"nome": melhor, "distancia": round(perto, 4),
            "limiar": LIMIAR_ROSTO, "cadastrados": len(linhas)}


@app.post("/api/cadastro/remover")
def remover_cadastro(r: Remocao) -> dict:
    """Retirar o consentimento. A linha NAO e apagada, e vira inativa: apagar
    esconderia que a pessoa chegou a ser cadastrada, e e justamente isso que
    alguem auditando precisa poder ver. Quem apaga de vez e o prazo."""
    with cursor(escrita=True) as (cur, m):
        cur.execute(f"UPDATE cadastros SET ativo = 0 WHERE nome = {m} AND ativo = 1",
                    (r.nome.strip(),))
        n = cur.rowcount
    if not n:
        raise HTTPException(404, f"ninguem cadastrado com o nome {r.nome!r}")
    return {"removidos": n, "nome": r.nome.strip()}


@app.post("/api/calibracao")
def gravar_calibracao(c: Calibracao) -> dict:
    """As amostras do que o sistema viu. Numeros do esqueleto ja normalizados:
    nenhuma imagem, nenhum rosto, nenhum nome — a mesma regra do treino."""
    if not CALIBRACAO:
        raise HTTPException(403, "registro de calibração desligado (CALIBRACAO=0)")
    if len(c.amostras) > CALIBRACAO_LOTE:
        raise HTTPException(413, f"lote acima de {CALIBRACAO_LOTE} amostras")
    agora = agora_iso()
    with cursor(escrita=True) as (cur, m):
        for a in c.amostras:
            cur.execute(
                f"""INSERT INTO calibracao (momento, camera, corpo, fps, analisavel,
                       nota, fora, geo, vel, ang, baixo, prop, alertou,
                       ms_rede, ms_analise, heap, cpu)
                    VALUES ({m}, {m}, {m}, {m}, {m}, {m}, {m}, {m}, {m}, {m},
                            {m}, {m}, {m}, {m}, {m}, {m}, {m})""",
                (agora, c.camera, a.corpo, a.fps, a.analisavel, a.nota, a.fora,
                 a.geo, a.vel, a.ang, a.baixo, a.prop,
                 # Sem virgula e sem quebra de linha: este campo e o unico que
                 # chega de fora como texto e sai direto numa planilha CSV.
                 # Uma virgula aqui desalinharia todas as colunas seguintes.
                 a.alertou.replace(",", " ").replace("\n", " ")[:20],
                 a.ms_rede, a.ms_analise, a.heap, a.cpu),
            )
    return {"gravadas": len(c.amostras)}


def _ler_margem(folga_nota: float, folga_vel: float) -> str:
    """Uma frase em portugues no lugar de dois numeros soltos. Quem vai ler isto
    e alguem decidindo se pode instalar numa escola, nao quem escreveu o
    codigo."""
    apertados = []
    if folga_nota < 0:
        apertados.append("a nota de queda PASSOU do limiar sem alertar")
    elif folga_nota < 0.10:
        apertados.append(f"a nota de queda chegou a {folga_nota:.2f} do limiar")
    if folga_vel < 0:
        apertados.append("a velocidade PASSOU do limiar sem alertar")
    elif folga_vel < 0.20:
        apertados.append(f"a velocidade chegou a {folga_vel:.2f} do limiar")
    if not apertados:
        return "folga confortável nos dois limiares neste período"
    return ("; ".join(apertados) +
            " — vale abrir o CSV e olhar essas janelas antes de instalar")


def _pct(vals: list, p: float) -> float:
    """Percentil pela ordenacao, sem numpy. Mediana e p95 dizem mais que media
    sobre latencia: a media esconde a travada de 5% dos quadros, e e justamente
    a travada que faz a demonstracao parecer ruim."""
    if not vals:
        return 0.0
    v = sorted(vals)
    i = min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))
    return float(v[i])


def _ler_custo(soma_p95: float, orcamento: float, fps: float) -> str:
    """O professor pediu CPU, RAM, FPS e latencia. Tres desses o navegador conta
    honestamente; CPU do sistema ele NAO ve, e inventar um numero seria pior que
    nao ter. O que esta linha entrega no lugar e a medida que responde a mesma
    pergunta: de cada quadro, quanto ja esta gasto so com o modelo."""
    if orcamento <= 0 or soma_p95 <= 0:
        return "sem medida de custo neste período (página antiga ou nenhuma amostra)"
    uso = soma_p95 * 100 / orcamento
    sobra = max(0.0, orcamento - soma_p95)
    frase = (f"a {fps:.0f} quadros por segundo cada quadro tem {orcamento:.0f} ms; "
             f"o modelo leva até {soma_p95:.0f} ms deles ({uso:.0f}%), "
             f"sobrando {sobra:.0f} ms para captura, desenho e o resto")
    if uso >= 90:
        return frase + " — está no limite: baixar a resolução ou a taxa antes de instalar"
    if uso >= 70:
        return frase + " — aperta, mas roda; sem folga para uma segunda câmera"
    return frase


def _linhas_calibracao(camera: str) -> list:
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT momento, corpo, fps, analisavel, nota, fora, geo, vel,
                       ang, baixo, prop, alertou, ms_rede, ms_analise, heap, cpu
                FROM calibracao WHERE camera = {m} ORDER BY id""",
            (camera,),
        )
        return cur.fetchall()


@app.get("/api/calibracao")
def resumo_calibracao(camera: str = "sala-12") -> dict:
    """A pergunta que este resumo responde NAO e "quantos alertas houve".
    E "o quao perto o sistema chegou de acusar sem motivo".

    Num dia comum de aula, a maior nota que NAO virou alerta e a margem real de
    seguranca. Se o limiar e 0,50 e a maior nota do dia foi 0,31, ha folga. Se
    foi 0,49, o sistema esta a um quadro ruim de um alarme falso — e isso nao
    aparece em lugar nenhum se a gente so registrar o que disparou."""
    linhas = _linhas_calibracao(camera)
    if not linhas:
        return {"status": "sem_amostras", "ligado": CALIBRACAO, "camera": camera}

    total = len(linhas)
    cegas = sum(1 for l in linhas if not l[3])
    fora = sum(1 for l in linhas if float(l[5]) > 6)
    alertas: dict[str, int] = {}
    for l in linhas:
        if l[11]:
            alertas[l[11]] = alertas.get(l[11], 0) + 1

    # So as amostras em que NADA foi acusado: e nelas que mora o falso positivo
    # que ainda nao aconteceu.
    calmas = [l for l in linhas if not l[11] and l[3]]
    pico_nota = max((float(l[4]) for l in calmas), default=0.0)
    pico_vel = max((float(l[7]) for l in calmas), default=0.0)
    geo_calma = sum(1 for l in calmas if l[6])

    faixas = {f"{i/10:.1f}-{(i+1)/10:.1f}": 0 for i in range(10)}
    for l in calmas:
        i = min(9, max(0, int(float(l[4]) * 10)))
        faixas[f"{i/10:.1f}-{(i+1)/10:.1f}"] += 1

    fps = [float(l[2]) for l in linhas if float(l[2]) > 0]
    fps_medio = round(sum(fps) / len(fps), 1) if fps else 0

    # ---- quanto custa manter isto ligado -----------------------------------
    # Amostra vinda de pagina antiga chega com zero nos tres campos; incluir
    # esses zeros puxaria a mediana para baixo e daria um custo mentirosamente
    # bom, entao elas ficam de fora da conta em vez de virarem media.
    medidas = [l for l in linhas if float(l[12]) > 0]
    rede = [float(l[12]) for l in medidas]
    anal = [float(l[13]) for l in medidas]
    soma = [float(l[12]) + float(l[13]) for l in medidas]
    heap = [float(l[14]) for l in medidas if float(l[14]) > 0]
    # Zero aqui quer dizer "nao foi medido" (navegador), e nao "a maquina estava
    # ociosa". Incluir esses zeros daria um uso de CPU mentirosamente baixo.
    cpu = [float(l[15]) for l in medidas if float(l[15]) > 0]
    orcamento = round(1000 / fps_medio, 1) if fps_medio else 0
    soma_p95 = round(_pct(soma, 0.95), 1)

    return {
        "status": "ok",
        "ligado": CALIBRACAO,
        "camera": camera,
        "amostras": total,
        # Uma amostra por corpo por segundo, entao isto e tempo de OBSERVACAO
        # somado por pessoa, e nao tempo de relogio.
        "corpos_minuto": round(total / 60, 1),
        "primeira": str(linhas[0][0]),
        "ultima": str(linhas[-1][0]),
        "fps_medio": fps_medio,
        # ISTO E O "ANTES E DEPOIS DE LIGAR O MODELO", e nao precisa de duas
        # medicoes: sem o modelo estes dois numeros valeriam zero, porque sao o
        # tempo gasto DENTRO dele e dentro da nossa analise. O custo de ligar e
        # exatamente a soma.
        #
        # ocupacao_pct nao e "uso de CPU". E quanto do orcamento de um quadro ja
        # esta comprometido com essas duas etapas. O que sobra ainda paga
        # decodificar o video e desenhar na tela, entao 60% aqui nao quer dizer
        # 40% de maquina livre.
        "custo": {
            "amostras_com_medida": len(medidas),
            "ms_rede_mediana": round(_pct(rede, 0.5), 1),
            "ms_rede_p95": round(_pct(rede, 0.95), 1),
            "ms_analise_mediana": round(_pct(anal, 0.5), 1),
            "ms_analise_p95": round(_pct(anal, 0.95), 1),
            "ms_total_mediana": round(_pct(soma, 0.5), 1),
            "ms_total_p95": soma_p95,
            "orcamento_do_quadro_ms": orcamento,
            "ocupacao_pct": round(soma_p95 * 100 / orcamento, 1) if orcamento else 0,
            # Memoria do JavaScript, que nao e a memoria do processo: nao conta
            # o que a GPU segura nem o proprio navegador. Serve para ver se
            # cresce sem parar ao longo da aula, que e a pergunta util aqui.
            "memoria_mb_mediana": round(_pct(heap, 0.5), 1),
            "memoria_mb_maximo": round(max(heap), 1) if heap else 0,
            # So a AIBOX preenche isto. Ver o comentario no modelo Amostra.
            "cpu_pct_mediana": round(_pct(cpu, 0.5), 1),
            "cpu_pct_p95": round(_pct(cpu, 0.95), 1),
            "cpu_medido": len(cpu),
            "leitura": _ler_custo(soma_p95, orcamento, fps_medio),
        },
        # Quanto do tempo o sistema NAO teve como julgar. E a nota da posicao da
        # camera, e nao do modelo: corpo cortado no quadro nao se analisa.
        "cegas_pct": round(cegas * 100 / total, 1),
        "fora_do_treino_pct": round(fora * 100 / total, 1),
        "alertas": alertas,
        # A FOLGA e o numero que este resumo existe para dar, e ele vem pronto
        # de proposito: quem le nao deveria precisar comparar dois campos de
        # cabeca para descobrir se o dia foi tranquilo ou por um fio.
        #
        # Positivo e a distancia que sobrou ate o limiar. NEGATIVO significa que
        # alguma janela PASSOU do limiar sem virar alerta — o que nao e
        # necessariamente erro (a permanencia e a trava de "em pe" ainda
        # decidem depois), mas e sempre coisa para ir olhar: ou as travas
        # seguintes salvaram, ou o sistema esta deixando passar.
        "margem": {
            "amostras_calmas": len(calmas),
            "maior_nota_sem_alerta": round(pico_nota, 3),
            "limiar_nota": 0.50,
            "folga_nota": round(0.50 - pico_nota, 3),
            "maior_velocidade_sem_alerta": round(pico_vel, 2),
            "limiar_velocidade": 1.20,
            "folga_velocidade": round(1.20 - pico_vel, 2),
            "leitura": _ler_margem(0.50 - pico_nota, 1.20 - pico_vel),
            "geometria_sem_alerta": geo_calma,
        },
        "faixas_de_nota": faixas,
    }


@app.get("/api/calibracao.csv")
def csv_calibracao(camera: str = "sala-12") -> Response:
    """Para abrir no Excel e olhar com os proprios olhos. Um resumo e a leitura
    de alguem; a planilha deixa voce discordar dela."""
    cabecalho = ("momento,corpo,fps,analisavel,nota,fora,geo,vel,ang,baixo,"
                 "prop,alertou,ms_rede,ms_analise,heap,cpu")
    linhas = [cabecalho]
    for l in _linhas_calibracao(camera):
        linhas.append(",".join(str(x) for x in l))
    return Response("\n".join(linhas) + "\n", media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="calibracao-{camera}.csv"'})


@app.get("/api/mapa")
def mapa(camera: str = "sala-12", dias: int = 0) -> dict:
    """dias=0 e a base inteira. Uma janela importa mais do que parece aqui: a
    grade soma para sempre, e um mes de transito afoga a aula de hoje — a sala
    inteira acaba do mesmo tom e o mapa para de responder onde alguem ficou."""
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT celula_x, celula_y, contagem, momento FROM mapa_calor
                WHERE camera = {m}""",
            (camera,),
        )
        linhas = cur.fetchall()

    corte = None
    if dias > 0:
        corte = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)

    soma: dict[tuple[int, int], int] = {}
    for x, y, n, mom in linhas:
        if corte is not None:
            q = mom if not isinstance(mom, str) else _ler_momento(mom)
            if q is None or q < corte:
                continue
        soma[(x, y)] = soma.get((x, y), 0) + int(n)

    celulas = _suavizar(soma)
    valores = sorted(c["z"] for c in celulas)
    return {"camera": camera, "dias": dias, "celulas": celulas,
            "total": sum(c["n"] for c in celulas),
            "pico": max((c["n"] for c in celulas), default=0),
            # Os cortes saem daqui porque so o servidor ve a distribuicao toda.
            # Escala linear sobre o pico nao serve: numa sala real a cauda e
            # longa e 95% das celulas caem no mesmo tom — o mapa vira um borrao.
            "cortes": _cortes_escala(valores)}


def _suavizar(soma: dict[tuple[int, int], int]) -> list[dict]:
    """Media 3x3 com peso no centro. Uma celula sozinha e ruido: a pessoa nao
    fica num quadradinho, ela ocupa uma regiao, e a grade so amostra isso. Sem
    suavizar, o mapa vira confete e some justamente a pergunta que ele responde
    — onde a sala para. A contagem CRUA continua em 'n', que e o que a dica
    mostra; o tom sai de 'z'."""
    if not soma:
        return []
    peso = ((1, 2, 1), (2, 4, 2), (1, 2, 1))
    saida = []
    for (x, y), n in sorted(soma.items()):
        acc = tot = 0.0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                w = peso[dy + 1][dx + 1]
                # Vizinho fora da grade nao vira zero: isso puxaria a borda para
                # baixo e inventaria um corredor frio em volta da sala inteira.
                if (x + dx, y + dy) in soma:
                    acc += w * soma[(x + dx, y + dy)]
                    tot += w
        saida.append({"x": x, "y": y, "n": n,
                      "z": round(acc / tot, 1) if tot else float(n)})
    return saida


def _cortes_escala(valores: list) -> list:
    """Quatro cortes em fracoes do percentil 95, sobre os valores suavizados.

    As duas escolhas obvias falham aqui, e cada uma de um jeito:

    - LINEAR SOBRE O PICO: numa sala real a cauda e longa, um unico canto
      concentra tudo e o resto inteiro cai no tom mais fraco — ou, se o piso de
      transito for alto, o mapa inteiro vira o mesmo tom medio. Foi o que
      acontecia.
    - QUANTIL: reparte as celulas em cinco grupos iguais, entao 20% delas
      recebem o tom mais quente por definicao — mesmo quando 95% da sala e so
      gente passando. O mapa fica bonito e mente.

    O percentil 95 e a bussola certa porque ignora o extremo (um pico isolado
    nao reescala a sala inteira) sem achatar o meio. Acima dele, tom cheio.
    """
    if not valores:
        return []
    p95 = valores[min(len(valores) - 1, int(0.95 * len(valores)))]
    if p95 <= 0:
        return []
    cortes = []
    for f in (0.25, 0.5, 0.75, 1.0):
        c = round(p95 * f, 1)
        if not cortes or c > cortes[-1]:
            cortes.append(c)
    return cortes


@app.get("/api/serie")
def serie(dias: int = 30) -> dict:
    """A dimensão de TEMPO, que faltava para o painel.

    As views do Power BI já respondem isto em SQL (vw_eventos_dia,
    vw_pico_horario), mas o navegador não fala com o banco. Aqui a agregação
    sai em Python de propósito: TIMESTAMP no Postgres e TEXT no SQLite se
    agrupam com sintaxe diferente, e uma consulta que só funciona num dos dois
    quebra justamente no fallback, que é quando ninguém pode parar para
    consertar.
    """
    dias = max(1, min(dias, 365))
    with cursor() as (cur, m):
        cur.execute(
            """SELECT timestamp, tipo_evento FROM logs_seguranca_escola
               ORDER BY id"""
        )
        linhas = cur.fetchall()

    corte = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)
    por_dia: dict[str, dict] = {}
    por_hora = [0] * 24
    total = graves = 0

    for ts, tipo in linhas:
        if TIPOS_PAINEL and tipo not in TIPOS_PAINEL:
            continue
        momento = ts if not isinstance(ts, str) else _ler_momento(ts)
        if momento is None or momento < corte:
            continue
        dia = momento.date().isoformat()
        alvo_dia = por_dia.setdefault(dia, {"dia": dia, "total": 0, "graves": 0})
        alvo_dia["total"] += 1
        por_hora[momento.hour] += 1
        total += 1
        if tipo in GRAVES:
            alvo_dia["graves"] += 1
            graves += 1

    # Dia sem evento tem de sair como zero, nao sumir da lista: o grafico liga
    # um ponto no outro por posicao, entao uma lacuna de quatro dias virava uma
    # reta subindo — desenhando movimento onde nao houve nenhum.
    hoje = datetime.now(timezone.utc).replace(tzinfo=None).date()
    serie_dia = []
    for i in range(dias - 1, -1, -1):
        dia = (hoje - timedelta(days=i)).isoformat()
        serie_dia.append(por_dia.get(dia, {"dia": dia, "total": 0, "graves": 0}))

    return {
        "dias": dias,
        "total": total,
        "graves": graves,
        "por_dia": serie_dia,
        "por_hora": [{"hora": h, "n": n} for h, n in enumerate(por_hora)],
    }


def _ler_momento(texto: str):
    """SQLite devolve texto. Aceita o formato que gravamos e o que o
    CURRENT_TIMESTAMP do SQLite escreve, sem estourar numa linha estranha."""
    texto = texto.strip().replace("T", " ")
    if "." in texto:
        texto = texto.split(".", 1)[0]
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


@app.get("/painel")
def pagina_painel() -> FileResponse:
    """O painel de leitura. A página da sala grava; esta aqui só lê."""
    if not PAINEL.exists():
        raise HTTPException(404, f"não achei {PAINEL.name} ao lado do servidor")
    return FileResponse(PAINEL, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/api/painel")
def painel() -> dict:
    """O que o Power BI consome. Agregado, nunca linha a linha de pessoa."""
    with cursor() as (cur, m):
        onde, vals = filtro_tipos(m)
        cur.execute(
            f"""SELECT tipo_evento, COUNT(*) FROM logs_seguranca_escola {onde}
                GROUP BY tipo_evento ORDER BY COUNT(*) DESC""", vals
        )
        por_tipo = [{"tipo": r[0], "n": r[1]} for r in cur.fetchall()]
        cur.execute(
            f"""SELECT localizacao, COUNT(*) FROM logs_seguranca_escola {onde}
                GROUP BY localizacao ORDER BY COUNT(*) DESC""", vals
        )
        por_local = [{"local": r[0], "n": r[1]} for r in cur.fetchall()]
    return {"por_tipo": por_tipo, "por_local": por_local,
            "integridade": verificar()}


if __name__ == "__main__":
    import uvicorn

    porta = int(os.environ.get("PORTA", "8000"))
    # HOST=0.0.0.0 libera o acesso de outro aparelho da mesma rede (celular,
    # o notebook da apresentacao). O padrao continua so nesta maquina.
    host = os.environ.get("HOST", "127.0.0.1")

    print(f"[auditix] sala   -> http://127.0.0.1:{porta}/")
    print(f"[auditix] painel -> http://127.0.0.1:{porta}/painel")
    # Sem esta linha, um .env nao lido (ou salvo como .env.txt) some sem
    # rastro: o servidor simplesmente nao avisa ninguem e a tela fica igual.
    if WEBHOOK:
        print(f"[auditix] alerta por e-mail LIGADO ({ALERTA_TIPOS}, "
              f"espera {ALERTA_ESPERA:.0f}s)"
              + ("" if WEBHOOK_SEGREDO else " — SEM SEGREDO, qualquer um pode disparar"))
    else:
        print("[auditix] alerta por e-mail DESLIGADO (falta WEBHOOK_URL no .env)")
    # Mesmo motivo do aviso acima: o que fica LIGADO ou DESLIGADO em silencio
    # e o que ninguem descobre a tempo. Ja perdemos uma tarde por causa de um
    # WEBHOOK_URL vazio que nao avisava nada.
    if CALIBRACAO:
        print(f"[auditix] registro de calibração LIGADO — grava o que o sistema "
              f"VÊ, não só o que acusa, e quanto custa vê-lo. Resumo em "
              f"/api/calibracao, planilha em /api/calibracao.csv. "
              f"Poda em {CALIBRACAO_DIAS:.0f} dias.")
    else:
        print("[auditix] registro de calibração DESLIGADO "
              "(CALIBRACAO=1 no .env para medir a margem numa sala de verdade)")
    print("[auditix] deixe esta janela ABERTA. Ctrl+C encerra.")

    # log_level="info" de proposito: o uvicorn precisa dizer "estou de pe".
    # Servidor que sobe calado nao da para diagnosticar quando cai.
    try:
        uvicorn.run(app, host=host, port=porta, log_level="info")
    except OSError as e:
        # Quase sempre e a porta ocupada: outra janela ficou aberta.
        print(f"\n[auditix] nao consegui abrir a porta {porta}: {e}")
        print(f"[auditix] feche a outra janela, ou rode com outra porta:")
        print(f"[auditix]   $env:PORTA=8001; uv run servidor.py")
        raise SystemExit(1)

    # Se chegou aqui, o uvicorn PAROU. Sem esta linha o processo sai em
    # silencio e parece que nunca subiu.
    print("[auditix] servidor encerrado.")
