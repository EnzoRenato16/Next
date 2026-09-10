# Next

Projeto **Auditix AI** (grupo11) — Desafio DATEN × FIAP, "Antes do NEXT".
Marca **SVATech**.

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
| `daten/` | EduVision: reconhecimento facial em Python no AIBOX |
| `SVATech_Health.md` | A tese do SVATech Health |

---

## Duas regras que atravessam o projeto

**Offline-first, com queda graciosa.** Postgres cai para SQLite, nuvem cai para
borda, e nenhuma página depende de CDN para desenhar. Demonstração que morre
porque a internet caiu é demonstração perdida.

**Evidência para conferência humana, nunca acusação automática.** Quem não é
reconhecido vira "Desconhecido pendente de validação", biometria tem prazo para
vencer, e o que vai para o Power BI é agregado — dá para ver onde a escola
aperta sem expor aluno por aluno.
