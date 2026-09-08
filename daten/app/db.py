"""Persistencia em SQLite (offline-first) — Passo 11 do roteiro.

Tabelas: students, attendance, camera_status, security_events.
Eventos precisam sobreviver ao reinicio do processo.
"""

import sqlite3
import threading
from datetime import datetime

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
                created_at TEXT
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
        _con.commit()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_student(student_id: str, name: str, turma: str = "") -> None:
    with _lock:
        _con.execute(
            "INSERT INTO students(student_id,name,turma,created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, turma=excluded.turma",
            (student_id, name, turma, _now()),
        )
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
