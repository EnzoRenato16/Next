/* A entrega dos alertas da AIBOX — roda com:  node testes/entrega.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. A caixa agora guarda o alerta e reenvia quando a rede
 * do laboratório volta. Reenviar tem um risco que ninguém vê na hora: o
 * servidor grava, a resposta se perde, a caixa manda de novo — e a cadeia
 * ganha uma queda que não aconteceu. Linha de cadeia não se apaga. É isso que
 * este arquivo cobra, junto com o resto do caminho novo.
 */
import { spawnSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const post = (rota, corpo) => fetch(BASE + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo) });
const total_ = async () => (await (await fetch(BASE + '/api/verificar')).json()).total;

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

const CHAVE = 'teste' + Date.now().toString(16);
const base = { aluno_id:'corpo-7', tipo_evento:'queda', localizacao:'teste-entrega' };

/* ---- 1. A MESMA CHAVE DUAS VEZES É UM EVENTO SÓ ---------------------- */
const antes = await total_();
const r1 = await (await post('/api/evento', { ...base, chave: CHAVE })).json();
const r2 = await (await post('/api/evento', { ...base, chave: CHAVE })).json();
const depois = await total_();
ok('o reenvio com a mesma chave NÃO grava outra linha na cadeia',
   depois === antes + 1, antes + ' -> ' + depois);
ok('e devolve o evento ORIGINAL, o mesmo id e o mesmo hash',
   r2.id === r1.id && r2.hash_atual === r1.hash_atual, r1.id + ' / ' + r2.id);
ok('avisando que era repetido', r2.repetido === true && r1.repetido === false,
   JSON.stringify([r1.repetido, r2.repetido]));

/* Chegando JUNTAS: a conferência acontece depois do cadeado da cadeia. Se ela
   viesse antes, as duas leriam "ainda não existe" e as duas gravariam. */
const C2 = CHAVE + 'b';
const n0 = await total_();
const juntas = await Promise.all([1,2,3,4,5].map(() =>
  post('/api/evento', { ...base, chave: C2 }).then(r => r.json())));
const n1 = await total_();
ok('cinco cópias chegando AO MESMO TEMPO viram uma linha só',
   n1 === n0 + 1 && new Set(juntas.map(j => j.id)).size === 1,
   (n1 - n0) + ' linha(s), ids ' + [...new Set(juntas.map(j => j.id))]);

/* ---- 2. O NAVEGADOR CONTINUA FUNCIONANDO SEM CHAVE -------------------- */
const r3 = await post('/api/evento', base);
const r4 = await post('/api/evento', base);
const j3 = await r3.json(), j4 = await r4.json();
ok('sem chave (o navegador), dois envios continuam sendo dois eventos',
   r3.ok && r4.ok && j3.id !== j4.id, j3.id + ' / ' + j4.id);

/* ---- 3. O ATRASO DE ENTREGA APARECE, FORA DA CADEIA ------------------- */
const r5 = await (await post('/api/evento',
  { ...base, chave: CHAVE + 'c', ocorreu_ha_ms: 95000 })).json();
const lista = await (await fetch(BASE + '/api/eventos?limite=20&completo=1')).json();
const meu = lista.find(e => e.id === r5.id);
ok('um alerta que esperou na fila mostra o atraso em segundos',
   meu && meu.atraso_s === 95, JSON.stringify(meu && meu.atraso_s));
const normal = lista.find(e => e.id === r1.id);
ok('e um que chegou na hora não mostra atraso nenhum',
   normal && normal.atraso_s === null, JSON.stringify(normal && normal.atraso_s));

/* ---- 4. AS POSES SÃO CONFERIDAS NA ENTRADA ---------------------------- */
const ponto = [0.5, 0.5, 0.9];
const quadro = Array(17).fill(ponto);
const r6 = await post('/api/evento', { ...base, chave: CHAVE + 'd', poses:[quadro, quadro] });
const j6 = await r6.json();
ok('poses no formato certo são aceitas', r6.ok, 'HTTP ' + r6.status);
const l2 = await (await fetch(BASE + '/api/eventos?limite=5&completo=1')).json();
ok('e o evento passa a dizer que tem esqueleto',
   (l2.find(e => e.id === j6.id) || {}).tem_esqueleto === true);
const r7 = await post('/api/evento', { ...base, chave: CHAVE + 'e',
  poses:[Array(12).fill(ponto)] });
ok('um quadro com 12 pontos em vez de 17 é recusado', r7.status === 400, 'HTTP ' + r7.status);
const n7 = await total_();
const r8 = await post('/api/evento', { ...base, chave: CHAVE + 'f', poses:[[[1,2]]] });
ok('e a recusa acontece ANTES de gravar: a cadeia não cresce',
   r8.status === 400 && (await total_()) === n7);

/* ---- 5. A CADEIA CONTINUA FECHANDO ------------------------------------ */
const v = await (await fetch(BASE + '/api/verificar')).json();
ok('depois de tudo isso, a cadeia continua íntegra', v.integra === true, JSON.stringify(v));

/* ---- 6. o lado da caixa (Python) -------------------------------------- */
console.log('\n  -- a fila de entrega da caixa (Python) --');
const py = spawnSync('python3', ['testes/entrega_lado.py'], { encoding:'utf-8' });
process.stdout.write(py.stdout || '');
if(py.stderr) process.stderr.write(py.stderr);
ok('a fila de entrega passou no Python', py.status === 0);

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
