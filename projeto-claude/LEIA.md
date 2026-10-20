# Como montar o Projeto no Claude

1. Em claude.ai, crie um **Projeto** (por exemplo "Auditix IA, final NEXT").
2. Abra `00-INSTRUCOES-DO-PROJETO.md` e cole o conteúdo no campo
   **Instruções do projeto**.
3. Em **Conhecimento do projeto**, suba:
   - `01-visao-geral.md`
   - `02-arena-como-funciona.md`
   - `03-operacao-na-caixa.md`
   - `04-medicoes-e-decisoes.md`
   - `05-estado-e-pendencias.md`
   - `06-pitch-viabilidade-e-perguntas.md`
   - `07-seguranca-lgpd-e-limpeza.md`
4. Para o contexto técnico completo, suba também, da raiz do repositório:
   - `CLAUDE.md` (a memória técnica, com todas as armadilhas)
   - `ARENA-PASSO-A-PASSO.md` (guia do laboratório)
   - `aibox/arena.py` (o programa da arena, se for discutir código)

Nenhum destes arquivos tem senha. **Não suba** o `.env`, a galeria
(`arena/galeria.json`), fotos ou vídeos.

O `05-estado-e-pendencias.md` envelhece rápido: atualize-o (ou peça ao Claude
para atualizar) a cada etapa concluída.
