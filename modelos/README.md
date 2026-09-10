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

## O que ele é, conferido no arquivo

| | |
|---|---|
| Entrada | `images`, `[1, 3, 640, 640]`, RGB normalizado em 0..1 |
| Saída | `output0`, `[1, 6, 8400]` — 4 de caixa + 2 de classe, **sem NMS** |
| Classes | `0: pistol`, `1: knife` |
| Licença | AGPL-3.0 (Ultralytics), autor não declarou licença própria |

A decodificação e a supressão de não-máximos estão escritas à mão na Sala e em
`daten/app/armas.py` — de propósito, para não arrastar a dependência do
Ultralytics só para ler um tensor.

**A AGPL é viral.** Para um trabalho acadêmico com repositório público, tudo
bem. Para virar produto fechado, não serve: aí é treinar um modelo próprio ou
usar um com licença permissiva.

## Medido, não estimado

Numa CPU de container, uma inferência levou **46 ms**. Com 8400 caixas de ruído
aleatório puro, **nenhuma** passou do limiar de 0.60 — o limiar alto está
fazendo o trabalho dele.
