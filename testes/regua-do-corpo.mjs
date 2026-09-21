/* A RÉGUA DO CORPO — roda com:  node testes/regua-do-corpo.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * DE ONDE ESTE TESTE VEIO. De um print de uso real: webcam de notebook a um
 * palmo do rosto, uma pessoa só, parada, e DEZESSEIS "quedas" na lista. Os
 * números do próprio alerta se contradiziam —
 *
 *     tronco 3°, quadril desceu 0.00 alturas, caixa 0.2, altura 22% da dele
 *
 * — três medidas dizendo "de pé" e uma dizendo "desabou". E a que dizia
 * "desabou" dispara SOZINHA, sem precisar de confirmação de nenhuma outra.
 *
 * `altura 22% da dele` é `baixo`, e `baixo` é a altura de agora dividida pela
 * régua da pessoa. Se a régua está errada, tudo depois dela está errado. Havia
 * dois defeitos somados, e são os dois que este arquivo cobra:
 *
 *   1. A régua misturava unidades. A altura sai de ombro→tornozelo, ou de
 *      ombro→joelho, ou do tronco × 3,2, conforme o que dá para ver. São
 *      aproximações diferentes da mesma pessoa, e num close a visibilidade do
 *      tornozelo PISCA em torno do limiar. Guardar as três no mesmo topo é
 *      comparar centímetro com polegada.
 *   2. Um quadro ruim envenenava para sempre. `Math.max` puro: o topo só subia
 *      e nunca era revisto, então um único quadro com ponto inventado ficava de
 *      régua pelo resto da trilha.
 *
 * O QUE ESTE TESTE NÃO PROVA, e é importante dizer: ele não prova que uma
 * webcam colada no rosto passa a funcionar. Não passa, e nenhum conserto de
 * código faz passar — com o corpo fora do quadro o modelo INVENTA o quadril, e
 * medida tirada de ponto inventado é lixo por mais cuidadosa que seja a conta.
 * O que se prova aqui é outra coisa, e ela é real: um quadro ruim não contamina
 * mais os seguintes.
 *
 * E o cenário 3 existe para o conserto não virar desligamento: queda de
 * verdade tem de continuar sendo pega. Um teste que só cobra "não dispara"
 * passaria com a regra apagada.
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

const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/', { timeout:20000 });
await pg.waitForFunction(() => typeof analisar === 'function', { timeout:10000 });

/* Roda a `analisar` DE VERDADE da Sala, quadro a quadro, sobre um corpo
   montado à mão. Nada de cópia da regra: cópia envelhece e mente. */
const correr = (quadros) => pg.evaluate((qs) => {
  /* Sem rede: o objetivo é medir a régua, não gravar evento nem calibração. */
  servidorVivo = false; calibrando = false; linhaChao = null; aspecto = 16/9;

  const corpo = ({ ombro, quadril, joelho, torn, visTorn }) => {
    const pt = (x, y, v = 1) => ({ x, y, z:0, visibility:v });
    const lm = Array.from({length:33}, () => pt(0.5, 0.5, 0));
    lm[0]  = pt(0.50, ombro - 0.12);          // nariz
    lm[11] = pt(0.44, ombro); lm[12] = pt(0.56, ombro);   // ombros
    lm[15] = pt(0.42, ombro + 0.20); lm[16] = pt(0.58, ombro + 0.20); // pulsos
    lm[23] = pt(0.45, quadril); lm[24] = pt(0.55, quadril);           // quadris
    lm[25] = pt(0.45, joelho, 0.9); lm[26] = pt(0.55, joelho, 0.9);
    lm[27] = pt(0.45, torn, visTorn); lm[28] = pt(0.55, torn, visTorn);
    return lm;
  };

  const t = { id:99, hist:[], firme:true, nasceu:0,
              box:{ x:0.3, y:0.2, w:0.2, h:0.7 } };
  const saida = [];
  let ms = 0;
  for(const q of qs){
    ms += 33;                                  // ~30 quadros por segundo
    t.box = { x:0.3, y:0.2, w:0.2, h:Math.max(0.05, q.caixaH ?? 0.7) };
    analisar(t, corpo(q), ms);
    saida.push({ ms, baixo:+(t.baixo ?? 1).toFixed(3),
                 regua:t.regua, topo:+(t.alturaTopo ?? 0).toFixed(3),
                 armado: !!t.quedaDesde });
  }
  return saida;
}, quadros);

/* ---- 1. um único quadro ruim não vira régua eterna ----------------------- */
/* Trinta quadros de pé, UM com o quadril inventado lá longe — o que num close
   acontece o tempo todo — e depois tudo normal de novo. A pessoa não se mexeu. */
const dePe   = { ombro:0.30, quadril:0.55, joelho:0.75, torn:0.95, visTorn:0.9 };
const picoRuim = { ombro:0.30, quadril:1.40, joelho:2.20, torn:3.00, visTorn:0.9 };
const c1 = await correr([
  ...Array(30).fill(dePe), picoRuim, ...Array(40).fill(dePe) ]);
const depoisDoPico = c1.slice(35);
const pior1 = Math.min(...depoisDoPico.map(f => f.baixo));
ok('um quadro com ponto inventado não vira a régua da pessoa',
   pior1 > 0.90, 'menor `baixo` depois do pico: ' + pior1.toFixed(3));
ok('e ninguém é acusado de cair por causa dele',
   !depoisDoPico.some(f => f.armado),
   depoisDoPico.filter(f => f.armado).length + ' quadros com o relógio armado');

/* ---- 2. o close do print: a visibilidade do tornozelo piscando ----------- */
/* Este é o caso do print. A pessoa está parada; o que oscila é só QUAL régua o
   código consegue usar, quadro a quadro. Antes do conserto as duas iam para o
   mesmo topo e a régua do tronco passava a valer uma fração da do tornozelo. */
/* As duas alturas têm de DISCORDAR MUITO, senão o cenário não prova nada: a
   primeira versão deste teste pôs o tornozelo inventado em proporção anatômica
   com o joelho, as duas réguas deram quase o mesmo número, e ele passava
   igualzinho no código com defeito. O ponto inventado justamente NÃO respeita
   anatomia — é essa a razão de ele estragar a medida.
     régua do tornozelo: |4.50 - 0.62| × 1,25 = 4,85
     régua do joelho:    |1.60 - 0.62| × 1,90 = 1,86   ->  38% de 4,85 */
const perto    = { ombro:0.62, quadril:1.25, joelho:1.60, torn:4.50, visTorn:0.9 };
const pertoCego= { ...perto, visTorn:0.1 };
const c2 = await correr(
  Array.from({length:90}, (_, i) => i % 2 ? perto : pertoCego));
const estavel = c2.slice(10);
const pior2 = Math.min(...estavel.map(f => f.baixo));
ok('com a régua piscando, cada uma é comparada só com ela mesma',
   pior2 > 0.90, 'menor `baixo`: ' + pior2.toFixed(3) +
   ' (réguas vistas: ' + [...new Set(c2.map(f => f.regua))].join(', ') + ')');
ok('e o close não gera queda em quem está parado',
   !estavel.some(f => f.armado),
   estavel.filter(f => f.armado).length + ' de ' + estavel.length +
   ' quadros acusariam');

/* ---- 3. E A QUEDA DE VERDADE CONTINUA SENDO PEGA ------------------------- */
/* Sem isto o conserto poderia ser "apagar a regra", e os dois testes acima
   passariam igual. Aqui a pessoa está de pé com o corpo inteiro no quadro, e
   então desaba: a altura cai para um terço, na MESMA régua o tempo todo. */
const caido = { ombro:0.88, quadril:0.93, joelho:0.95, torn:0.97, visTorn:0.9 };
const c3 = await correr([
  ...Array(40).fill(dePe), ...Array(40).fill({ ...caido, caixaH:0.12 }) ]);
const noChao = c3.slice(45);
ok('quem desaba de verdade continua caindo abaixo do limiar de 0,40',
   noChao.every(f => f.baixo < 0.40),
   'menor `baixo`: ' + Math.min(...noChao.map(f => f.baixo)).toFixed(3));
ok('e o relógio de queda arma',
   noChao.some(f => f.armado),
   noChao.filter(f => f.armado).length + ' de ' + noChao.length + ' quadros');

/* ---- 4. a régua nova precisa de três quadros, e isso é de propósito ------ */
const c4 = await correr(Array(3).fill(dePe));
ok('nos primeiros quadros a régua é a própria altura, e `baixo` vale 1',
   c4.every(f => Math.abs(f.baixo - 1) < 1e-6),
   c4.map(f => f.baixo).join(', '));

ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));

await nav.close();
console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
