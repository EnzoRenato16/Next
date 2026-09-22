/* A cadeia conferida no navegador — roda com:  node testes/cadeia.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. Já existe /api/verificar, que responde se a cadeia
 * fecha. Só que isso é o servidor dando atestado de si mesmo, e "auditável"
 * não é o servidor afirmar — é qualquer um poder refazer a conta.
 *
 * A página /cadeia recalcula os hashes no navegador. Isso só vale alguma coisa
 * se a conta dela for A MESMA do servidor: uma fórmula diferente daria todos os
 * elos vermelhos, ou — pior — todos verdes por acaso, se ela comparasse o que
 * ela mesma calculou consigo mesma. É isso que este arquivo cobra.
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

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

/* Precisa de alguns eventos para a cadeia ter o que encadear. */
for(let i = 0; i < 4; i++){
  await fetch(BASE + '/api/evento', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ aluno_id:'corpo-' + i, tipo_evento:'queda',
                           localizacao:'teste-cadeia' }) });
}

const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/cadeia', { timeout:20000 });
await pg.waitForSelector('table tbody tr', { timeout:15000 });

/* ---- 1. a conta do navegador bate com a do servidor -------------------- */
/* A asserção que sustenta todas as outras. */
const verde = await pg.$$eval('tbody tr', ls => ls.filter(l => !l.classList.contains('quebrado')).length);
const linhas = await pg.$$eval('tbody tr', ls => ls.length);
ok('todos os elos fecham com o hash recalculado no navegador',
   linhas > 0 && verde === linhas, verde + ' de ' + linhas);
ok('e o veredito diz isso em palavras',
   (await pg.textContent('#txt')).includes('fecha'), await pg.textContent('#txt'));

/* Prova de que não é auto-confirmação: o hash que a página mostra tem que ser
   um PREFIXO do hash que o servidor gravou. Se a página comparasse o que ela
   mesma calculou consigo, isto não bateria com o banco. */
const daPagina = await pg.$eval('tbody tr:last-child .hash', e => e.textContent.replace('…',''));
const doServidor = (await (await fetch(BASE + '/api/eventos?limite=200')).json())
  .sort((a,b) => a.id - b.id).pop().hash_atual;
ok('o hash da página é o mesmo que está gravado no banco',
   doServidor.startsWith(daPagina), daPagina + ' vs ' + doServidor.slice(0, 12));

/* ---- 2. adulterar acende a linha E TODAS AS SEGUINTES ------------------ */
/* O ponto inteiro da cadeia. Se só a linha mexida ficasse vermelha, o hash
   encadeado não estaria fazendo nada — bastaria recalcular a linha adulterada
   para encobrir o rastro. */
await pg.click('#adulterar');
await pg.waitForSelector('tr.quebrado', { timeout:5000 });
const quebrados = await pg.$$eval('tr.quebrado', ls => ls.length);
const culpados = await pg.$$eval('tr.culpado', ls => ls.length);
ok('adulterar UMA linha quebra ela e todas as seguintes',
   quebrados > 1, quebrados + ' de ' + linhas + ' linhas vermelhas');
ok('e exatamente uma é apontada como a origem', culpados === 1, String(culpados));
ok('o veredito nomeia o evento que quebrou',
   (await pg.textContent('#txt')).includes('QUEBROU'), await pg.textContent('#txt'));

/* ---- 3. NADA FOI GRAVADO ---------------------------------------------- */
/* Uma demonstração que estraga o banco de verdade seria inaceitável: a regra
   do projeto é que linha de cadeia não se apaga nem se altera. */
const v = await (await fetch(BASE + '/api/verificar')).json();
ok('o banco continua íntegro — a adulteração foi só na cópia do navegador',
   v.integra === true, JSON.stringify(v));

/* ---- 4. desfazer volta tudo ------------------------------------------- */
await pg.click('#restaurar');
await pg.waitForFunction(() => !document.querySelector('tr.quebrado'), { timeout:5000 });
ok('desfazer devolve a cadeia inteira ao verde',
   (await pg.$$eval('tr.quebrado', ls => ls.length)) === 0);

ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));
await nav.close();

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
