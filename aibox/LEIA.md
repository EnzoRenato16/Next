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

## Os arquivos

| arquivo | o que faz |
|---|---|
| `medidas.py` | COCO-17 → geometria. Importa as 12 características do treino |
| `rede.py` | os 113 pesos, lidos de `treino/modelo.json` |
| `regras.py` | queda, corrida e briga. Mesmos limiares do navegador |
| `trilhas.py` | quem é quem entre um quadro e o outro |
| `olho.py` | quem enxerga: YOLO (caixa) ou MediaPipe (PC) |
| `custo.py` | CPU e memória, lidos do `/proc`, sem dependência nova |
| `sala.py` | o laço |
