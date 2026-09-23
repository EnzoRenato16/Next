/* PORTE PARA A AIBOX — roda com:  node testes/aibox.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * A PERGUNTA QUE ESTE ARQUIVO RESPONDE: a versão que vai rodar dentro da caixa
 * calcula a MESMA COISA que a versão do navegador?
 *
 * Sem isto, "portamos o projeto para a AIBOX" é uma frase de slide. Um tensor
 * lido no formato errado não dá erro: dá número plausível e errado, e a gente
 * descobre na frente da banca. Já aconteceu nesta base de código — é por isso
 * que treino/provas.py existe.
 *
 * São três provas, da mais forte para a mais fraca:
 *
 *  1. As 30 provas gravadas por treino/provas.py. Geometria por quadro, as 12
 *     características e a nota final, tudo calculado no treino. O Python da
 *     caixa refaz o caminho e compara. Se isto divergir, o porte está errado e
 *     não há o que discutir.
 *  2. O MESMO cenário sintético rodando nos DOIS lados: o `analisar` de verdade
 *     no Chrome, e o `Rebanho` de verdade em Python. Compara quadro a quadro.
 *  3. Uma queda: os dois têm de acusar, e no mesmo instante.
 *
 * AS DUAS DIFERENÇAS CONHECIDAS, declaradas aqui em vez de escondidas:
 *
 *  a) CORTE DE CONFIANÇA. O navegador ignora ponto abaixo de 0,40; a caixa
 *     ignora abaixo de 0,30, que é o corte do TREINO. Num ponto entre os dois
 *     valores os dois lados escolhem réguas diferentes. Foi escolhido de
 *     propósito ficar perto do treino, e não perto do navegador.
 *  b) PRECISÃO DOS PESOS. O auditix-sala.html guarda a rede com 5 algarismos;
 *     treino/modelo.json tem precisão dupla. A caixa lê o arquivo original,
 *     então ela roda o modelo MAIS exato dos dois. Diferença medida na nota:
 *     ordem de 1e-6, contra um limiar de 0,50.
 *  c) FOLGA DA CAIXA. A caixa do corpo no navegador leva 6% de folga na
 *     horizontal e 4% na vertical, herdadas do rastreamento; a do treino e a da
 *     AIBOX não levam. Isso faz `prop` sair ~3,7% maior no navegador. Aqui o
 *     harness monta a caixa sem folga para comparar maçã com maçã — ao vivo a
 *     diferença existe e é essa.
 */
import { chromium } from 'playwright';
import { existsSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const ASP = 16 / 9;
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const py = (entrada) => JSON.parse(execFileSync('python3',
  ['testes/aibox_lado.py'], { input: JSON.stringify(entrada), encoding:'utf8' }));

/* ---- 1. as provas do treino --------------------------------------------- */
const pr = py({ modo:'provas' });
/* A tolerância não é frouxidão: provas.json guarda a geometria arredondada em
   3 a 5 casas, então o erro de arredondamento do próprio arquivo entra na
   conta. 1e-3 é folgado para isso e apertado para um erro de porte, que daria
   diferença na primeira casa. */
ok('o Python da caixa refaz as 12 características do treino',
   pr.pior_caracteristica < 1e-3,
   pr.casos + ' provas, pior diferença ' + pr.pior_caracteristica.toExponential(2));
ok('e chega à mesma nota da rede',
   pr.pior_nota < 1e-4, 'pior diferença ' + pr.pior_nota.toExponential(2));

/* ---- o cenário, montado uma vez e usado nos dois lados ------------------ */
/* Índices do MediaPipe que correspondem aos 17 do COCO, na ordem do COCO. */
const DO_MP = [0,2,5,7,8,11,12,13,14,15,16,23,24,25,26,27,28];

function quadro({ ombro, quadril, joelho, torn, cx = 0.5, punho = 0.20, v = 0.9 }){
  const p = (x, y) => ({ x, y, z:0, visibility:v });
  const lm = Array.from({length:33}, () => ({ x:0.5, y:0.5, z:0, visibility:0 }));
  lm[0]  = p(cx, ombro - 0.12);                       // nariz
  lm[2]  = p(cx - 0.02, ombro - 0.14);                // olhos
  lm[5]  = p(cx + 0.02, ombro - 0.14);
  lm[7]  = p(cx - 0.05, ombro - 0.13);                // orelhas
  lm[8]  = p(cx + 0.05, ombro - 0.13);
  lm[11] = p(cx - 0.06, ombro); lm[12] = p(cx + 0.06, ombro);
  lm[13] = p(cx - 0.08, ombro + 0.10); lm[14] = p(cx + 0.08, ombro + 0.10);
  lm[15] = p(cx - 0.08, ombro + punho); lm[16] = p(cx + 0.08, ombro + punho);
  lm[23] = p(cx - 0.05, quadril); lm[24] = p(cx + 0.05, quadril);
  lm[25] = p(cx - 0.05, joelho);  lm[26] = p(cx + 0.05, joelho);
  lm[27] = p(cx - 0.05, torn);    lm[28] = p(cx + 0.05, torn);
  return lm;
}
const paraCoco = lm => DO_MP.map(i => [lm[i].x, lm[i].y, lm[i].visibility]);

/* A caixa que o harness entrega ao navegador é montada dos MESMOS 17 pontos e
   SEM folga, para que `prop` seja comparável. Ver a nota (b) no cabeçalho. */
function caixaDos17(lm){
  const k = paraCoco(lm).filter(p => p[2] >= 0.30);
  const xs = k.map(p => p[0]), ys = k.map(p => p[1]);
  return { x:Math.min(...xs), y:Math.min(...ys),
           w:(Math.max(...xs) - Math.min(...xs)) * ASP,
           h: Math.max(...ys) - Math.min(...ys) };
}

function cenario(passos){
  const qs = [];
  let t = 0;
  for(const s of passos){ t += 33; qs.push({ t, lm:quadro(s) }); }
  return qs;
}

const nav = await chromium.launch({
  executablePath: ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync),
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/', { timeout:20000 });
await pg.waitForFunction(() => typeof analisar === 'function', { timeout:10000 });

const noNavegador = (qs) => pg.evaluate(({ qs, asp }) => {
  servidorVivo = false; calibrando = false; linhaChao = null; aspecto = asp;
  const t = { id:1, hist:[], firme:true, nasceu:0 };
  const saida = [];
  for(const q of qs){
    t.box = q.box;
    analisar(t, q.lm, q.t);
    saida.push({ t:q.t, baixo:+(t.baixo ?? 1), ang:t.ang, altura:t.altura,
                 prop:t.prop, nota:t.notaQueda, fora:t.foraDoTreino,
                 vel:t.velocidade, fps:t.fps, armado: !!t.quedaDesde });
  }
  return saida;
}, { qs, asp: ASP });

/* ---- 2. pessoa em pé, andando de leve ----------------------------------- */
const dePe = Array.from({length:70}, (_, i) => ({
  ombro:0.30 + Math.sin(i / 9) * 0.004, quadril:0.55, joelho:0.75, torn:0.95,
  cx:0.45 + i * 0.0012 }));
const qsA = cenario(dePe);
const jsA = await noNavegador(qsA.map(q => ({ ...q, box: caixaDos17(q.lm) })));
const pyA = py({ aspecto: ASP,
                 quadros: qsA.map(q => ({ t:q.t, kp: paraCoco(q.lm) })) });

const pior = (a, b, campo) => Math.max(...a.map((x, i) => Math.abs(x[campo] - b[i][campo])));
for(const campo of ['altura', 'ang', 'baixo', 'prop', 'vel'])
  ok(`em pé: \`${campo}\` bate entre navegador e caixa`,
     pior(jsA, pyA, campo) < 1e-6, 'pior diferença ' + pior(jsA, pyA, campo).toExponential(2));
ok('em pé: a taxa de quadros medida é a mesma dos dois lados',
   jsA.every((x, i) => x.fps === pyA[i].fps), 'fps final ' + jsA.at(-1).fps);
/* A NOTA TEM UMA DIFERENÇA REAL, e ela é pequena e explicada.

   A geometria bate bit a bit — as asserções acima dão 0.00e+0. A nota não, e a
   causa não é o porte: os pesos embutidos no auditix-sala.html estão gravados
   com 5 algarismos significativos (`0.25591`), enquanto treino/modelo.json tem
   precisão dupla (`0.25590618023100575`). O navegador roda uma CÓPIA
   ARREDONDADA do modelo; a AIBOX lê o arquivo original.

   Medido: 3e-6 com a pessoa em pé, e 9e-5 no meio do tombo — a diferença cresce
   onde a rede está no trecho íngreme da curva, que é onde ela decide. Mesmo
   assim são quatro ordens de grandeza abaixo do limiar de 0,50.

   O TETO É 1e-3, e não 1e-4, de propósito. Com 1e-4 este teste passava com 9%
   de margem sobre o pior caso medido, e teste que passa raspando quebra no
   primeiro cenário novo sem ter achado defeito nenhum. 1e-3 continua quinhentas
   vezes menor que qualquer decisão que esta nota toma, e um erro de porte de
   verdade apareceria na segunda casa, não na quarta.

   DÁ PARA ZERAR ISTO: é só gravar os pesos no HTML com precisão dupla, como no
   modelo.json. Não foi feito agora porque mexer no modelo que roda a
   demonstração, às vésperas dela, para corrigir 1e-4, é risco sem retorno. */
ok('em pé: a nota da rede é a mesma, dentro do arredondamento dos pesos',
   pior(jsA, pyA, 'nota') < 1e-3,
   'pior diferença ' + pior(jsA, pyA, 'nota').toExponential(2) + ' (limiar da nota: 0,50)');
ok('em pé: a distância do treino é a mesma',
   pior(jsA, pyA, 'fora') < 1e-6);
ok('em pé: NENHUM dos dois acusa queda',
   !jsA.some(x => x.armado) && !pyA.some(x => x.armado),
   'navegador ' + jsA.filter(x => x.armado).length +
   ', caixa ' + pyA.filter(x => x.armado).length);

/* ---- 3. a queda: os dois têm de acusar, e junto ------------------------- */
const caindo = [
  ...Array.from({length:40}, () => ({ ombro:0.30, quadril:0.55, joelho:0.75, torn:0.95 })),
  ...Array.from({length:12}, (_, i) => ({            // o tombo, em ~0,4s
    ombro:0.30 + i * 0.048, quadril:0.55 + i * 0.030,
    joelho:0.75 + i * 0.016, torn:0.95 })),
  ...Array.from({length:60}, () => ({ ombro:0.88, quadril:0.91, joelho:0.94, torn:0.96 })),
];
const qsB = cenario(caindo);
const jsB = await noNavegador(qsB.map(q => ({ ...q, box: caixaDos17(q.lm) })));
const pyB = py({ aspecto: ASP,
                 quadros: qsB.map(q => ({ t:q.t, kp: paraCoco(q.lm) })) });
/* O MESMO tombo, gravado para o teste de ponta a ponta da sala.py
   (testes/sala-ponta.mjs) — que precisa de uma queda que a rede de verdade
   reconheça, e esta é a que os dois lados já concordam que é queda. */
if(process.env.DUMP_QUEDA){
  writeFileSync(process.env.DUMP_QUEDA, JSON.stringify({ aspecto: ASP,
    quadros: qsB.map(q => ({ t:q.t, kp: paraCoco(q.lm) })) }));
}

const primeiro = (a) => { const i = a.findIndex(x => x.armado); return i < 0 ? null : a[i].t; };
ok('queda: os DOIS acusam',
   primeiro(jsB) !== null && primeiro(pyB) !== null,
   'navegador ' + primeiro(jsB) + 'ms, caixa ' + primeiro(pyB) + 'ms');
ok('queda: e armam no MESMO quadro',
   primeiro(jsB) === primeiro(pyB),
   'navegador ' + primeiro(jsB) + 'ms contra caixa ' + primeiro(pyB) + 'ms');
for(const campo of ['altura', 'ang', 'baixo', 'prop'])
  ok(`queda: \`${campo}\` bate quadro a quadro`,
     pior(jsB, pyB, campo) < 1e-6, 'pior diferença ' + pior(jsB, pyB, campo).toExponential(2));
ok('queda: a nota da rede bate no tombo inteiro',
   pior(jsB, pyB, 'nota') < 1e-3,
   'pior diferença ' + pior(jsB, pyB, 'nota').toExponential(2) +
   '; maior nota vista: navegador ' + Math.max(...jsB.map(x => x.nota)).toFixed(4) +
   ', caixa ' + Math.max(...pyB.map(x => x.nota)).toFixed(4));

ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));
await nav.close();
console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
