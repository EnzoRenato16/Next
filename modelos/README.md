# Modelos servidos ao navegador

A Sala (`auditix-sala.html`) roda a camada de **objeto suspeito** dentro do
navegador, com ONNX Runtime Web. O modelo é servido pelo `servidor.py` em
`/modelo/objeto-suspeito.onnx`, lendo o arquivo desta pasta.

Junto com ele vai o **ONNX Runtime Web**, em `modelos/ort/`, servido em `/ort/`.
Nenhum dos dois está no repositório: são ~23 MB, e o modelo carrega
**AGPL-3.0**. Baixe uma vez, da raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File baixar-modelos.ps1   # Windows
```
```bash
bash baixar-modelos.sh                                        # Linux / macOS
```

## Por que o runtime é servido daqui, e não de CDN

Duas razões, e a segunda é técnica:

1. A apresentação não pode depender da internet da escola.
2. A inferência roda num **worker**, para não travar o vídeo — e o navegador
   **bloqueia worker criado a partir de outra origem**. Servido da mesma
   origem, funciona.

## A versão do runtime não é livre — 1.22.0, e foi medida

Reproduzido no Chromium, com este modelo:

| Versão | Resultado |
|---|---|
| 1.19.2 | falha ao criar a sessão (`33574344`, sem mensagem) |
| 1.20.1 | falha ao criar a sessão (`33594080`, sem mensagem) |
| **1.22.0** | **sessão em 453 ms, inferência em 558 ms, saída correta** |

As versões antigas erram com um número cru de exceção do WebAssembly, sem
mensagem nenhuma. Se um dia aparecer isso na tela de novo, é este o caminho:
subir a versão, não mexer no modelo.

Sem o arquivo, **nada quebra**: o servidor devolve 404, a Sala não liga a
camada e escreve isso na tela. É de propósito.

## Dois modelos, e a escolha é de procedência

`baixar-modelos.sh coco` (padrão) ou `baixar-modelos.sh armas`. A Sala descobre
qual está instalado pelo número de classes da saída.

| | `coco` (padrão) | `armas` |
|---|---|---|
| O que detecta | **faca** | **pistola e faca** |
| Treino | COCO, 118 mil imagens revisadas | dataset anônimo de Colab |
| Desempenho publicado | sim | **nenhum** |
| Adoção | referência da área | 0 downloads, sem model card |
| Entrada | float16 | float32 |
| Tamanho | 6,4 MB | 12 MB |

O `armas` é o único que detecta arma de fogo — o COCO não tem essa classe. Mas
ele é obra de um treino de Colab sem nenhuma métrica publicada: não dá para
dizer o que ele acerta. Para **lâmina**, o COCO é a aposta mais segura.

Do COCO a Sala usa **só** a faca (índice 43). Tesoura (76) e taco de beisebol
(34) também estão lá e também são objetos de escola — ficam de fora de
propósito: cada classe a mais é uma fonte a mais de alarme falso.

> A classe 0 do COCO é **pessoa**. Ler um modelo do COCO com a tabela do modelo
> de armas transformaria todo mundo na sala em "arma de fogo". Por isso a
> escolha é pelo número de classes, e `testes/objeto-suspeito.mjs` trava isso.

## Como medir na sua sala

A faixa embaixo do vídeo mostra a **maior confiança** de cada leitura, mesmo
abaixo do limiar. Aponte o objeto e leia:

- **perto de 0,60 ou acima** — funciona; se não alerta, é o `ARMA_CONF`.
- **entre 0,05 e 0,40** — o modelo vê algo; dá para discutir baixar o limiar,
  sabendo que isso aumenta alarme falso.
- **perto de 0** — o modelo não reconhece aquele objeto. Nenhum ajuste resolve.

## O que ele é, conferido no arquivo

| | |
|---|---|
| Entrada | `images`, `[1, 3, 640, 640]`, RGB normalizado em 0..1 |
| Saída (`armas`) | `output0`, `[1, 6, 8400]` — 4 de caixa + 2 de classe, **sem NMS** |
| Saída (`coco`) | `output0`, `[1, 84, 8400]` — 4 de caixa + 80 de classe, **sem NMS** |
| Licença | AGPL-3.0 (Ultralytics) nos dois |

A decodificação e a supressão de não-máximos estão escritas à mão na Sala e em
`daten/app/armas.py` — de propósito, para não arrastar a dependência do
Ultralytics só para ler um tensor.

**A AGPL é viral.** Para um trabalho acadêmico com repositório público, tudo
bem. Para virar produto fechado, não serve: aí é treinar um modelo próprio ou
usar um com licença permissiva.

## Velocidade — o que foi medido

Uma inferência, neste container, com 4 núcleos:

| | |
|---|---|
| 1 thread | **453 ms** |
| 2 threads | 244 ms |
| **4 threads** | **152 ms** |

Três vezes mais rápido, e é a diferença entre "demora" e "aparece". Só funciona
com `SharedArrayBuffer`, que o navegador libera quando o servidor manda
`Cross-Origin-Opener-Policy` e `Cross-Origin-Embedder-Policy` — o `servidor.py`
agora manda. A Sala lê `crossOriginIsolated` do próprio navegador em vez de
supor: pedir várias threads sem isolamento MATA o carregamento, com um número
cru de exceção e nenhuma mensagem.

`credentialless` foi escolhido de propósito. Com `require-corp`, os arquivos de
CDN (MediaPipe, face-api, fontes) precisariam de um cabeçalho que não
controlamos, e a página inteira quebraria.

> **Se algo de CDN parar de carregar por causa disso**, suba com
> `SEM_ISOLAMENTO=1 uv run servidor.py`. A camada volta a uma thread e continua
> funcionando, só mais devagar. Perder a Sala inteira por causa dela seria um
> mau negócio. Este é o único ponto que não consegui verificar em ambiente com
> CDN acessível.

A inferência roda num **worker**, e continua rodando: custava 500 ms de vídeo
travado antes, custa 16 ms agora, e é o que mantém a câmera fluida.

**WebGPU foi testado e não entrou.** Deu 2870 ms contra 468 ms do wasm — mas a
GPU do ambiente de teste é emulada por software, então esse número não vale
para uma máquina com GPU de verdade. Ficou de fora porque são mais 21 MB de
download e um ganho que ninguém mediu. É o caminho óbvio se um dia a velocidade
voltar a incomodar.

## Medido, não estimado

Numa CPU de container, uma inferência levou **46 ms**. Com 8400 caixas de ruído
aleatório puro, **nenhuma** passou do limiar de 0.60 — o limiar alto está
fazendo o trabalho dele.
