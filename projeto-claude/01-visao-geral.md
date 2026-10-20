# Auditix IA: visão geral

## O projeto

Auditix IA é o projeto do **Grupo 11 (2ECR, FIAP)** no desafio **DATEN × FIAP
NEXT**. Em sala de aula, ele detecta **queda, corrida, briga e pedido de
ajuda** e deixa uma trilha auditável (cada evento vira uma linha de uma cadeia
de hash SHA-256). Roda numa **AI BOX** da DATEN (Qualcomm QCS6490, ARM, 8
núcleos, 7 GB, NPU Hexagon V68) ao lado da câmera.

- Repositório: `github.com/EnzoRenato16/Next`, branch de trabalho
  `claude/entender-projeto-0tgk9u`.
- O grupo passou para a final em **3º lugar (32/40)**. A banca elogiou aderência
  e pitch e rebaixou **viabilidade** para "Adequado": pediu custos,
  implantação, manutenção, escala, métricas técnicas e uma demonstração curta e
  confiável.

## A final

- **Sábado 24/10/2026, ARCA (Vila Leopoldina).** Estande A24 das 12h às 15h
  (obrigatório, faltar tira ponto). Concentração 16h a 16h30. **Arena 17h às
  17h45.** Premiação a partir das 18h.
- **O que vale nota é só a arena**, e a arena é **só identificação**: dizer quem
  está cadastrado e quem não está. Queda, corrida e briga não entram na nota
  final.
- **Até 5 minutos no total, setup incluído** (o guia sugere 2 de acesso e 3 de
  prova, sem prorrogação).
- O notebook é só terminal por **SSH** com o usuário do grupo. **O
  processamento tem de rodar na AI BOX.** AI BOX e câmeras são da organização:
  não mexer, sem `sudo`, sem mudar configuração.
- **Teste:** 4 cadastrados e 2 desconhecidos pelo guia (o professor falou em 3
  e 2; número final a confirmar). Um desconhecido é de outra equipe e um da
  plateia. Ordem e posição mudam. Só os autorizados previstos podem estar
  cadastrados; nada de ajuste manual nem treino na hora.
- **Ao final, mostrar:** autorizados identificados, alertas de desconhecido,
  estado das câmeras, latência e estabilidade. Erro não se esconde.
- **Não haverá internet**, só a do evento, instável.
- A AI BOX é recolhida na **quarta 21/10 à noite**.

## As pessoas

- **Na galeria (autorizados):** Lucas, Daniel, Samuel, Matheus.
- **Fora da galeria:** Enzo (opera o terminal) e Guilherme.

## A solução para a arena, em uma frase

Um programa só (`aibox/arena.py`, aberto por `bash aibox/arena.sh`) lê a câmera
em resolução cheia, acha rostos com **YuNet**, mede cada rosto com **ArcFace**
(512 números), compara com a galeria local dos 4 autorizados e decide **por
pessoa, não por quadro**, com várias leituras. A página
`http://IP_DA_CAIXA:8080` mostra a imagem, o placar, os alertas, o estado da
câmera e o tempo por quadro. Tudo dentro da caixa, sem internet.
