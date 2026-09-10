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
| `/api/v1/retencao` | prazo de cada biometria guardada (LGPD) |
| `/docs` | Swagger automático do FastAPI |

---

## 8. Retenção de biometria (LGPD Art. 14)

Biometria de criança e adolescente não fica guardada para sempre. Dois relógios
independentes, e **o primeiro que vencer apaga o cadastro**:

| Prazo | Padrão | Conta a partir de | Para que serve |
|---|---|---|---|
| `RETENCAO_DIAS` | 365 | data do cadastro | prazo do consentimento; vencido, só volta com autorização nova |
| `INATIVIDADE_DIAS` | 90 | última vez reconhecido | é como o sistema percebe sozinho que o aluno **saiu da escola** |

O segundo é o que responde de verdade a "apagar quando o aluno sai": ninguém vai
lembrar de avisar o sistema que fulano mudou de colégio, mas quem saiu para de
ser reconhecido.

Apagar aqui significa apagar **os dois lugares** onde a biometria mora: a linha
em `students` e as amostras dela em `data/embeddings.npz`. Apagar só o primeiro
deixaria o rosto reconhecível, que é exatamente o dado que a lei manda
descartar. O descarte fica registrado em `security_events` — a escola precisa
conseguir provar que fez.

**O que NÃO é apagado:** a presença já registrada em `attendance`. Isso é
registro escolar (fulano esteve na aula tal), não biometria.

```bash
python -m app.retencao --ver    # só mostra os prazos, não apaga
python -m app.retencao          # apaga o que venceu
curl http://127.0.0.1:8000/api/v1/retencao
```

O expurgo também roda sozinho **no startup da API**: se um prazo venceu com o
sistema desligado, ele não volta reconhecendo a pessoa. Para rodar todo dia:

```
0 3 * * *  cd ~/eduvision && .venv/bin/python -m app.retencao
```

---

## 9. Desempenho no AIBOX — meça antes de otimizar

```bash
python -m app.capture_once   # gera data/frame.jpg (a SUA sala)
python -m app.bench          # mede com esse frame
```

### `DETECT_WIDTH` — onde está o ganho de verdade

O YuNet roda no frame **reduzido**; o recorte do rosto continua saindo do frame
em resolução cheia, então o embedding não perde qualidade junto com o custo.
Medido aqui em 1280×720, 4 threads, OpenCV 4.10:

| largura | custo | ganho |
|---|---|---|
| 1280 (resolução cheia) | 36,9 ms | 1,0× |
| 960 | 20,4 ms | 1,8× |
| **640 (padrão)** | **8,7 ms** | **4,2×** |
| 320 | 3,8 ms | 9,7× |

O limite é o **tamanho do rosto depois de reduzir**: abaixo de ~40 px o YuNet
simplesmente não acha. Um rosto de 90 px em 720p some se você reduzir para 480.

> Por isso o padrão é **640 e não os 320** do `SVATech_Health.md`: 320 serve para
> uma caixa de OPME a um metro da câmera, não para uma sala com gente sentada ao
> fundo. Rode o `app.bench` com o frame da sala real e escolha a **menor largura
> que ainda ache todo mundo**.

### `SFACE_BACKEND` — o ONNX Runtime não venceu

A recomendação comum é trocar o OpenCV DNN por ONNX Runtime. **Medimos, e aqui
ele ficou mais lento:**

| | OpenCV DNN | ONNX Runtime |
|---|---|---|
| OpenCV 4.10, 4 threads | **11,6 ms/rosto** | 18,2 ms |
| OpenCV 5.00, 4 threads | **7,5 ms/rosto** | 20,3 ms |

O suporte existe e é trocável sem editar código (`export SFACE_BACKEND=ort`),
porque em ARM64 pode inverter. Mas o padrão é o que está medido: `opencv`.
Meça no AIBOX antes de mudar.

**Cuidado que isso revelou:** o SFace espera **RGB**, não BGR. Alimentado com
BGR ele devolve 128 números com cara de embedding e cosseno 0,877 contra o
OpenCV — alto demais para alguém notar, baixo demais para reconhecer bem. Por
isso o `FaceEngine` **confere a paridade dos dois backends no boot** e recusa o
ORT se o embedding divergir: cadastro feito num backend tem que valer no outro.

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
│   ├── retencao.py      # descarte automático de biometria vencida (LGPD)
│   ├── bench.py         # mede DETECT_WIDTH e SFACE_BACKEND no próprio aparelho
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
- Retenção (Art. 14): biometria **vence e some sozinha**, e a presença já
  registrada sobrevive ao descarte. Ver seção 8.
```
