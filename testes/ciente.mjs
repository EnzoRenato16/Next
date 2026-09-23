/* "Estou ciente", a sirene e quem pode gravar — roda com:  node testes/ciente.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. A cadeia provava que o sistema DETECTOU a queda. Agora
 * ela prova que uma pessoa REAGIU, e em quanto tempo. Isso só vale se o
 * registro for único (dois cliques não são duas reações), se o alarme não
 * puder passar despercebido, e se nem toda máquina da rede puder gravar.
 */
import { chromium } from 'playwright';
import { existsSync, mkdtempSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const post = (base, rota, corpo) => fetch(base + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo) });
const dormir = ms => new Promise(r => setTimeout(r, ms));
const totalCadeia = async () => (await (await fetch(BASE + '/api/verificar')).json()).total;

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

const queda = async () => (await (await post(BASE, '/api/evento',
  { aluno_id:'corpo-3', tipo_evento:'queda', localizacao:'teste-ciente' })).json()).id;

/* ---- 1. o ciente vira linha da cadeia, UMA vez ------------------------ */
const q1 = await queda();
await dormir(1100);
const n0 = await totalCadeia();
const c1 = await (await post(BASE, '/api/ciente', { evento_id: q1 })).json();
ok('"estou ciente" grava uma linha na cadeia', (await totalCadeia()) === n0 + 1);
ok('e devolve o tempo de resposta, no relógio do servidor',
   c1.resposta_s >= 1 && c1.resposta_s < 10, c1.resposta_s + ' s');
const c2 = await (await post(BASE, '/api/ciente', { evento_id: q1 })).json();
ok('clicar de novo NÃO grava outra — é a mesma reação',
   (await totalCadeia()) === n0 + 1 && c2.repetido && c2.ciente_id === c1.ciente_id);

const q2 = await queda();
const n1 = await totalCadeia();
await Promise.all([1,2,3,4,5].map(() => post(BASE, '/api/ciente', { evento_id: q2 })));
ok('cinco pessoas clicando AO MESMO TEMPO viram um registro só',
   (await totalCadeia()) === n1 + 1, ((await totalCadeia()) - n1) + ' linha(s)');

const lista = await (await fetch(BASE + '/api/eventos?limite=30&completo=1')).json();
const linha = lista.find(e => e.tipo_evento === 'ciente' && e.aluno_id === 'evento-' + q1);
ok('na cadeia, o ciente aponta para o alerta pelo id', !!linha, linha && linha.aluno_id);
ok('e o alerta passa a dizer em quanto tempo alguém ficou ciente',
   lista.find(e => e.id === q1).ciente_s === c1.resposta_s);

const comum = (await (await post(BASE, '/api/evento',
  { aluno_id:'Fulano', tipo_evento:'reconhecido', localizacao:'teste-ciente' })).json()).id;
ok('evento que não é alerta grave não aceita ciente',
   (await post(BASE, '/api/ciente', { evento_id: comum })).status === 400);
ok('e evento que não existe dá 404',
   (await post(BASE, '/api/ciente', { evento_id: 99999999 })).status === 404);
ok('a cadeia continua fechando',
   (await (await fetch(BASE + '/api/verificar')).json()).integra === true);

/* ---- 2. o painel: alarme, sirene, ciente ------------------------------ */
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
/* Som de verdade não dá para ouvir num teste. Um AudioContext falso conta os
   toques: é o que prova que a sirene toca, e que PARA. */
await pg.addInitScript(() => {
  window.__toques = 0;
  window.AudioContext = class {
    constructor(){ this.state = 'running'; this.currentTime = 0; this.destination = {}; }
    resume(){ this.state = 'running'; return Promise.resolve(); }
    createGain(){ return { gain:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} },
                           connect(d){ return d; } }; }
    createOscillator(){ return { frequency:{}, connect(g){ return g; },
                                 start(){ window.__toques++; }, stop(){} }; }
  };
});
await pg.goto(BASE + '/painel', { timeout:20000 });
await pg.waitForSelector('#tabela table', { timeout:15000 });
/* Os alertas deste teste já estão cientes; fecha qualquer pendente anterior
   para o alarme começar limpo. */
await pg.mouse.click(5, 5);
await dormir(2500);
while(await pg.$eval('#alarme', a => !a.hidden)){
  await pg.click('#alarme-ciente'); await dormir(600);
}

const antes = await pg.evaluate(() => window.__toques);
const q3 = await queda();
const t0 = Date.now();
await pg.waitForFunction(() => !document.getElementById('alarme').hidden, { timeout:6000 });
const ms = Date.now() - t0;
ok('uma queda nova toma a tela em poucos segundos (antes: até 15 s)', ms < 4500, ms + ' ms');
ok('com o que aconteceu escrito grande', (await pg.textContent('#alarme-tit')) === 'queda');
await dormir(2300);
/* 3 pulsos por toque, um toque a cada 2 s: em ~2,3 s são 2 toques, 6 pulsos. */
const toques = (await pg.evaluate(() => window.__toques)) - antes;
ok('a sirene toca, e repete a cada 2 s', toques === 6, toques + ' pulsos desde o alarme');
ok('o foco vai para o "Estou ciente"',
   await pg.evaluate(() => document.activeElement.id) === 'alarme-ciente');

await pg.click('#alarme-ciente');
await pg.waitForFunction(() => document.getElementById('alarme').hidden, { timeout:4000 });
const depois = await pg.evaluate(() => window.__toques);
await dormir(2500);
ok('depois do ciente, a sirene PARA', await pg.evaluate(() => window.__toques) === depois);
await pg.waitForFunction(id => [...document.querySelectorAll('#tabela tr')]
  .some(tr => tr.textContent.includes('ciente em') && tr.firstChild.textContent == id),
  q3, { timeout:6000 });
ok('e a tabela mostra "ciente em" na linha do alerta', true);

ok('alerta de ontem não dispara sirene hoje',
   await pg.evaluate(() => pendente({ tipo_evento:'queda', ciente_s:null,
                                      timestamp:'2020-01-01 00:00:00' })) === false);
ok('o cabeçalho não promete mais "não grava nada"',
   !(await pg.textContent('header')).includes('não grava nada'));
ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));
await nav.close();

/* ---- 3. QUEM_ESCREVE: o resto da rede só lê ---------------------------- */
/* Servidor à parte, com banco à parte, para não mexer no que está no ar. */
const sobe = async (porta, quem) => {
  const dir = mkdtempSync(join(tmpdir(), 'auditix-'));
  const p = spawn('uv', ['run', 'servidor.py'], { env:{ ...process.env,
    PORTA:String(porta), QUEM_ESCREVE: quem, SQLITE_ARQUIVO: join(dir, 'a.db'),
    DATABASE_URL:'' }, stdio:'ignore' });
  for(let i = 0; i < 60; i++){
    try{ await fetch(`http://127.0.0.1:${porta}/api/verificar`); return p; }
    catch{ await dormir(500); }
  }
  p.kill(); throw new Error('servidor de teste não subiu');
};
const fechado = await sobe(8792, '10.9.9.9');
const B2 = 'http://127.0.0.1:8792';
const rr = await post(B2, '/api/evento', { aluno_id:'x', tipo_evento:'queda', localizacao:'y' });
const jr = await rr.json();
ok('máquina fora da lista NÃO grava na cadeia', rr.status === 403, 'HTTP ' + rr.status);
ok('e a recusa diz o IP que o servidor viu, para dar para consertar',
   /127\.0\.0\.1/.test(jr.detail) && /10\.9\.9\.9/.test(jr.detail), jr.detail);
ok('nem remove cadastro de ninguém',
   (await post(B2, '/api/cadastro/remover', { nome:'alguém' })).status === 403);
ok('mas continua LENDO tudo', (await fetch(B2 + '/api/verificar')).ok &&
   (await fetch(B2 + '/api/eventos')).ok);
fechado.kill();

const aberto = await sobe(8793, '127.0.0.1,10.9.9.9');
const ra = await post('http://127.0.0.1:8793', '/api/evento',
  { aluno_id:'x', tipo_evento:'queda', localizacao:'y' });
ok('quem está na lista grava normalmente', ra.ok, 'HTTP ' + ra.status);
aberto.kill();

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
