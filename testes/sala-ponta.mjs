/* A sala.py inteira, de ponta a ponta — roda com:  node testes/sala-ponta.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. O laço da sala.py mudou em vários pontos de uma vez —
 * entrega em fila, poses junto do alerta, vídeo fluido — e cada peça tinha seu
 * teste, mas o LAÇO nunca tinha rodado inteiro. Um NameError numa linha que só
 * roda quando cai alguém apareceria pela primeira vez na frente da banca.
 */
import { spawnSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

const py = spawnSync('python3', ['testes/sala_ponta.py', BASE],
                     { encoding:'utf-8', timeout:60000 });
const linhas = (py.stdout || '').trim().split('\n');
const fim = JSON.parse(linhas[linhas.length - 1] || '{}');
console.log(linhas.slice(0, -1).map(l => '    │ ' + l).join('\n'));
if(py.stderr && py.status !== 0) console.log(py.stderr.slice(-1500));

ok('a sala.py roda inteira e termina sozinha, sem erro', py.status === 0 && fim.saida === 0,
   'código ' + py.status);
ok('a tela mostrou a queda no log', /\[QUEDA\]/.test(py.stdout));

const evs = await (await fetch(BASE + '/api/eventos?limite=50&completo=1')).json();
const meus = evs.filter(e => e.localizacao === fim.local);
ok('a queda chegou ao servidor, UMA vez', meus.length === 1 && meus[0].tipo_evento === 'queda',
   meus.map(e => e.tipo_evento).join(','));
ok('com o corpo junto', meus[0] && meus[0].tem_esqueleto === true);
const esq = meus[0] ? await (await fetch(BASE + '/api/esqueleto/' + meus[0].id)).json() : {};
ok('o corpo tem os últimos quadros, 17 pontos cada',
   esq.poses && esq.poses.length >= 10 && esq.poses.every(q => q.length === 17),
   (esq.poses || []).length + ' quadros');
ok('e o último quadro é o corpo mais baixo que o primeiro (ele caiu)',
   esq.poses && esq.poses.at(-1)[11][1] > esq.poses[0][11][1],
   esq.poses && (esq.poses[0][11][1] + ' -> ' + esq.poses.at(-1)[11][1]));
ok('chegou na hora — sem atraso de fila', meus[0] && meus[0].atraso_s === null);
ok('a tela ao vivo contou o alerta como entregue', fim.estado.enviados === 1,
   JSON.stringify({ enviados: fim.estado.enviados, fila: fim.estado.pendentes }));
/* Só que ele DESENHOU com alguém olhando. "Mais rápido que a análise" não dá
   para cobrar aqui: o detector de mentira é instantâneo, então a análise anda
   no ritmo da câmera. Essa parte é do testes/fluido.mjs (vídeo 25/s contra
   análise 8/s, que é a conta da caixa de verdade). */
ok('e o pintor do vídeo fluido desenhou enquanto alguém assistia',
   fim.estado.video > 0, 'vídeo ' + (fim.estado.video || 0).toFixed(1) + '/s');
ok('a cadeia continua fechando',
   (await (await fetch(BASE + '/api/verificar')).json()).integra === true);

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
