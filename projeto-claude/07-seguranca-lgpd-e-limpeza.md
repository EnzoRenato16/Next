# Segurança, LGPD e limpeza

## Senhas

- Senha de câmera e de SSH mora **só no `.env` da caixa**. Nunca no Git, em
  PDF, slide ou mensagem.
- A senha da HAIZ vai dentro do endereço (padrão Xiongmai). Os programas agora
  mostram o endereço com `password=***`.
- Senhas antigas aparecem no histórico do repositório e em mensagens: pedir ao
  professor que **troque as senhas do SSH e das câmeras** depois do evento.

## Biometria

- **Nenhuma imagem de rosto é gravada** pelo modo arena; o resultado em
  `arena/resultados/*.json` não tem imagem.
- A galeria `arena/galeria.json` guarda os 512 números de cada amostra **crus**
  (a chave de giro teria de morar na mesma caixa, então não protegeria nada).
  Por isso: só os 4 autorizados, e **apagar depois do evento**.
- Fotos (`fotos-cadastro/`), vídeos (`*.mp4 *.mov *.avi *.mkv`) e a galeria
  estão no `.gitignore`: o repositório é público.

## LGPD (resposta pronta)

Em ago/2026 a ANPD suspendeu o reconhecimento facial de alunos da rede
estadual do Paraná (Nota Técnica nº 4/2026) por falta de necessidade,
proporcionalidade e alternativa menos invasiva. A resposta do Auditix:
finalidade é segurança, não chamada; consentimento do responsável (art. 14);
tudo processado dentro da sala, offline; quem não se cadastrou não fica
guardado; o rosto não vai para a nuvem.

## Limpeza

**Antes de sair do laboratório (quarta):**

- `bash aibox/servico.sh remover` na caixa.
- Copiar `arena/galeria.json` da caixa para o pen drive.
- No PC do laboratório (usuário compartilhado `labsfiap`): apagar
  `fotos-cadastro` e os vídeos.

**Depois do evento (sábado):**

- Apagar `arena/` da caixa (`rm -r ~/auditix/arena`) e do PC.
- Apagar `.env.bak-haiz` da caixa (tem a senha da câmera).
- Apagar a galeria do pen drive.
