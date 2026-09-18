/* O botão de pedir ajuda — roda com:  node testes/pedir-ajuda.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ESTE TESTE PRECISA DO NAVEGADOR DE VERDADE.
 *
 * O valor do botão está inteiro na INTERAÇÃO, não na requisição. Um teste que
 * só chamasse POST /api/evento com tipo `pedido_ajuda` passaria sem provar nada
 * do que importa: que um clique de raspão não chama socorro, que segurar chama,
 * e que digitar num campo não chama. Essas três coisas só existem no evento de
 * ponteiro e de teclado, então o teste roda no Chrome.
 *
 * O QUE ELE COBRA, em ordem de importância:
 *
 *  1. FALHA EM VOZ ALTA. É a mais importante e a menos óbvia. Todo o resto do
 *     sistema falha em silêncio de propósito. Aqui, silêncio é mentira: quem
 *     aperta e não vê nada vai embora achando que pediu socorro. O teste
 *     derruba o servidor no meio do caminho e cobra que a tela diga isso.
 *  2. Clique curto não dispara. Dois enganos e a coordenação para de acreditar
 *     no alerta, e aí a queda de verdade morre junto com a confiança.
 *  3. Segurar dispara, e vira linha na cadeia de hash.
 *  4. Digitar "a" num campo não chama socorro.
 *  5. O servidor RECUSA imagem para este tipo, mesmo ele sendo grave. A recusa
 *     mora no servidor porque combinar com o navegador não vale nada.
 */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const SEGURAR = 900;                 // o mesmo AJUDA_SEGURAR de auditix-sala.html

const CAMINHOS = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'];
const executablePath = CAMINHOS.find(existsSync);

let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};

const contar = async () => {
  const r = await fetch(BASE + '/api/eventos?limite=200');
  const j = await r.json();
  const lista = Array.isArray(j) ? j : (j.eventos || j.itens || []);
  return lista.filter(e => e.tipo_evento === 'pedido_ajuda').length;
};

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE + ' (uv run servidor.py)');
       process.exit(1); }

const nav = await chromium.launch({ executablePath, args:['--no-sandbox','--no-proxy-server'] });
const p = await nav.newPage();
const erros = [];
p.on('pageerror', e => erros.push(e.message));
await p.goto(BASE + '/', { timeout:20000 });
await p.waitForSelector('#btn-ajuda');

/* A câmera NÃO é aberta em nenhum momento deste teste, e isso é parte do que
   se prova: o botão existe justamente para os casos em que a câmera não ajuda,
   então exigir `rodando` mataria o motivo dele existir. */

const antesDeTudo = await contar();

/* ---- 2. clique curto não dispara ---------------------------------------- */
await p.click('#btn-ajuda');                       // clique comum, instantâneo
await p.waitForTimeout(600);
ok('clique rápido não chama socorro', await contar() === antesDeTudo,
   'eventos antes ' + antesDeTudo + ', depois ' + await contar());

/* E soltar no meio do caminho também não. */
const cx = await p.$eval('#btn-ajuda', b => {
  const r = b.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; });
await p.mouse.move(cx[0], cx[1]);
await p.mouse.down();
await p.waitForTimeout(SEGURAR * 0.5);
await p.mouse.up();
await p.waitForTimeout(600);
ok('soltar na metade do tempo não chama socorro', await contar() === antesDeTudo);

/* ---- 4. digitar num campo não dispara ------------------------------------ */
/* O diálogo de cadastro precisa estar ABERTO, e isso não é detalhe: os únicos
   campos de texto da página moram dentro dele. Na primeira versão o teste
   chamava focus() no campo escondido, o foco não saía do body, e ele acusava a
   guarda de teclado de estar quebrada quando a quebrada era ele.
   Por isso a linha seguinte é uma PRÉ-CONDIÇÃO cobrada, não uma suposição: se
   o foco não estiver no campo, o teste falha dizendo isso em vez de julgar o
   código por um cenário que nunca montou. */
await p.$eval('#dlg-pes', d => d.showModal());
await p.focus('#pe-nome');
const focado = await p.evaluate(() => document.activeElement.id);
ok('pré-condição: o cursor está mesmo dentro do campo de nome',
   focado === 'pe-nome', 'activeElement = #' + focado);

await p.keyboard.down('a');
await p.waitForTimeout(SEGURAR * 1.5);
await p.keyboard.up('a');
await p.waitForTimeout(500);
ok('segurar "a" escrevendo o nome de um aluno não chama socorro',
   await contar() === antesDeTudo,
   'eventos de ajuda: ' + await contar());
await p.$eval('#dlg-pes', d => d.close());

/* ---- 3. segurar dispara, e vira linha na cadeia -------------------------- */
const elosAntes = (await (await fetch(BASE + '/api/verificar')).json()).total;
await p.mouse.move(cx[0], cx[1]);
await p.mouse.down();
await p.waitForTimeout(SEGURAR + 350);
await p.mouse.up();
await p.waitForTimeout(900);

const depois = await contar();
ok('segurar até o fim chama socorro', depois === antesDeTudo + 1,
   'eventos de ajuda: ' + antesDeTudo + ' -> ' + depois);

const cadeia = await (await fetch(BASE + '/api/verificar')).json();
ok('o pedido vira elo na cadeia, e a cadeia continua íntegra',
   cadeia.integra && cadeia.total === elosAntes + 1,
   'elos ' + elosAntes + ' -> ' + cadeia.total + ', íntegra: ' + cadeia.integra);

const texto = await p.innerText('body');
ok('a tela confirma que foi registrado', /ajuda pedida|registrad/i.test(texto));

/* ---- 5. o servidor recusa imagem para este tipo -------------------------- */
const eventos = await (await fetch(BASE + '/api/eventos?limite=200')).json();
const lista = Array.isArray(eventos) ? eventos : (eventos.eventos || eventos.itens || []);
const oPedido = lista.find(e => e.tipo_evento === 'pedido_ajuda');
const rFoto = await fetch(BASE + '/api/foto', { method:'POST',
  headers:{'Content-Type':'application/json'},
  body: JSON.stringify({ evento_id: oPedido.id,
                         imagem:'data:image/jpeg;base64,' + 'A'.repeat(200) }) });
ok('o servidor recusa imagem de pedido de ajuda, mesmo ele sendo grave',
   rFoto.status === 403, 'HTTP ' + rFoto.status + ' — ' +
   (await rFoto.text()).slice(0, 80));
ok('e o evento não ficou com foto', oPedido.tem_foto === 0 || !oPedido.tem_foto);

/* ---- 1. falha em voz alta ------------------------------------------------ */
/* Derruba a rota no navegador para simular servidor caído. Esta é a parte que
   separa este botão de um enfeite: a pessoa PRECISA saber que ninguém foi
   avisado, para chamar ajuda por outro meio. */
await p.route('**/api/evento', r => r.abort('failed'));
const antesDaQueda = await contar();
await p.mouse.move(cx[0], cx[1]);
await p.mouse.down();
await p.waitForTimeout(SEGURAR + 350);
await p.mouse.up();
await p.waitForTimeout(900);

ok('com o servidor fora, nada é gravado', await contar() === antesDaQueda);
const txtFalha = await p.innerText('body');
ok('e a tela DIZ que não foi registrado, em vez de calar',
   /não registrado|nao registrado/i.test(txtFalha),
   txtFalha.match(/N[ÃA]O REGISTRADO[^\\n]{0,60}/i)?.[0] || '(nada na tela)');
ok('e manda chamar ajuda por outro meio',
   /outro meio/i.test(txtFalha));

ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));

await nav.close();
console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
