# O modo arena por dentro

Arquivos: `aibox/arena.py` (programa), `aibox/arena.sh` (atalho),
`aibox/galeria.py` (galeria local), `aibox/arcface.py` (modelo de rosto),
`aibox/gstcam.py` (leitura da câmera), `aibox/cadastrar.py` (passada pela
câmera), `aibox/cadastrar_fotos.py` (galeria por fotos, no PC),
`aibox/achar_rtsp.py` (descobre o caminho da câmera, no PC),
`testes/arena_juiz.py` (52 testes do juiz).

## O caminho de cada quadro

1. **Câmera:** o OpenCV da caixa não abre RTSP, então o `gstcam` chama o
   `gst-launch-1.0` por fora (TCP, fila que descarta quadro velho). Pede a
   imagem em 1920x1080 com faixa preta em vez de esticar, e joga fora quadros
   acima de 6 por segundo antes de converter (`ARENA_FPS`).
2. **Achar rostos:** YuNet procura numa cópia de **1280 de largura**
   (`ARENA_DETECCAO`), o que baixou de ~530 para ~300 ms por quadro. Os pontos
   voltam para a escala cheia: o rosto é **medido no quadro cheio**.
3. **Portão de qualidade** (leitura só conta se passar em tudo):
   - nota do YuNet ≥ 0,80 (`ARENA_NOTA_MIN`);
   - largura ≥ 32 px (`ARENA_ROSTO_MIN`);
   - de pé (olhos lado a lado e acima do nariz);
   - **virado até 0,70** (`ARENA_FRENTE`): desvio do nariz até o meio dos
     olhos, dividido pela distância entre os olhos.
4. **Medir:** ArcFace `w600k_mbf.onnx` (buffalo_s da InsightFace, 13 MB,
   licença não comercial, fora do Git) pelo `cv2.dnn`. Alinha o rosto em 112x112
   pelos 5 pontos e devolve 512 números.
5. **Nota por pessoa:** cosseno contra cada foto da galeria; a nota da pessoa é
   a da foto mais parecida (`ARENA_TOPK=1`; com 3, a média das 3 melhores).
6. **Rastreador:** cola o rosto no mais próximo do quadro anterior. Rosto que
   muda mais de **1,6x de largura** é outra trilha (`TAMANHO_MAX`): achado num
   log em que um estranho de 54 px sumiu e o Samuel entrou no mesmo ponto com
   179 px e herdou a trilha.

## O juiz (decide por trilha, não por quadro)

Limiares do ArcFace (padrão): `ARENA_LIMIAR_ARCFACE=0.34`,
`ARENA_LIMIAR_BAIXO_ARCFACE=0.26`. (Os do SFace são outros: o limiar é por
motor, e a galeria diz o motor.)

- **AUTORIZADO:** pelo menos **3 leituras boas**, média ≥ 0,34, folga ≥ 0,05
  sobre o segundo nome e maioria dos votos.
- **DESCONHECIDO:** pelo menos **5 leituras** e média < 0,26.
- **No meio:** "analisando", até **14 leituras**; aí quem não foi autorizado
  com folga vira desconhecido (na dúvida, alerta).
- **Autorizado não cai para desconhecido** por virar o rosto.
- **Troca de trilha:** se as 8 últimas leituras boas de uma trilha autorizada
  nunca deram o nome dela e a média ficou abaixo de 0,26, a trilha recomeça ("o
  rosto deixou de ser X"); quem já foi identificado continua no placar.
- **Desconhecido que volta** com outra trilha é comparado com os já vistos e não
  vira segundo alerta se parecer ≥ 0,60 (`ARENA_MESMO_DESC_ARCFACE`). Duas
  trilhas vistas **no mesmo quadro** nunca são juntadas (são duas pessoas).
- **Desconhecido que depois é reconhecido** sai da conta de alertas.
- **Rosto pequeno demais** (abaixo do portão de tamanho) vira caixa **cinza fina
  sem texto** e fica fora da conta. De propósito: na arena o fundo é a plateia,
  e cada rosto dela viraria um alerta.

## A página (`http://IP_DA_CAIXA:8080`)

- Imagem com caixas: verde AUTORIZADO, vermelho DESCONHECIDO #n, âmbar
  analisando, cinza longe demais.
- Placar: autorizados X de 4, alertas de desconhecido, estado da câmera,
  leituras por segundo, tempo por quadro, últimos eventos.
- **Ctrl+C** no terminal imprime o resultado e grava
  `arena/resultados/*.json` (sem imagem).
- `--calibrar` imprime a nota de cada leitura com tamanho em px e quanto o
  rosto estava virado, e os rostos descartados com o motivo.
- `--preparo` mostra o **botão Cadastrar** (só no laboratório; ver
  `03-operacao-na-caixa.md`).
- Opcional e **desligado**: vídeo fluido pelo fluxo leve da câmera
  (`CAMERA_ARENA_VIDEO`). Na HAIZ o fluxo leve é H.265 e saiu corrompido;
  ficou desligado. Sem ele a página mostra os quadros analisados.

## A galeria

- `arena/galeria.json` (fora do Git), motor **arcface**, 512 números por
  amostra, **crus** (sem o giro da `CHAVE_BIO` do servidor da escola).
- Criada por fotos no PC (`cadastrar_fotos.py --motor arcface --galeria ...`) e
  completada pela câmera da arena com a **passada** (`cadastrar.py --acrescentar`
  ou o botão). Amostra com cosseno < 0,25 contra a média da pessoa fica de fora
  (outra pessoa na frente da câmera).
- `galeria.py conferir`: cada foto contra a galeria sem ela, como o juiz faz.
- Reserva SFace: `arena/galeria-sface.json` (no PC), com limiares 0,45 / 0,38.
