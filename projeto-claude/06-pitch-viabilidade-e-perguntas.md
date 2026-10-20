# Pitch, viabilidade e respostas para a banca

## O pitch (`Auditix-pitch.html`)

12 slides em HTML (three.js versionado, roda sem internet), modo 5 minutos por
padrão, abrir com `pc pitch` (serve em 127.0.0.1:8090). Ordem: dados, Auditix
IA, sala 360, vídeo, A e B, cadeia, painel, privacidade, LGPD, AIBOX, custo,
equipe. Teclas: setas, `F` tela cheia, `N` roteiro, `M` deck completo, `T`
zera o cronômetro.

Dados de abertura (com fonte na tela, não trocar por número sem fonte):
15.759 episódios de violência em escolas em 2024 (Anuário Brasileiro de
Segurança Pública 2025, SINAN); mais de 55 mil internações de crianças por
queda em 2025 (Criança Segura, DataSUS).

## Custo (slide do pitch)

- Câmera IP: R$ 0 (a escola já tem; se faltar, Intelbras VIPC 1230 B G2 de
  R$ 258 a R$ 455 no varejo, out/2026).
- AI BOX: preço da DATEN (único hardware novo).
- Software: R$ 0 (código do grupo sobre bibliotecas e modelos abertos).
- Servidor e e-mail: R$ 0 (PC da coordenação e e-mail da escola).
- Banco na nuvem: R$ 0 (SQLite) a US$ 25/mês (Postgres db.t4g.micro, São Paulo).
- Programador: R$ 8.000 por empresa, na implantação.
- **Plano: a partir de R$ 18.500 por empresa**, implantação e programador
  inclusos.
- Atenção às licenças: YOLO11 é AGPL (sem custo com o código aberto); o ArcFace
  `w600k_mbf` é licença **não comercial** (serve para a competição; para vender
  é preciso trocar de modelo, por exemplo AdaFace, MIT).

## Métricas técnicas para citar (todas medidas)

- **0 estranhos aprovados em 2.558 leituras** na câmera da arena; pior nota de
  estranho 0,27, limiar 0,34.
- Dono de frente: **0,75 a 0,82**; decidido em **menos de 1 s** (3 leituras).
- Galeria: **100% das fotos acertam o dono**, folga mínima +0,46.
- Tudo **offline, dentro da AI BOX**; nenhuma imagem sai da sala.

## Respostas prontas

**"Por que o vídeo tem poucos quadros por segundo?"**
"A imagem mostra só os quadros que a IA analisou de verdade, em resolução
cheia, dentro da caixa. Cada pessoa é decidida em menos de 1 segundo, com 3
leituras do rosto."

**"Por que não usar Gemini/ChatGPT para identificar?"**
"A regra exige processamento na AI BOX e não há internet. Modelos de linguagem
não comparam com uma galeria e recusam identificar pessoas pelo rosto. E
mandar o rosto de quem não consentiu para fora seria problema de LGPD. Usamos
IA especializada em rosto, offline."

**"E a NPU?"**
"A AI BOX tem NPU Hexagon com SNPE 2.12. Hoje o reconhecimento roda na CPU e
decide em menos de 1 s. O próximo passo, já mapeado, é converter YuNet e
ArcFace para a NPU e deixar a CPU só com a decisão. Isso libera a caixa para
mais câmeras."

**"Como escala?"**
Uma AI BOX por sala (ou por grupo de câmeras quando a NPU estiver em uso), PC
da coordenação com o painel, banco local ou na nuvem. Implantação por
programador, sem licença por câmera nem por aluno.

**"E quem está de costas ou muito longe?"**
"Sem rosto visível não há reconhecimento facial, em nenhum sistema. Rosto
pequeno demais aparece em cinza e não entra na conta, para a plateia ao fundo
não virar alerta. Quem chega perto é decidido."

**"E se errar?"**
"Na dúvida o sistema dá alerta, nunca autoriza. Estranho nunca passou do
limiar nos nossos testes. Erro aparece no placar e no resultado gravado; não
escondemos."
