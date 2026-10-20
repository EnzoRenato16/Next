# Medições e decisões (tudo medido, nada estimado)

## Modelo de rosto: por que ArcFace e não SFace

| teste | SFace | ArcFace (w600k_mbf) |
|---|---|---|
| LFW, rosto de 96 px: donos aceitos com 0,1% de estranhos aprovados | 98,7% | 99,3% |
| LFW, rosto de 38 px: idem | 97,8% | 99,0% |
| LFW: maior nota de estranho | 0,40 | 0,34 (mediana 0,00) |
| Vídeo do Enzo (estranho) contra a galeria do grupo: pico | 0,40 | 0,24 |
| Vídeo do Samuel (dono) contra o Enzo: folga | +0,13 | +0,21 |

Decisão de 20/10: a galeria da arena é **ArcFace**, limiares 0,34 / 0,26. Com
o SFace o limiar teria de subir para 0,45 / 0,38 (o Enzo chegou a 0,40 contra
o Lucas e foi aceito como Lucas com 0,36).

## Galeria (`galeria.py conferir`, 21/10)

| pessoa | amostras | acertou | menor folga |
|---|---|---|---|
| Daniel | 7 | 7 de 7 | +0,50 |
| Lucas | 9 | 9 de 9 | +0,51 |
| Matheus | 9 | 9 de 9 | +0,53 |
| Samuel | 18 (12 fotos + 6 da passada) | 18 de 18 | +0,46 |

Par mais parecido entre pessoas diferentes: 0,29 (foto contra foto).

## Estranhos na câmera HAIZ (todas as rodadas de 20 e 21/10)

- **2.558 leituras boas de estranhos, 0 aprovados.**
- Pior leitura isolada: **0,27**. Pior média de 3 leituras seguidas: **0,24**.
  Pior média de 8: **0,23**. Limiar para autorizar: 0,34.
- Rodada 0550: 911 leituras, p99 0,21; uma pessoa sentada 2:40 deu **um**
  alerta só.

## Samuel na HAIZ (dono)

| situação | antes da passada | depois da passada |
|---|---|---|
| de frente | ~0,73 (0,61 a 0,77) | **0,75 a 0,82** |
| virado ~0,3 | | 0,72 a 0,76 |
| virado ~0,5 | 0,64 | 0,64 a 0,69 |
| virado 0,55 a 0,70 | mínimo 0,41 | |
| mais longe (131 a 143 px), virado 0,5 a 0,6 | | 0,45 a 0,52 |
| **atravessando andando de lado** | | **0,34 / 0,30 / 0,27** (ponto fraco) |

Autorizado na 2ª leitura, em menos de 1 s.

## Rosto virado (`ARENA_FRENTE`)

| virado | Samuel | maior estranho |
|---|---|---|
| até 0,35 | mediana 0,73 | 0,25 |
| 0,35 a 0,55 | mínimo 0,38 | 0,18 |
| 0,55 a 0,70 | mínimo 0,41 | 0,19 |
| 0,70 a 0,85 | 1/4 das leituras cai para 0,15 a 0,27 | 0,19 |

Decisão: **0,70**. Acima disso quem erra é o dono (alerta errado contra o
autorizado), não o estranho. De costas não há rosto: nenhum sistema facial
resolve.

## Velocidade

| situação | tempo por quadro | leituras/s |
|---|---|---|
| HAIZ, busca no quadro cheio | ~530 ms | ~1,9 |
| HAIZ, busca em 1280 | ~296 ms | ~3,2 |
| HAIZ madrugada, 1 pessoa | 118 a 163 ms | 5 a 6 |
| HAIZ com outros grupos usando a caixa | 400+ ms | ~2 |
| Intelbras .108 (H.265, sala inteira) | ~470 ms | ~2, com atraso crescente |

- O peso é decodificar 2880x1620 a 30/s na CPU, mais a busca de rosto. O
  juiz custa menos de 1 ms.
- **30 leituras por segundo não existe nesta CPU** com rosto em 4 MP. O que
  importa é decidir rápido: 3 leituras = menos de 1 s com a caixa livre.
- Tentado e desfeito: não medir de novo quem já foi decidido (a pessoa nova que
  ocupa o lugar herdava o nome; ensaio 4 de 4 virou 1 de 4).

## Decisões em aberto

- **Limiar 0,34 ou 0,30?** Com 0,30 ainda sobram 0,06 sobre o pior estranho
  (0,24 em 3 leituras), e o Samuel andando de lado passaria. Só decidir com os
  4 medidos andando na câmera da arena.
- **Juntar desconhecidos com 0,60 ou ~0,45?** Um alerta saiu com "mais
  parecido 0,50"; se era a mesma pessoa, 0,60 está alto.
- **`qtivdec`** (decodificação no hardware): entrega NV12 em memória comum ou
  GBM; o código agora pede a comum. Falta o teste na caixa.
- **NPU:** a caixa tem SNPE 2.12 e HTP V68. Caminho: converter YuNet e ArcFace
  para DLC quantizado com o SNPE SDK num PC Linux e validar as notas. Depois da
  final.
