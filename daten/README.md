# EduVision — Grupo11 (Auditix AI)

Reconhecimento facial dos membros do grupo rodando no **AIBOX** (Edge AI).
Desafio **DATEN × FIAP** — foco no **Passo 10 do roteiro** (cadastro + reconhecimento).

Câmera aponta pro grupo → o dashboard mostra **quem foi reconhecido**
(ex.: "Enzo ✓ 91%"), grava presença no SQLite e expõe uma API REST.

> Substitua `<IP_AIBOX>` pelo IP informado pelo professor (AIBOX_1 `192.168.50.10`
> ou AIBOX_2 `192.168.50.20`). A câmera é fixa em `192.168.50.108`.

---

## Stack
`Python 3.8` · `OpenCV` (YuNet + SFace, roda em CPU/ARM64) · `FastAPI` · `SQLite`

Escolhemos **YuNet + SFace** (OpenCV Zoo) porque são leves, rodam sem GPU e
**não dependem** do modelo YOLO do professor — são "nossos" e cabem no AIBOX.

---

## 0. No notebook: preparar e enviar

```bash
# IP fixo na rede do lab (cada notebook um IP diferente!)
#   IP 192.168.50.201  Máscara 255.255.255.0

# baixe os 2 modelos ONNX antes (ver models/README.md) e coloque em models/

# envie o projeto pro AIBOX (PowerShell/CMD do notebook):
scp -r "C:\Users\EWZ\Desktop\Next\daten\*" grupo11@<IP_AIBOX>:/home/grupo11/eduvision/
```

## 1. Entrar no AIBOX (Passo 1)
```bash
ssh grupo11@<IP_AIBOX>        # senha: grupo112026
whoami                        # -> grupo11   (se aparecer root, PARE)
cd ~/eduvision
```

## 2. Ambiente Python (Passo 3)
```bash
python3 -m venv .venv
source .venv/bin/activate
which python                  # -> ~/eduvision/.venv/...
pip install -r requirements.txt
```

## 3. Credenciais da câmera (Passo 4 — fora do código)
```bash
cp config/camera.env.example config/camera.env
nano config/camera.env        # confira usuário/senha da câmera (FIAP / fiap@2026)
chmod 600 config/camera.env
source config/camera.env
```

## 4. Testar rede + RTSP (Passos 5-6)
```bash
ping -c 4 192.168.50.108
python -m app.capture_once    # gera data/frame.jpg -> confirme que é a sala
```

## 5. Cadastrar os membros do grupo (Passo 10 — enrollment)
```bash
# 1 subpasta por pessoa, 2+ fotos de rosto cada:
#   data/faces/enzo/1.jpg  data/faces/enzo/2.jpg
#   data/faces/luan/1.jpg  ...
python -m app.enroll          # gera data/embeddings.npz + tabela students
```

## 6. Rodar o sistema (Passos 7/13)
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Durante o desenvolvimento, mantenha em `127.0.0.1`. A abertura pra rede
(`--host 0.0.0.0`, acessar `http://<IP_AIBOX>:8000`) é só na **validação final**
com o professor.

## 7. Testar endpoints (Passo 14 — evidências)
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/classroom/status
curl http://127.0.0.1:8000/api/v1/present
curl http://127.0.0.1:8000/api/v1/attendance
```

| Rota | O que retorna |
|---|---|
| `/` | Dashboard (stream + presentes) |
| `/video` | Stream MJPEG anotado |
| `/health` | online / camera_offline |
| `/api/v1/classroom/status` | métricas (fps, presentes, cadastrados…) |
| `/api/v1/present` | quem do grupo está presente agora |
| `/api/v1/attendance` | presenças de hoje (SQLite) |
| `/docs` | Swagger automático do FastAPI |

---

## Estrutura
```
daten/
├── app/
│   ├── config.py        # caminhos, RTSP, limiares (sem senha)
│   ├── camera.py        # captura RTSP + processamento (thread) + métricas
│   ├── recognizer.py    # YuNet (detecta) + SFace (embedding) + matching
│   ├── enroll.py        # cadastro dos membros (fotos -> embeddings.npz)
│   ├── capture_once.py  # teste do Passo 6 (1 frame)
│   ├── db.py            # SQLite: students, attendance, camera_status, security_events
│   └── main.py          # FastAPI + dashboard
├── config/
│   ├── camera.env.example
│   └── eduvision.service   # template de boot (entregar ao professor)
├── models/              # YuNet + SFace .onnx (ver models/README.md)
├── data/faces/          # fotos p/ cadastro (não versionar)
├── requirements.txt
└── README.md
```

## Regras do lab respeitadas
- Sem `sudo`/root; tudo em `/home/grupo11` e no `.venv`.
- Senha da câmera só em `config/camera.env` (chmod 600, no `.gitignore`).
- API em `127.0.0.1` até a validação final.
- Ética (Passo 12): *alerta ≠ acusação* — não reconhecido vira **"Desconhecido"**
  e evento **pendente de validação humana**, nunca acusação.
```
