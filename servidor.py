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
import os
import sqlite3
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

AQUI = Path(__file__).parent
PAGINA = AQUI / "auditix-sala.html"
PAINEL = AQUI / "auditix-painel.html"
SQLITE = AQUI / "auditix.db"
GENESE = "0" * 64

# eventos que merecem acordar alguém na hora
GRAVES = {"queda", "agitacao", "objeto_perigoso", "objeto_suspeito",
          "patrimonio_sumiu"}


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


class Celula(BaseModel):
    x: int
    y: int
    n: int


class Calor(BaseModel):
    camera: str = Field(default="sala-12", max_length=60)
    celulas: list[Celula]


@asynccontextmanager
async def ciclo(_app: FastAPI):
    criar_tabelas()
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

    if WEBHOOK and ev.tipo_evento in GRAVES:
        disparar_webhook(novo_id, momento, ev, atual)

    return {"id": novo_id, "timestamp": momento, "hash_anterior": anterior,
            "hash_atual": atual, "banco": "postgres" if USANDO_PG else "sqlite"}


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
    try:
        with httpx.Client(timeout=5) as cli:
            cli.post(WEBHOOK, json=corpo)
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


@app.get("/api/eventos")
def listar(limite: int = 50) -> list[dict]:
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT id, timestamp, aluno_id, tipo_evento, localizacao, hash_atual
                FROM logs_seguranca_escola ORDER BY id DESC LIMIT {m}""",
            (max(1, min(limite, 500)),),
        )
        return [
            {"id": r[0], "timestamp": str(r[1]), "aluno_id": r[2],
             "tipo_evento": r[3], "localizacao": r[4], "hash_atual": r[5]}
            for r in cur.fetchall()
        ]


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


@app.get("/api/mapa")
def mapa(camera: str = "sala-12") -> dict:
    with cursor() as (cur, m):
        cur.execute(
            f"""SELECT celula_x, celula_y, SUM(contagem) FROM mapa_calor
                WHERE camera = {m} GROUP BY celula_x, celula_y""",
            (camera,),
        )
        celulas = [{"x": r[0], "y": r[1], "n": int(r[2])} for r in cur.fetchall()]
    return {"camera": camera, "celulas": celulas,
            "pico": max((c["n"] for c in celulas), default=0)}


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

    return {
        "dias": dias,
        "total": total,
        "graves": graves,
        "por_dia": sorted(por_dia.values(), key=lambda d: d["dia"]),
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
        cur.execute(
            """SELECT tipo_evento, COUNT(*) FROM logs_seguranca_escola
               GROUP BY tipo_evento ORDER BY COUNT(*) DESC"""
        )
        por_tipo = [{"tipo": r[0], "n": r[1]} for r in cur.fetchall()]
        cur.execute(
            """SELECT localizacao, COUNT(*) FROM logs_seguranca_escola
               GROUP BY localizacao ORDER BY COUNT(*) DESC"""
        )
        por_local = [{"local": r[0], "n": r[1]} for r in cur.fetchall()]
    return {"por_tipo": por_tipo, "por_local": por_local,
            "integridade": verificar()}


if __name__ == "__main__":
    import uvicorn

    porta = int(os.environ.get("PORTA", "8000"))
    print(f"[auditix] abra http://127.0.0.1:{porta}")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
