# Estado e pendências (atualizado em 21/10/2026, manhã)

## Feito

- Modo arena completo na caixa (`bash aibox/arena.sh`), com página, placar,
  alertas, estado da câmera, resultado gravado e 52 testes do juiz.
- Galeria ArcFace dos 4 por fotos, `conferir` 100%.
- Código, modelos e galeria na caixa. Câmera HAIZ configurada no `.env`.
- **Samuel:** passada feita (12 → 18 amostras), calibrado de frente, de lado e
  andando.
- 2.558 leituras de estranhos na HAIZ, 0 aprovados.
- Correções vindas dos logs: juntar desconhecidos por sobreposição, rosto que
  muda de tamanho vira outra trilha, rosto virado até 0,70, rosto pequeno cinza
  e fora da conta, senha escondida na tela, botão Cadastrar com `--preparo`.

## Falta (antes da quarta 21/10 à noite)

1. **Lucas:** a passada foi recusada (colheu outra pessoa, notas 0,01 a 0,09).
   Calibrar com ele sozinho e de frente: se der "Lucas ≥ 0,4", refazer a passada
   com ele mais perto (botão); se der outro nome ou < 0,2, as fotos dele na
   galeria não batem e é preciso refazer o cadastro dele.
2. **Daniel e Matheus:** passada e calibrar (o roteiro do Samuel, incluindo
   atravessar andando).
3. `galeria.py conferir` depois das passadas.
4. **Decidir o limiar** (0,34 ou 0,30) com os logs dos 4 andando.
5. **Ensaio cronometrado de 5 minutos:** do notebook fechado ao placar, os 4 em
   ordem misturada mais 1 ou 2 estranhos; conferir 4 de 4 e um alerta por
   estranho.
6. Testar o `qtivdec` (uma vez) e decidir se fica ligado.
7. Antes de ir embora:
   - `bash aibox/servico.sh remover` (a caixa não sobe o serviço da sala sozinha);
   - copiar `arena/galeria.json` **da caixa** para o pen drive (é a mais nova);
   - no PC do laboratório, apagar `fotos-cadastro` e os vídeos.

## Perguntar ao professor

- A caixa da arena é esta mesma? Qual o IP dela e da câmera no evento?
- A câmera da arena é a HAIZ ou a Intelbras? Quantas câmeras?
- 3 ou 4 autorizados? A que distância e altura as pessoas ficam? Por onde andam?
- O notebook liga por cabo ou Wi-Fi? (levar o adaptador Realtek)
- A caixa vai estar **só com o nosso processo** no nosso turno? (hoje os grupos
  05 e 06 ocupavam 3 núcleos)
- Pedir a **troca das senhas** do SSH e das câmeras depois do evento (apareceram
  em mensagens e no histórico do repositório).

## No dia (sábado)

1. Ligar o notebook na rede da caixa e entrar por SSH.
2. `cd ~/auditix && bash aibox/arena.sh` (**sem** `--preparo` e sem `--calibrar`).
3. Abrir `http://IP_DA_CAIXA:8080` e projetar.
4. Os autorizados entram e olham para a câmera por ~1 s.
5. No fim, Ctrl+C e mostrar o resultado. Erro não se esconde.
6. Depois do evento: apagar `arena/` da caixa e do PC.
