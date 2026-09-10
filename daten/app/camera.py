"""Captura RTSP + processamento (deteccao/reconhecimento) em thread — Passos 5-10.

Baseado no camera_stream.py de exemplo, mas:
  - separa metricas de saude (Passo 7): camera_online, fps, frames, ultimo_erro;
  - roda o FaceEngine com frame-skip (DETECT_EVERY) para aliviar a CPU do AIBOX;
  - confirma presenca so apos ver a pessoa em varios frames (PRESENCE_MIN_HITS).
"""

import time
import threading
from collections import defaultdict

import cv2

from . import config, db, ponte
from .recognizer import FaceEngine


class Pipeline:
    def __init__(self):
        self.frame = None                 # ultimo frame anotado (BGR)
        self.lock = threading.Lock()

        # metricas de saude (Passo 7)
        self.camera_online = False
        self.fps = 0.0
        self.width = 0
        self.height = 0
        self.frames_processados = 0
        self.last_error = ""
        self.last_update = 0.0

        # estado de reconhecimento
        self.engine = None
        self.enrolled = 0
        # objeto suspeito (desligado por padrao; ver config.ARMAS_ATIVO)
        self.armas = None
        self.confirmador = None
        self._ultimas_armas = []
        self._hits = defaultdict(int)     # student_id -> frames confirmando
        self._present = {}                 # student_id -> {name, confidence, since}
        self._present_lock = threading.Lock()

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # ---- ciclo de vida -----------------------------------------------------
    def start(self):
        try:
            self.engine = FaceEngine()
            self.enrolled = len(self.engine.known_ids)
        except Exception as e:  # sem modelos ou sem cadastro: segue so com video
            self.last_error = f"FaceEngine off: {e}"
            print("[AVISO]", self.last_error)

        # Camada de objeto suspeito. Falhar aqui NAO pode derrubar a presenca:
        # e uma camada a mais, nao a razao de o sistema existir.
        if config.ARMAS_ATIVO:
            try:
                from .armas import DetectorArmas, Confirmador
                self.armas = DetectorArmas()
                self.confirmador = Confirmador()
                print(f"[OK] Objeto suspeito ligado ({self.armas.backend}, "
                      f"limiar {config.ARMA_CONF}, {config.ARMA_HITS} leituras).")
            except Exception as e:
                print(f"[AVISO] Objeto suspeito off: {e}")
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ---- leitura para a API ------------------------------------------------
    def present_people(self) -> list:
        with self._present_lock:
            return [dict(student_id=k, **v) for k, v in self._present.items()]

    def status(self) -> dict:
        return {
            "sistema": "EduVision",
            "grupo": config.GROUP_ID,
            "camera_id": config.CAMERA_ID,
            "room_id": config.ROOM_ID,
            "camera_online": self.camera_online,
            "resolucao": {"largura": self.width, "altura": self.height},
            "fps": round(self.fps, 2),
            "frames_processados": self.frames_processados,
            "cadastrados": self.enrolled,
            "presentes": len(self._present),
            "model_status": "ok" if self.engine else "sem_modelo",
            "objeto_suspeito": {
                "ativo": self.armas is not None,
                "backend": self.armas.backend if self.armas else None,
                "limiar": config.ARMA_CONF,
                "na_tela": len(self._ultimas_armas),
            },
            "last_error": self.last_error,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    # ---- loop principal ----------------------------------------------------
    def _run(self):
        print("Conectando a camera:", config.mask_secret(config.RTSP_URL))
        cap = cv2.VideoCapture(config.RTSP_URL)
        if not cap.isOpened():
            self.camera_online = False
            self.last_error = "Falha ao abrir RTSP (CAMERA_OFFLINE)"
            print("[ERRO]", self.last_error)
            return

        self.camera_online = True
        print("Camera conectada.")
        contador, inicio, n = 0, time.time(), 0

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                self.camera_online = False
                self.last_error = "CAMERA_OFFLINE"
                time.sleep(1)
                cap.release()
                cap = cv2.VideoCapture(config.RTSP_URL)   # tenta reconectar
                continue

            self.camera_online = True
            self.height, self.width = frame.shape[:2]
            n += 1
            self.frames_processados = n

            # FPS aproximado
            contador += 1
            dt = time.time() - inicio
            if dt >= 1:
                self.fps = contador / dt
                contador, inicio = 0, time.time()

            # Reconhecimento com frame-skip
            if self.engine and (n % config.DETECT_EVERY == 0):
                self._process_faces(frame)

            # Objeto suspeito: mais caro que o rosto, roda mais espacado
            if self.armas and (n % config.ARMA_CADA == 0):
                self._process_armas(frame)
            self._desenhar_armas(frame)

            self._draw_hud(frame)
            with self.lock:
                self.frame = frame
            self.last_update = time.time()

        cap.release()

    # ---- deteccao/reconhecimento por frame ---------------------------------
    def _process_faces(self, frame):
        faces = self.engine.detect(frame)
        seen_now = set()
        for f in faces:
            x, y, w, h = map(int, f[:4])
            feat = self.engine.embedding(frame, f)
            student_id, name, score = self.engine.identify(feat)

            if student_id:
                seen_now.add(student_id)
                self._hits[student_id] += 1
                color = (47, 158, 68)  # verde
                label = f"{name} {score:.2f}"
                # Confirma presenca so apos varios frames (nao confia em 1 frame)
                if self._hits[student_id] == config.PRESENCE_MIN_HITS:
                    with self._present_lock:
                        self._present[student_id] = {
                            "name": name,
                            "confidence": round(score, 3),
                            "since": time.strftime("%H:%M:%S"),
                        }
                    db.log_attendance(student_id, name, score)
                    # Segura o relogio da inatividade: quem aparece na aula
                    # nunca vence por falta de uso (ver app/retencao.py).
                    db.touch_student(student_id)
                    db.log_security_event("reconhecido", f"{name} presente", score)
                    print(f"[PRESENCA] {name} confirmado ({score:.2f})")
            else:
                color = (222, 83, 94)  # vermelho
                label = f"Desconhecido {score:.2f}"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, label, (x, max(20, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # decai hits de quem sumiu do frame (evita travar contagem)
        for sid in list(self._hits):
            if sid not in seen_now:
                self._hits[sid] = max(0, self._hits[sid] - 1)

    # ---- objeto suspeito ---------------------------------------------------
    def _process_armas(self, frame):
        try:
            achados = self.armas.detectar(frame)
        except Exception as e:
            self.last_error = f"armas: {e}"
            return
        self._ultimas_armas = achados

        for a in self.confirmador.passo(achados, time.time()):
            texto = f"{a['rotulo']} ({a['conf']:.0%})"
            print(f"[OBJETO SUSPEITO] {texto} — pendente de validacao humana")
            db.log_security_event("objeto_suspeito", texto, a["conf"])
            # Sem aluno_id de proposito: ver o comentario em ponte.enviar_evento.
            ponte.enviar_evento("objeto_suspeito", config.ROOM_ID)

    def _desenhar_armas(self, frame):
        """Desenha o que a ULTIMA leitura achou, em todos os quadros.

        A deteccao roda espacada; sem repintar entre uma e outra a caixa
        piscaria e daria a impressao de que o sistema esta incerto quando ele
        so esta economizando CPU.
        """
        for a in self._ultimas_armas:
            x, y, w, h = a["box"]
            cv2.rectangle(frame, (x, y), (x + w, y + h), (61, 83, 222), 2)
            cv2.putText(frame, f"{a['rotulo']} {a['conf']:.2f}",
                        (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (61, 83, 222), 2)

    def _draw_hud(self, frame):
        txt = (f"EduVision | {config.GROUP_ID} | {self.width}x{self.height} | "
               f"FPS {self.fps:.1f} | presentes {len(self._present)}/{self.enrolled}")
        cv2.putText(frame, txt, (16, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 136), 2)


# instancia unica compartilhada com a API
pipeline = Pipeline()
