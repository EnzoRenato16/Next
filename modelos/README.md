# Modelos servidos ao navegador

A Sala (`auditix-sala.html`) roda a camada de **objeto suspeito** dentro do
navegador, com ONNX Runtime Web. O modelo é servido pelo `servidor.py` em
`/modelo/objeto-suspeito.onnx`, lendo o arquivo desta pasta.

Ele **não está no repositório**, por dois motivos: tem 12 MB, e carrega
**AGPL-3.0**. Baixe uma vez:

```bash
curl -L -o modelos/objeto_suspeito_yolov8.onnx \
  https://huggingface.co/Hadi959/weapon-detection-yolov8/resolve/main/best.onnx
```

No Windows (PowerShell):

```powershell
curl.exe -L -o modelos\objeto_suspeito_yolov8.onnx `
  https://huggingface.co/Hadi959/weapon-detection-yolov8/resolve/main/best.onnx
```

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
