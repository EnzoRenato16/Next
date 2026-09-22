/* A plataforma de cadastro de rostos — roda com:  node testes/cadastro.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. O cadastro morava no localStorage de UM navegador: outra
 * máquina, outro navegador ou cache limpo e some tudo. Numa escola, quem
 * cadastra na secretaria e quem assiste na coordenação não são a mesma tela.
 * Agora o cadastro é do servidor, e o que este arquivo protege é isso.
 *
 * O QUE ELE NÃO PROVA: que a prova de vida funciona. Abrir a boca e virar a
 * cabeça precisam de um rosto de verdade na frente da câmera, e um rosto
 * sintético que passasse nesse teste seria exatamente o que a prova de vida
 * existe para barrar. Isso se testa com gente, não com código.
 */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const desc = () => Array.from({length:128}, () => Math.random());
const post = (rota, corpo) => fetch(BASE + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo) });

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

const NOME = 'Teste ' + Date.now();

/* ---- 1. o servidor guarda, lista e devolve ------------------------------ */
const r1 = await post('/api/cadastro', { nome: NOME, descritores:[desc(), desc(), desc()] });
ok('um cadastro é aceito e volta com o prazo', r1.ok, 'HTTP ' + r1.status);
const lista = await (await fetch(BASE + '/api/cadastros')).json();
const meu = lista.cadastros.find(c => c.nome === NOME);
ok('e aparece na lista com o número de amostras',
   !!meu && meu.amostras === 3, JSON.stringify(meu));

/* ---- 2. O DESCRITOR NÃO SAI DE GRAÇA ------------------------------------ */
/* É o dado biométrico. Quem monta a tela de gerenciamento precisa de nome e
   prazo; só quem vai RECONHECER precisa dos números do rosto. */
ok('a listagem comum NÃO traz os descritores',
   meu && meu.descritores === undefined);
const comDesc = await (await fetch(BASE + '/api/cadastros?descritores=1')).json();
const cheio = comDesc.cadastros.find(c => c.nome === NOME);
ok('e traz quando explicitamente pedidos, com 128 números cada',
   cheio.descritores.length === 3 && cheio.descritores.every(d => d.length === 128),
   cheio.descritores[0].length + ' números');

/* ---- 3. descritor torto é recusado --------------------------------------- */
/* Um descritor de tamanho errado não dá erro na hora de comparar: dá uma
   distância qualquer, e a pessoa simplesmente nunca é reconhecida. Falha
   silenciosa é a pior de diagnosticar, então a recusa é na entrada. */
const r3 = await post('/api/cadastro', { nome:'Torto', descritores:[[1,2,3]] });
ok('descritor com tamanho errado é recusado na entrada', r3.status === 400,
   'HTTP ' + r3.status);
const r3b = await post('/api/cadastro', { nome:'Vazio', descritores:[] });
ok('e cadastro sem nenhuma amostra também', r3b.status === 400, 'HTTP ' + r3b.status);

/* ---- 4. recadastrar SUBSTITUI, não acumula ------------------------------- */
/* Sem isto, quem refaz o cadastro por ter mudado o cabelo fica com duas fichas,
   e a antiga continua valendo — com o rosto que a pessoa não tem mais. */
await post('/api/cadastro', { nome: NOME, descritores:[desc(), desc()] });
const l2 = await (await fetch(BASE + '/api/cadastros')).json();
const meus = l2.cadastros.filter(c => c.nome === NOME);
ok('recadastrar o mesmo nome substitui a ficha anterior',
   meus.length === 1 && meus[0].amostras === 2,
   meus.length + ' ficha(s), ' + (meus[0] || {}).amostras + ' amostras');

/* ---- 5. remover tira da lista ------------------------------------------- */
const r5 = await post('/api/cadastro/remover', { nome: NOME });
ok('remover responde ok', r5.ok, 'HTTP ' + r5.status);
const l3 = await (await fetch(BASE + '/api/cadastros')).json();
ok('e o nome some da lista', !l3.cadastros.some(c => c.nome === NOME));
const r5b = await post('/api/cadastro/remover', { nome:'Ninguém ' + Date.now() });
ok('remover quem não existe dá 404, e não um ok silencioso',
   r5b.status === 404, 'HTTP ' + r5b.status);

/* ---- 6. a página abre e é ela mesma -------------------------------------- */
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/cadastro', { timeout:20000 });
await pg.waitForSelector('#ligar');
ok('a página /cadastro é servida', await pg.title() === 'Auditix IA — cadastro de rostos');

/* Os três modelos de rosto têm de carregar do vendor/. Sem eles a página abre
   bonita e não cadastra ninguém — e o erro só apareceria com alguém na frente
   da câmera, que é tarde demais. */
await pg.waitForFunction(() => typeof modelos !== 'undefined' && modelos === true,
                         { timeout:30000 }).catch(() => {});
ok('os três modelos de rosto carregam do servidor',
   await pg.evaluate(() => modelos === true),
   await pg.$eval('#dica', e => e.textContent.slice(0, 70)));

ok('o botão de salvar começa desligado',
   await pg.$eval('#salvar', b => b.disabled));

/* O nome sozinho não pode liberar o salvar: sem prova de vida não há cadastro. */
await pg.fill('#nome', 'Alguém').catch(() => {});
await pg.evaluate(() => { $('nome').disabled = false; $('nome').value = 'Alguém';
                          $('nome').dispatchEvent(new Event('input')); });
ok('e o nome sozinho NÃO libera o salvar, sem a prova de vida',
   await pg.$eval('#salvar', b => b.disabled));

const vazio = await pg.$eval('#lista', e => e.textContent);
ok('a lista carrega do servidor', /cadastrado|nome|Ninguém/i.test(vazio),
   vazio.trim().slice(0, 50));
ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));

await nav.close();
console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
