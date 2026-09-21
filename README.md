# Next

Projeto **Auditix IA** (grupo 11, 2ECR) — Desafio DATEN × FIAP, "Antes do NEXT".

Quatro produtos que partem da mesma tese: **IA na borda que gera prova
auditável**, com um enquadramento ético que não muda de página para página —
*alerta não é acusação*.

---

## Como rodar

O navegador não fala com PostgreSQL. Quem serve as páginas e conversa com o
banco é o `servidor.py`:

```bash
uv run servidor.py           # http://127.0.0.1:8000
```

| Endereço | O que é |
|---|---|
| `/` | **Sala auditada** — câmera ao vivo, três camadas de visão. Grava eventos. |
| `/painel` | **Painel** — leitura do banco: integridade da cadeia, séries, mapa de calor. Não grava nada. |
| `/docs` | Swagger dos endpoints |

Sem `.env`, o servidor cai sozinho para SQLite local e avisa na tela. Copie
`.env.example` para `.env` e preencha a senha para usar o Postgres do `db-fiap`.

As outras páginas são arquivos soltos, abrem direto no navegador:
`auditix-portaria.html`, `svatech-dashboard.html`, `svatech-scanner.html`,
`index.html` (pitch).

O **EduVision** roda separado, no AIBOX — veja [`daten/README.md`](daten/README.md).

---

## O que tem aqui

| Arquivo | O que faz |
|---|---|
| `servidor.py` | API + cadeia de hash SHA-256 + Postgres com queda para SQLite |
| `auditix-sala.html` | Sala auditada: pose, rosto, assinatura de corpo, prova de vida, mapa de calor |
| `auditix-portaria.html` | Portaria: leitor de palma, com consentimento do responsável |
| `auditix-painel.html` | Painel de leitura servido em `/painel` |
| `svatech-dashboard.html` | Caixa-preta cirúrgica (OPME) |
| `svatech-scanner.html` | Leitor de patrimônio (código de barras / QR) |
| `views_powerbi.sql` | Visões agregadas para o Power BI — nunca a tabela crua |
| `testes/` | Testes das regras de visão — `node testes/<arquivo>.mjs` |
| `treino/` | Rede de detecção de queda: dados, treino e provas — [`treino/LEIA.md`](treino/LEIA.md) |
| `daten/` | EduVision: reconhecimento facial em Python no AIBOX |
| `SVATech_Health.md` | A tese do SVATech Health |

---

## Duas regras que atravessam o projeto

**Offline-first, com queda graciosa.** Postgres cai para SQLite, nuvem cai para
borda, e nenhuma página depende de CDN para desenhar. Demonstração que morre
porque a internet caiu é demonstração perdida.

**Medido, não achado.** A Sala mede três coisas, e não finge que são iguais:
**queda** por rede treinada em 4.509 clipes de um dataset público (revocação 89%
contra 60% da regra geométrica), **corrida** e **briga** por regra geométrica.
e **pedido de ajuda** por um humano segurando um botão, que é a única das
quatro sem falso positivo possível, porque não tem nada inferindo.
Todas têm cenários em `testes/`. Briga usa as features do DIFEM
([arXiv 2412.05386](https://arxiv.org/abs/2412.05386)) sem o classificador
treinado deles, porque ainda não temos dataset — então o painel escreve
`regra` ao lado do tipo, e o caminho para virar modelo é o
[RWF-2000](https://arxiv.org/abs/1911.05913). Quando algo não foi medido, o
código diz isso.

**E dá para medir na sua sala.** `CALIBRACAO=1` liga o registro de calibração:
cada corpo deposita uma amostra por segundo com os números crus da análise
— nota, distância ao treino, velocidade, inclinação — **mesmo quando nada
acontece**. Uma hora de aula vira a distribuição do que o sistema enxergou, e
`/api/calibracao` responde a pergunta que decide se isto serve numa escola:
*o quão perto do limiar as coisas chegaram num dia comum*. Planilha em
`/api/calibracao.csv`. Nenhuma imagem, nenhum rosto, nenhum nome — e as
amostras **não entram na cadeia de hash**, porque medir o que se viu não é
afirmar o que aconteceu.

**Evidência para conferência humana, nunca acusação automática.** Quem não é
reconhecido vira "Desconhecido pendente de validação", biometria tem prazo para
vencer, e o que vai para o Power BI é agregado — dá para ver onde a escola
aperta sem expor aluno por aluno.
