# SVATech Health — Caixa-Preta Inteligente do Centro Cirúrgico

> Plataforma de **Edge AI** que audita visualmente, em tempo real, o uso de **OPMEs**
> (Órteses, Próteses e Materiais Especiais) para blindar hospitais contra **glosas
> milionárias**, fraudes operacionais e garantir a segurança do paciente.

**Grupo:** Auditix AI (grupo11) — Enzo Renato Cunha, 2ECR
**Contexto:** Desafio DATEN × FIAP — "Antes do NEXT" (marca SVATech)

---

## 1. O Problema (a dor de negócio)

Hospitais perdem **milhões** com **glosas de OPME**: o plano de saúde se recusa a pagar
alegando que o material (ex.: um parafuso de titânio de R$ 15.000) não foi usado.
Sem prova visual do momento do uso, o hospital não consegue contestar.

**Um único parafuso glosado = R$ 15.000.** O SVATech recupera isso com um log visual
em milissegundos.

---

## 2. A Solução

Uma "caixa-preta" na sala de cirurgia que **detecta, registra e comprova** o uso de
cada OPME — com **timestamp, foto do frame e leitura do lote/etiqueta** — gerando
evidência irrefutável para auditoria.

> **Enquadramento ético:** o sistema gera **evidência para revisão humana**, não acusa
> ninguém. *Alerta ≠ acusação.* É uma ferramenta de **rastreabilidade e auditoria**.

---

## 3. Hardware (Infraestrutura)

| Componente | Especificação | Papel |
|---|---|---|
| Processamento (Edge) | **Raspberry Pi 4 Model B (4GB RAM)** | Cérebro local — IA sem nuvem (latência zero + privacidade/LGPD) |
| Visão | Câmera IP RTSP **ou** USB Full HD | Monitora a mesa de instrumentação / campo cirúrgico |
| Armazenamento | MicroSD 32GB+ Classe 10 (ou SSD) | Linux + persistência local do banco |
| Acelerador (opcional) | **Google Coral USB (Edge TPU)** | Upgrade futuro de FPS se houver muitos itens simultâneos |

> **Nota de viabilidade (Pi 4, sem Coral):** o gargalo é só o YOLO (~2–6 FPS real, não 30).
> **Tudo bem** — o item fica parado na mesa. Estratégia: rodar em 320×320, com
> **frame-skipping** (YOLO 1x a cada N frames, ByteTrack arrasta o ID). Usar
> **Raspberry Pi OS 64-bit** e dissipador+ventoinha (evita throttle na demo).
> Se migrar pro AIBOX (Kryo 670 8-core + GPU Adreno), o mesmo código roda voando.

---

## 4. Stack de Software

| Módulo | Tecnologia | Aplicação |
|---|---|---|
| Core | **Python** | Orquestração do pipeline de visão + backend |
| Captura de vídeo | **OpenCV** | Conexão com a câmera, leitura de frames, bounding boxes |
| IA | **YOLO nano (TFLite/NCNN, quantizado) + ByteTrack** | Detecção leve (15–30 FPS ideal) + tracking pra não contar o mesmo item 2x |
| Leitura de etiqueta | **pyzbar** | Lê código de barras + nº de lote (a prova antiglosa de verdade) |
| Banco de dados | **SQLite** | Registro offline-first (item, horário, status, confiança) |
| API | **FastAPI** | Endpoints REST rápidos → dashboard financeiro / ERP do hospital |

---

## 5. Fluxo do Efeito "UAU"

1. **Ingestão** — a câmera foca na mesa cirúrgica.
2. **Detecção** — o YOLO no Pi identifica a caixa/etiqueta do OPME imediatamente.
3. **Leitura da prova** — o `pyzbar` lê o **código de barras + lote** da etiqueta.
4. **Registro** — o SQLite salva `timestamp`, `frame.jpg`, classe, lote e confiança.
5. **Blindagem financeira** — a FastAPI dispara alerta ao dashboard. Se o plano tentar
   glosar, o hospital tem o **log visual + lote** em milissegundos para comprovar o uso.

---

## 6. Diferencial Estratégico (o que faz GANHAR)

- **Herói técnico = ler a etiqueta, não "reconhecer o objeto".** Detectar forma é frágil;
  ler **barcode + lote + registro ANVISA** transforma "vi um objeto" em prova defensável.
- **Foco:** 1 fluxo impecável (detecta → lê lote → salva prova → alerta) > 5 features meia-boca.
- **Demo ao vivo:** pegar uma caixa na frente do jurado e o dashboard piscar
  "🟢 OPME auditado — lote 4471 — R$15.000 — [foto]".
- **Número de impacto:** "1 parafuso glosado = R$15.000; recuperado em milissegundos."
- **Edge/offline + LGPD:** dado de centro cirúrgico é sensível — processar local é a
  arquitetura correta.

---

## 7. MVP para a Demo (sem hospital)

Webcam apontando pra uma mesa com **caixinhas rotuladas** simulando OPMEs:

1. Câmera → OpenCV
2. YOLO detecta "caixa de OPME"
3. ByteTrack → ID único (não conta 2x)
4. Salva `frame.jpg` + timestamp + classe + confiança no SQLite
5. **Bônus matador:** `pyzbar` lê o código de barras (lote)
6. FastAPI expõe `/api/v1/audit/log` → dashboard mostra o item auditado

---

## 8. Estrutura de Projeto (proposta)

```
svatech-health/
├── app/
│   ├── capture.py        # câmera + OpenCV
│   ├── detector.py       # YOLO + ByteTrack
│   ├── barcode.py        # pyzbar (leitura de lote)
│   ├── db.py             # SQLite (auditorias)
│   └── api.py            # FastAPI (endpoints REST)
├── models/               # pesos YOLO (nano, quantizado)
├── data/                 # eduvision.db + frames de prova
├── logs/
├── config/
│   └── camera.env        # RTSP/credenciais (NÃO versionar — chmod 600)
├── dashboard/            # HTML do painel de auditoria
├── tests/
├── requirements.txt
└── README.md
```

**Esquema SQLite sugerido — tabela `audits`:**
`id, opme_class, lote, timestamp, confidence, frame_path, status`
