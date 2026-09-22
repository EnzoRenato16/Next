# Auditix IA dentro da AIBOX

O mesmo sistema, sem navegador.

```
câmera --RTSP--> OpenCV --> YOLO11-pose (ONNX Runtime) --> 17 pontos COCO
       --> as 12 características --> a rede de queda --> POST /api/evento
```

É o desenho que o professor do desafio descreveu, com o nosso cérebro no meio.

## Por que isto coube tão bem

A rede de queda foi treinada no **Fall Vision**, que traz os pontos no formato
**COCO-17**. O **YOLO11-pose entrega COCO-17 nativamente**. E dos 33 pontos do
MediaPipe, a versão do navegador já usava justamente esses 17.

Ou seja: o modelo não está sendo adaptado para um detector diferente — **está
voltando para o formato em que nasceu.**

E o cérebro não foi reescrito. As 12 características vêm de `treino/extrair.py`
e os 113 pesos de `treino/modelo.json`, os mesmos arquivos do treino e do
navegador. Não existe um segundo modelo para divergir do primeiro.

**Sai de cena o go2rtc.** O navegador precisava dele porque o Chrome não abre
RTSP. O OpenCV abre. Uma peça a menos para falhar na apresentação.

## Rodar

No PC, antes de ter a caixa — usa o mesmo detector do navegador:

```bash
uv run aibox/sala.py --olho mediapipe --camera 0 --mostrar
```

Na caixa:

```bash
uv run aibox/sala.py --mostrar
```

Sessão de medição que para sozinha:

```bash
uv run aibox/sala.py --mostrar --segundos 1800
```

## Configuração (no `.env`, ao lado do `servidor.py`)

```
CAMERA_RTSP=rtsp://usuario:senha@192.168.0.50:554/stream2
SERVIDOR=http://127.0.0.1:8000
LOCAL_CAMERA=sala-12
OLHO=yolo
MODELO=yolo11n-pose.onnx
CALIBRACAO=1
```

**A senha da câmera mora no `.env` e em mais lugar nenhum.** O `.env` não vai
para o git, e é para isso que ele existe.

Use o **substream** da câmera, não o principal. Abrir conexão a mais numa câmera
que já está servindo a plataforma é pedir para ela engasgar no meio da
demonstração — e a análise não ganha nada com 4K, os pontos do corpo saem iguais.

## O que está provado, e o que não está

`node testes/aibox.mjs` roda o **mesmo cenário nos dois lados**: o `analisar` de
verdade no Chrome e o `Rebanho` de verdade em Python.

Resultado medido: `altura`, `ang`, `baixo`, `prop` e `vel` batem **bit a bit**
(diferença `0.00e+0`), a taxa de quadros medida é idêntica, e numa queda os dois
armam **no mesmo quadro**.

Três diferenças conhecidas, declaradas em vez de escondidas:

| o quê | navegador | caixa | efeito |
|---|---|---|---|
| corte de confiança | 0,40 | **0,30** (o do treino) | régua diferente num ponto entre os dois |
| precisão dos pesos | 5 algarismos | **precisão dupla** | ~1e-4 na nota, contra limiar 0,50 |
| folga da caixa | 6% / 4% | sem folga (como o treino) | `prop` ~3,7% menor |

Nos três casos a caixa está **mais perto do treino** que o navegador.

**O que NÃO está provado** e só a caixa na mão resolve: se o hardware aguenta a
taxa de quadros, se o RTSP se comporta na rede da escola, e se o YOLO coloca os
pontos no mesmo lugar que o MediaPipe. Os dois falam COCO-17, mas são modelos
diferentes — pode haver diferença sistemática. A medição de calibração existe
justamente para responder isso com número em vez de opinião.

## Desempenho: o que foi medido e o que dá para esperar

Na caixa do desafio (Qualcomm QCS6490, ARM, 8 núcleos, 7 GB):

| configuração | quadros/s | modelo | nossa análise |
|---|---|---|---|
| PyTorch, entrada 640 | 1,5 | 600 ms | 0,2 ms |
| PyTorch, entrada 320 | 3,1 | 300 ms | 0,0 ms |
| **ONNX Runtime, entrada 320** | **8,7** | **~110 ms** | 0,5 ms |

Quase **6× em relação ao ponto de partida**, no mesmo hardware e com o mesmo
modelo — só trocando como ele é executado.

A conclusão mais forte está na última coluna: **a nossa parte custa meio
milissegundo.** Todo o peso é o modelo de pose.

### Sobre a meta de 30 quadros por segundo

Sendo honesto: **30/s com este modelo em CPU ARM é improvável.** A conta é
direta — 30/s dá 33 ms por quadro, e ainda é preciso decodificar o vídeo,
casar as trilhas e desenhar. Sobrariam uns 25 ms para uma inferência que hoje
leva 110. São 4,4× e não há uma manopla só que dê isso.

O que existe, em ordem de retorno:

1. **Descobrir o teto da câmera primeiro.** `$P aibox/medir.py` mede isso
   separado. Se o substream entrega 15/s, **30/s é impossível por mais rápido
   que o modelo fique**, e a correção é no site da câmera, não no código.
2. **Entrada menor** (`CAM_IMGSZ` no `.env`): 256 ou 192. Ganho grande, preço
   real — pessoa longe passa a ser perdida.
3. **INT8** (`$P aibox/quantizar.py`): converte e **mede**; se não adiantar,
   ele mesmo avisa para não usar.
4. **O NPU (Hexagon) da Qualcomm.** É o único caminho que daria 30/s de
   verdade, e exige o *execution provider* QNN do ONNX Runtime — que a caixa
   não tem instalado. É projeto à parte, não ajuste.

### E quanto é suficiente de verdade

A rede de queda exige **8 amostras dentro de 1 segundo**, e as 12
características são normalizadas pela taxa MEDIDA (`fps` em
`treino/extrair.py`) — então ela não depende de ser 30. Uma queda dura uns 400
ms: a 15/s são 6 amostras dentro do tombo, e a 8,7/s são 3.

Ou seja: **8,7 já funciona, e 15 seria confortável.** O número 30 vem do
dataset de treino, não de uma exigência do detector.

## Os arquivos

| arquivo | o que faz |
|---|---|
| `medidas.py` | COCO-17 → geometria. Importa as 12 características do treino |
| `rede.py` | os 113 pesos, lidos de `treino/modelo.json` |
| `regras.py` | queda, corrida e briga. Mesmos limiares do navegador |
| `trilhas.py` | quem é quem entre um quadro e o outro |
| `olho.py` | quem enxerga: YOLO (caixa) ou MediaPipe (PC) |
| `custo.py` | CPU e memória, lidos do `/proc`, sem dependência nova |
| `vivo.py` | a imagem ao vivo por MJPEG, com o esqueleto |
| `sala.py` | o laço |
| `medir.py` | separa o teto da câmera do teto do modelo |
| `quantizar.py` | tenta INT8 e mede se adiantou |
