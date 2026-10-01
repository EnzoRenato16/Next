/* A rede de queda tem de FALAR na taxa de quadros da caixa — roda com:
 *
 *     node testes/piso-rede.mjs
 *
 * Nao precisa do servidor: e so conta, em Python puro.
 *
 * POR QUE ISTO EXISTE. A rede de queda so e chamada quando cabem N amostras na
 * janela de 1 segundo, e esse N era 8, fixo, copiado do navegador. O navegador
 * roda perto de 30 quadros por segundo e 8 cabem com folga. A AIBOX entrega
 * 6,7 analises por segundo — 6,7 amostras NUNCA chegam a 8 em 1 segundo.
 *
 * O resultado nao foi um erro: foi SILENCIO. A nota da rede ficava 0.00 em
 * cima de toda pessoa, o tempo todo, e 0.00 e exatamente o numero que a rede
 * da para quem esta em pe. O defeito era identico ao funcionamento normal na
 * tela, e so apareceu olhando ANALISE/S = 6.7 ao lado de QUEDA_AMOSTRAS = 8,
 * com a caixa ja ligada na camera da sala do laboratorio.
 *
 * Nenhum teste pegava porque todos rodavam a 30 quadros por segundo, que e
 * justamente a taxa em que o numero fixo esta certo.
 *
 * As tres perguntas aqui:
 *
 *  1. a 6,7/s (a caixa de verdade) a rede FALA, e a nota de uma queda sobe;
 *  2. a 30/s o piso continua 8, bit a bit igual ao navegador — e por isso que
 *     testes/aibox.mjs nao muda;
 *  3. o piso nunca desce de QUEDA_PISO, por mais lenta que a maquina esteja:
 *     abaixo disso as duas entradas que dividem por tempo viram ruido.
 */
import { spawnSync } from 'node:child_process';

const py = spawnSync('python3', ['testes/piso_rede_lado.py'], { encoding:'utf-8' });
process.stdout.write(py.stdout);
if(py.status !== 0) process.stderr.write(py.stderr || '');
process.exit(py.status === 0 ? 0 : 1);
