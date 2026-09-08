# Graph Report - Next  (2026-09-03)

## Corpus Check
- Corpus is ~10,814 words - fits in a single context window. You may not need a graph.

## Summary
- 127 nodes · 176 edges · 11 communities (8 shown, 3 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 23 edges (avg confidence: 0.89)
- Token cost: 100,589 input · 17,516 output

## Community Hubs (Navigation)
- EduVision Docs & Models
- SVATech Health Pitch Deck
- Face Recognition Pipeline
- EduVision App Modules
- Database & Startup
- FastAPI Endpoints
- PPTX Builder Script
- SVATech Health Tech Stack
- NumPy Dependency
- Uvicorn Dependency
- Google Coral Hardware

## God Nodes (most connected - your core abstractions)
1. `FaceEngine` - 11 edges
2. `SVATech Health Pitch Deck (index.html)` - 11 edges
3. `Pipeline` - 10 edges
4. `EduVision Project (Grupo11 / Auditix AI, AIBOX)` - 10 edges
5. `Pipeline Slide: Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI` - 7 edges
6. `EduVision Project Structure (app/, config/, models/, data/faces/)` - 6 edges
7. `SVATech Health Project` - 5 edges
8. `YuNet (face detector)` - 5 edges
9. `SFace (face embedding model)` - 5 edges
10. `EduVision Pitch Deck` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Raspberry Pi 4 Model B (Edge Compute)` --semantically_similar_to--> `AIBOX (Edge AI device)`  [INFERRED] [semantically similar]
  SVATech_Health.md → daten/README.md
- `Why YuNet+SFace (lightweight, GPU-free, independent of professor's YOLO)` --semantically_similar_to--> `Read-the-label > recognize-the-shape (technical differentiator)`  [INFERRED] [semantically similar]
  daten/README.md → SVATech_Health.md
- `Ethical Framing: Alerta ≠ Acusação` --semantically_similar_to--> `Ética Passo 12: alerta ≠ acusação (Desconhecido pendente de validação)`  [INFERRED] [semantically similar]
  SVATech_Health.md → daten/README.md
- `Proposed Project Structure (app/, models/, data/, dashboard/)` --semantically_similar_to--> `EduVision Project Structure (app/, config/, models/, data/faces/)`  [INFERRED] [semantically similar]
  SVATech_Health.md → daten/README.md
- `Pipeline Slide: Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI` --conceptually_related_to--> `pyzbar (barcode/lote reader)`  [INFERRED]
  index.html → SVATech_Health.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **SVATech Health detection→proof pipeline (Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI)** — svatech_health_opencv, svatech_health_yolo_nano, svatech_health_bytetrack, svatech_health_pyzbar, svatech_health_sqlite, svatech_health_fastapi [EXTRACTED 1.00]
- **EduVision face-recognition + attendance flow (YuNet+SFace → SQLite → FastAPI)** — daten_readme_yunet, daten_readme_sface, daten_readme_sqlite, daten_readme_fastapi [EXTRACTED 1.00]
- **Auditix AI shared Edge-AI + 'alert ≠ accusation' design pattern across SVATech Health and EduVision** — svatech_health_raspberry_pi4, svatech_health_ethical_framing, daten_readme_aibox, daten_readme_ethics_passo12 [INFERRED 0.85]

## Communities (11 total, 3 thin omitted)

### Community 0 - "EduVision Docs & Models"
Cohesion: 0.11
Nodes (25): opencv/opencv_zoo repository, face_recognition_sface_2021dec.onnx, face_detection_yunet_2023mar.onnx, EduVision Pitch Deck, Ethics note: alerta não é acusação, How It Works: cadastro → localizar → comparar → decidir, Problem Slide: manual surveillance fatigue, Solution Slide: AIBOX recognizes authorized people (+17 more)

### Community 1 - "SVATech Health Pitch Deck"
Cohesion: 0.13
Nodes (19): Closing Metrics Slide (100% rastreado, 0 dado na nuvem), Edge Setup Slide: Raspberry Pi in the operating room, InlineEditor (JS inline-edit + localStorage class), Hero Slide: reading the label (barcode/lote/ANVISA), Ledger Security Slide: hash-chained blocks (blockchain-like), Live Demo Slide: dashboard mock, Problem Slides: R$15.000 parafuso / R$5,8 bi glosa anual, SlidePresentation (JS deck controller class) (+11 more)

### Community 2 - "Face Recognition Pipeline"
Cohesion: 0.14
Nodes (5): Pipeline, FaceEngine, Alinha o rosto (usando os landmarks da linha do YuNet) e extrai o embedding., Retorna (student_id, name, score) do melhor match, ou (None, 'Desconhecido',…, ndarray

### Community 3 - "EduVision App Modules"
Cohesion: 0.17
Nodes (9): Captura RTSP + processamento (deteccao/reconhecimento) em thread — Passos 5-10.…, main(), Passo 6 do roteiro — captura 1 frame e salva em data/frame.jpg. Teste minimo…, mask_secret(), Configuracao central do EduVision. Regra do roteiro: NENHUMA senha no codigo-…, Esconde a senha ao logar a URL RTSP., Cadastro (enrollment) dos membros do grupo — Passo 10 do roteiro. Como usar: 1.…, EduVision — Grupo11 (Auditix AI) — Desafio DATEN x FIAP. Pipeline de Edge AI no… (+1 more)

### Community 4 - "Database & Startup"
Cohesion: 0.19
Nodes (13): Connection, _connect(), init_db(), log_attendance(), log_security_event(), _now(), Persistencia em SQLite (offline-first) — Passo 11 do roteiro. Tabelas:…, Presencas distintas de hoje (uma linha por pessoa, a mais recente). (+5 more)

### Community 5 - "FastAPI Endpoints"
Cohesion: 0.26
Nodes (11): attendance(), classroom_status(), dashboard(), health(), _mjpeg(), present(), API REST + dashboard — Passos 13/14 do roteiro. Rodar (durante o…, Quem do grupo esta presente agora (confirmado). (+3 more)

### Community 6 - "PPTX Builder Script"
Cohesion: 0.20
Nodes (8): BRACKET, C, chrome(), iconRow(), p, pptxgen, T(), tint()

### Community 7 - "SVATech Health Tech Stack"
Cohesion: 0.25
Nodes (8): SQLite (students/attendance DB), Pipeline Slide: Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI, /api/v1/audit/log endpoint, ByteTrack (object tracking), FastAPI (REST endpoints), OpenCV (video capture), SQLite (audits DB), YOLO nano (TFLite/NCNN quantized)

## Knowledge Gaps
- **21 isolated node(s):** `pptxgen`, `p`, `C`, `BRACKET`, `Google Coral USB (Edge TPU)` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 48 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FaceEngine` connect `Face Recognition Pipeline` to `EduVision App Modules`, `Database & Startup`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `SVATech Health Pitch Deck (index.html)` connect `SVATech Health Pitch Deck` to `SVATech Health Tech Stack`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `EduVision Project (Grupo11 / Auditix AI, AIBOX)` (e.g. with `EduVision Pitch Deck` and `Tech & Status Slide (done vs next)`) actually correct?**
  _`EduVision Project (Grupo11 / Auditix AI, AIBOX)` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Pipeline Slide: Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI` (e.g. with `ByteTrack (object tracking)` and `FastAPI (REST endpoints)`) actually correct?**
  _`Pipeline Slide: Câmera→OpenCV→YOLO nano→ByteTrack→pyzbar→SQLite→FastAPI` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pptxgen`, `p`, `C` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `EduVision Docs & Models` be split into smaller, more focused modules?**
  _Cohesion score 0.11333333333333333 - nodes in this community are weakly interconnected._
- **Should `SVATech Health Pitch Deck` be split into smaller, more focused modules?**
  _Cohesion score 0.1286549707602339 - nodes in this community are weakly interconnected._