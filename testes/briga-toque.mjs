/* BRIGA É ENCOSTAR — roda com:  node testes/briga-toque.mjs
 *
 * Precisa do servidor no ar (CALIBRACAO=1 uv run servidor.py) e do python3
 * com numpy (o lado da caixa).
 *
 * Desde 23/10 a briga acusa quando um ponto do esqueleto de uma pessoa
 * encosta no esqueleto da outra por 0,3 s. Antes era "punho perto do centro
 * do tronco" com dois golpes rápidos, e na tela parecia a caixa encostando.
 * Este teste roda a `analisarBriga` DE VERDADE do navegador e a
 * `analisar_briga` da caixa sobre os mesmos dois esqueletos, e cobra que os
 * dois lados digam o mesmo.
 */
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};

/* Uma pessoa de pé em COCO-17, centrada em cx. `mao` leva a mão direita
   (ponto 10) até um lugar. Um balanço de 0,002 para não virar "objeto parado". */
function pessoa(cx, t, mao = null){
  const s = Math.sin(t / 300) * 0.002;
  const p = (x, y) => [x + s, y, 0.95];
  const kp = [p(cx,.20), p(cx-.01,.19), p(cx+.01,.19), p(cx-.02,.20), p(cx+.02,.20),
    p(cx-.05,.30), p(cx+.05,.30), p(cx-.06,.42), p(cx+.06,.42), p(cx-.06,.52), p(cx+.06,.52),
    p(cx-.04,.55), p(cx+.04,.55), p(cx-.04,.72), p(cx+.04,.72), p(cx-.04,.90), p(cx+.04,.90)];
  if(mao) kp[10] = [mao[0], mao[1], 0.95];
  return kp;
}
const ASP = 16 / 9, FPS = 15;
/* `toque(t)` diz para onde vai a mão do A naquele instante (ou null). */
function cena(seg, toque){
  const q = [];
  for(let i = 0; i <= seg * FPS; i++){
    const t = Math.round(i * 1000 / FPS);
    q.push({ t, a: pessoa(0.40, t, toque(t)), b: pessoa(0.60, t) });
  }
  return q;
}
const NO_TRONCO = [0.58, 0.40], NO_BRACO = [0.545, 0.47], PERTO_MAS_NAO = [0.51, 0.40];
const cenas = {
  longe:     cena(3.6, () => null),
  tronco:    cena(3.6, t => t > 2500 && t < 3300 ? NO_TRONCO : null),
  braco:     cena(3.6, t => t > 2500 && t < 3300 ? NO_BRACO : null),
  quaseLa:   cena(3.6, t => t > 2500 ? PERTO_MAS_NAO : null),
  relance:   cena(3.6, t => t > 2500 && t < 2600 ? NO_TRONCO : null),
};

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe, args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/', { timeout:20000 });
await pg.waitForFunction(() => typeof analisarBriga === 'function', { timeout:10000 });

const noNavegador = (qs) => pg.evaluate(([qs, asp]) => {
  servidorVivo = false; calibrando = false; linhaChao = null; aspecto = asp;
  anomalias.length = 0; alertaDe.clear(); brigaPar.clear();
  /* COCO-17 -> os 33 pontos do MediaPipe, pelo mesmo mapa da Sala. */
  const lm33 = kp => { const lm = Array.from({length:33}, () => ({x:.5,y:.5,z:0,visibility:0}));
    COCO_DO_MP.forEach((i, k) => lm[i] = { x:kp[k][0], y:kp[k][1], z:0, visibility:kp[k][2] });
    return lm; };
  const caixa = kp => { const xs = kp.map(p => p[0]), ys = kp.map(p => p[1]);
    return { x:Math.min(...xs), y:Math.min(...ys), w:Math.max(...xs)-Math.min(...xs), h:Math.max(...ys)-Math.min(...ys) }; };
  const A = { id:1, hist:[], firme:true, nasceu:-1e6 }, B = { id:2, hist:[], firme:true, nasceu:-1e6 };
  trilhas = [A, B];
  for(const q of qs){
    A.box = caixa(q.a); B.box = caixa(q.b);
    analisar(A, lm33(q.a), q.t); analisar(B, lm33(q.b), q.t);
    analisarBriga(q.t);
  }
  trilhas = [];
  return anomalias.filter(a => a.tipo === 'briga').map(a => a.porque);
}, [qs, ASP]);

const naCaixa = (qs) => JSON.parse(execFileSync('python3', ['-c', `
import json, sys, os
sys.path.insert(0, os.getcwd())
from aibox import trilhas
ent = json.load(sys.stdin)
reb = trilhas.Rebanho()
out = []
for q in ent["q"]:
    for al in reb.quadro([(1, [tuple(p) for p in q["a"]]), (2, [tuple(p) for p in q["b"]])], ent["asp"], q["t"]):
        if al.get("tipo") == "briga": out.append(al.get("porque", ""))
print(json.dumps(out))
`], { input: JSON.stringify({ q: qs, asp: ASP }) }).toString());

const res = {};
for(const [nome, qs] of Object.entries(cenas)) res[nome] = { js: await noNavegador(qs), py: naCaixa(qs) };
const n = (r) => r.js.length + ' no navegador, ' + r.py.length + ' na caixa';

ok('lado a lado, sem encostar, não é briga', !res.longe.js.length && !res.longe.py.length, n(res.longe));
ok('mão no tronco do outro por 0,8 s é briga, nos dois lados',
   res.tronco.js.length === 1 && res.tronco.py.length === 1, n(res.tronco) + '  ' + res.tronco.js[0]);
ok('mão no braço do outro também é briga', res.braco.js.length === 1 && res.braco.py.length === 1, n(res.braco));
ok('mão a um palmo do outro, sem encostar, não é', !res.quaseLa.js.length && !res.quaseLa.py.length, n(res.quaseLa));
ok('um relance de 0,1 s não é briga', !res.relance.js.length && !res.relance.py.length, n(res.relance));
ok('o motivo diz qual ponto encostou', /a mão direita do #1 encostou no corpo do #2/.test(res.tronco.js[0] || ''),
   res.tronco.py[0] || '');
ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));

await nav.close();
console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM' : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
