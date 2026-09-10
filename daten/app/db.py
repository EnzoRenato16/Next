"""Persistencia em SQLite (offline-first) — Passo 11 do roteiro.

Tabelas: students, attendance, camera_status, security_events.
Eventos precisam sobreviver ao reinicio do processo.

Retencao (LGPD Art. 14): students carrega created_at e last_seen. Os dois
juntos respondem "esta biometria ainda pode existir?" — o prazo do
consentimento conta de created_at, e a inatividade conta de last_seen.
Quem apaga de verdade e app/retencao.py, porque apagar so a linha aqui
deixaria o embedding vivo em data/embeddings.npz.
"""

import sqlite3
import threading
from datetime import datetime, timedelta

from . import config

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


_con = _connect()


def init_db() -> None:
    with _lock:
        _con.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,   -- ex.: RM ou apelido
                name       TEXT NOT NULL,
                turma      TEXT,
                created_at TEXT,               -- inicio do prazo de consentimento
                last_seen  TEXT                -- ultima vez reconhecido (inatividade)
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                name       TEXT,
                room_id    TEXT,
                confidence REAL,
                timestamp  TEXT
            );

            CREATE TABLE IF NOT EXISTS camera_status (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id    TEXT,
                online       INTEGER,
                fps          REAL,
                width        INTEGER,
                height       INTEGER,
                last_error   TEXT,
                timestamp    TEXT
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kind       TEXT,          -- reconhecido | desconhecido | objeto_perigoso
                detail     TEXT,
                confidence REAL,
                room_id    TEXT,
                status     TEXT,          -- pendente_validacao_humana
                timestamp  TEXT
            );
            """
        )
        # Bancos criados antes da retencao nao tem last_seen. Adiciona sem
        # perder o que ja esta gravado.
        colunas = {r["name"] for r in _con.execute("PRAGMA table_info(students)")}
        if "last_seen" not in colunas:
            _con.execute("ALTER TABLE students ADD COLUMN last_seen TEXT")
        _con.commit()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_student(student_id: str, name: str, turma: str = "") -> None:
    """Cadastra ou recadastra. Recadastrar REINICIA o prazo de consentimento,
    que e o comportamento certo: houve autorizacao nova."""
    agora = _now()
    with _lock:
        _con.execute(
            "INSERT INTO students(student_id,name,turma,created_at,last_seen) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, "
            "turma=excluded.turma, created_at=excluded.created_at, "
            "last_seen=excluded.last_seen",
            (student_id, name, turma, agora, agora),
        )
        _con.commit()


def touch_student(student_id: str) -> None:
    """Marca que a pessoa foi vista agora. E o que segura o relogio da
    inatividade: quem frequenta a escola nunca vence por esse lado."""
    with _lock:
        _con.execute("UPDATE students SET last_seen=? WHERE student_id=?",
                     (_now(), student_id))
        _con.commit()


def log_attendance(student_id: str, name: str, confidence: float) -> None:
    with _lock:
        _con.execute(
            "INSERT INTO attendance(student_id,name,room_id,confidence,timestamp) "
            "VALUES(?,?,?,?,?)",
            (student_id, name, config.ROOM_ID, round(float(confidence), 4), _now()),
        )
        _con.commit()


def log_security_event(kind: str, detail: str, confidence: float) -> None:
    with _lock:
        _con.execute(
            "INSERT INTO security_events(kind,detail,confidence,room_id,status,timestamp) "
            "VALUES(?,?,?,?,?,?)",
            (kind, detail, round(float(confidence), 4), config.ROOM_ID,
             "pendente_validacao_humana", _now()),
        )
        _con.commit()


def today_attendance() -> list:
    """Presencas distintas de hoje (uma linha por pessoa, a mais recente)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock:
        rows = _con.execute(
            "SELECT student_id, name, MAX(timestamp) AS timestamp, MAX(confidence) AS confidence "
            "FROM attendance WHERE timestamp LIKE ? "
            "GROUP BY student_id ORDER BY timestamp DESC",
            (today + "%",),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- Retencao de biometria -------------------------------------------------

def _dias_desde(iso: str) -> float:
    """Dias decorridos desde um timestamp ISO. Valor ausente ou ilegivel conta
    como 0: na duvida NAO apaga biometria, so avisa."""
    if not iso:
        return 0.0
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).total_seconds() / 86400
    except ValueError:
        return 0.0


def students_status() -> list:
    """Todo mundo cadastrado, com quantos dias faltam em cada relogio.

    `expira_em` e o menor dos dois prazos: e o que realmente vale.
    """
    with _lock:
        rows = _con.execute(
            "SELECT student_id, name, turma, created_at, last_seen "
            "FROM students ORDER BY name"
        ).fetchall()

    saida = []
    for r in rows:
        d = dict(r)
        # Sem last_seen (cadastro antigo), a inatividade conta do cadastro.
        visto = d["last_seen"] or d["created_at"]
        resta_consent = config.RETENCAO_DIAS - _dias_desde(d["created_at"])
        resta_inativ = config.INATIVIDADE_DIAS - _dias_desde(visto)
        d["dias_para_consentimento_vencer"] = round(resta_consent, 1)
        d["dias_para_inatividade_vencer"] = round(resta_inativ, 1)
        d["expira_em"] = round(min(resta_consent, resta_inativ), 1)
        d["motivo"] = ("consentimento vencido" if resta_consent <= 0 else
                       "inatividade" if resta_inativ <= 0 else "")
        saida.append(d)
    return saida


def expired_students() -> list:
    """Quem ja passou de um dos dois prazos. Nao apaga nada, so aponta."""
    return [s for s in students_status() if s["expira_em"] <= 0]


def delete_student(student_id: str) -> None:
    """Apaga a pessoa da tabela students.

    A presenca ja registrada em attendance NAO e apagada de proposito: ela e
    registro escolar (fulano esteve na aula tal), nao dado biometrico. O que a
    LGPD manda descartar e a biometria, e essa mora em students + embeddings.npz.
    """
    with _lock:
        _con.execute("DELETE FROM students WHERE student_id=?", (student_id,))
        _con.commit()
