/* Teste de corrida e briga — roda com:  node testes/corrida-briga.mjs
 *
 * As funções abaixo são COPIADAS de auditix-sala.html. Mudou lá, cole aqui e
 * rode de novo.
 *
 * O QUE ESTE TESTE PRECISA PROVAR, e por quê:
 *
 * CORRIDA. A literatura que mede corrida em pixels por segundo é obrigada a
 * calibrar um limiar por câmera (o worker-abnormal-behavior-detection diz isso
 * com todas as letras: "calibrated per environment"). Calibração por ambiente
 * é o tipo de coisa que funciona na demonstração e morre na décima escola,
 * porque ninguém recalibra. A alegação desta implementação é que dividir pela
 * altura medida do corpo dispensa a calibração. Isso é testável, e o teste
 * `mesma corrida perto e longe` é o que decide: se os dois números não baterem,
 * a alegação é falsa e ela sai do pitch.
 *
 * BRIGA. As features vêm do DIFEM (arXiv 2412.05386): velocidade de
 * articulação e interseção entre articulações de pessoas diferentes. O que a
 * gente NÃO tem é o classificador treinado deles, porque não temos dataset. A
 * regra por cima das features só vale se derrubar os quatro falsos positivos
 * óbvios de uma escola, e é isso que os quatro testes negativos cobram:
 * abraço, conversa animada de longe, um empurrão só, e gesticular perto.
 *
 * LIMITE HONESTO: os cenários são sintéticos, construídos a partir de física
 * de corpo humano (1,70m, caminhada a 1,3 m/s, corrida a 3 m/s, soco de ~130ms).
 * Provam que as regras SEPARAM os casos e que a normalização funciona. Não
 * provam taxa de acerto em vídeo real — isso só sai medindo no RWF-2000, e até
 * lá briga se chama regra, não modelo.
 */

const CORRE_VEL = 1.20, CORRE_JANELA = 700, CORRE_PASSO = 100, CORRE_SEG = 600;
const BRIGA_PERTO = 1.6, BRIGA_TOQUE = 0.55, BRIGA_GOLPE = 1.80;
const BRIGA_TOQUES = 2, BRIGA_JANELA = 2500, BRIGA_GAP = 250, BRIGA_SEG = 600;
const GOLPE_MEM = 250, BRIGA_SOLTA = 0.6;

let aspecto = 16 / 9;

/* ---- cópias de auditix-sala.html ---------------------------------------- */

function velocidadeCorrida(hist, agora){
  const corrJan = hist.filter(h => agora - h.t < CORRE_JANELA);
  if(corrJan.length < 3) return 0;
  const amostras = [corrJan[0]];
  for(const h of corrJan)
    if(h.t - amostras[amostras.length - 1].t >= CORRE_PASSO) amostras.push(h);
  if(amostras.length < 3) return 0;
  let caminho = 0;
  for(let i = 1; i < amostras.length; i++)
    caminho += Math.hypot((amostras[i].qx - amostras[i-1].qx) * aspecto,
                           amostras[i].qy - amostras[i-1].qy);
  const dtTot = (amostras[amostras.length-1].t - amostras[0].t) / 1000;
  const reg = Math.max.apply(null, amostras.map(h => h.altura));
  return dtTot > 0 && reg > 1e-6 ? caminho / reg / dtTot : 0;
}

const emPe = t => t.ang < 40 && t.baixo > 0.72 && !t.quedaDesde;

const centroTronco = t => ({ x: (t.qx + t.ox) / 2, y: (t.qy + t.oy) / 2 });

function golpeDirigido(t, alvo, agora){
  if(alvo.qx == null || alvo.ox == null) return 0;
  const tx = (alvo.qx + alvo.ox) / 2, ty = (alvo.qy + alvo.oy) / 2;
  const h = t.hist.filter(x => agora - x.t < GOLPE_MEM);
  if(h.length < 2) return 0;
  const alt = t.altura || 1;
  let melhor = 0;
  for(const esq of [true, false]){
    for(let i = 0; i < h.length; i++){
      const p0 = esq ? h[i].px : h[i].pd;
      const d0 = Math.hypot((tx - p0.x) * aspecto, ty - p0.y);
      for(let j = i + 1; j < h.length; j++){
        const dt = (h[j].t - h[i].t) / 1000;
        if(dt < 0.09) continue;
        if(dt > 0.20) break;
        const p1 = esq ? h[j].px : h[j].pd;
        const d1 = Math.hypot((tx - p1.x) * aspecto, ty - p1.y);
        melhor = Math.max(melhor, (d0 - d1) / alt / dt);
      }
    }
  }
  return melhor;
}

function tocando(t, alvo){
  if(t.qx == null || alvo.qx == null || alvo.ox == null) return false;
  const h = t.hist && t.hist[t.hist.length - 1];
  if(!h) return false;
  const c = centroTronco(alvo), lim = BRIGA_TOQUE * (alvo.altura || 1);
  for(const pu of [h.px, h.pd])
    if(Math.hypot((pu.x - c.x) * aspecto, pu.y - c.y) < lim) return true;
  return false;
}

function distanciaEntre(a, b){
  if(a.qx == null || b.qx == null) return Infinity;
  const escala = (a.altura + b.altura) / 2;
  if(!(escala > 1e-6)) return Infinity;
  return Math.hypot((a.qx - b.qx) * aspecto, a.qy - b.qy) / escala;
}

/* O laço de pares, reduzido a um par e devolvendo o veredito em vez de gravar
   evento. A lógica de decisão é a mesma de analisarBriga(). */
function rodarBriga(quadros){
  const est = { desde: 0, toques: [], armado: false, pico: 0 };
  let acusou = false, motivo = null;
  for(const { a, b, agora } of quadros){
    est.toques = est.toques.filter(x => agora - x < BRIGA_JANELA);
    const dist = distanciaEntre(a, b);
    const encosta = dist < BRIGA_PERTO && (tocando(a, b) || tocando(b, a));
    const golpe = Math.max(golpeDirigido(a, b, agora), golpeDirigido(b, a, agora));
    if(encosta && golpe >= BRIGA_GOLPE && !est.armado){
      const ult = est.toques[est.toques.length - 1];
      if(ult == null || agora - ult > BRIGA_GAP){
        est.toques.push(agora);
        est.pico = Math.max(est.pico, golpe);
      }
      est.armado = true;
    }
    if(golpe < BRIGA_GOLPE * BRIGA_SOLTA) est.armado = false;
    if(encosta && est.toques.length >= BRIGA_TOQUES){
      if(!est.desde) est.desde = agora;
      else if(agora - est.desde > BRIGA_SEG){
        acusou = true;
        motivo = { toques: est.toques.length, pico: +est.pico.toFixed(2),
                   dist: +dist.toFixed(2) };
      }
    } else est.desde = 0;
  }
  return { acusou, motivo, toques: est.toques.length };
}

/* ---- construtores de cenário -------------------------------------------- */

/* Uma pessoa andando/correndo na horizontal. `v` em alturas de corpo por
   segundo, `alt` é a altura do corpo no quadro (0..1) — é ela que muda quando
   a pessoa está longe da câmera. */
function andando({ v, alt, seg = 1.0, fps = 30, jitter = 0, x0 = 0.2 }){
  const h = [];
  const n = Math.round(seg * fps);
  for(let i = 0; i <= n; i++){
    const t = i * 1000 / fps;
    const j = jitter ? (i % 2 ? jitter : -jitter) : 0;
    h.push({ t, qx: x0 + (v * alt * (t/1000)) / aspecto + j, qy: 0.5, altura: alt });
  }
  return h;
}

/* Duas pessoas frente a frente. `dist` em alturas de corpo. `socos` é uma lista
   de instantes (ms) em que A dá um golpe em B; entre eles os punhos ficam
   recolhidos junto ao próprio tronco. `alcance` diz o quanto o punho chega
   perto do tronco alheio no pico do golpe, em alturas do alvo. */
/* GEOMETRIA, e ela foi corrigida depois de o teste reprovar a primeira versão:
   com os dois a 1,0 altura de distância (1,70m entre os quadris) NENHUM soco
   alcança, porque um braço humano tem ~0,7m. A distância de briga de verdade é
   0,6 a 0,9 alturas. O teste pegou um cenário impossível antes de eu acreditar
   nele, que é exatamente para isso que ele existe. */
function duelo({ dist, socos, seg = 2.0, fps = 30, alt = 0.5, alcance = 0.15,
                 recolhido = 0.50 }){
  const quadros = [];
  const n = Math.round(seg * fps);
  const bx = 0.5, ax = bx - dist * alt / aspecto;
  const mk = (x, hist) => ({ qx: x, qy: 0.55, ox: x, oy: 0.45, altura: alt, hist });
  const histA = [], histB = [];
  for(let i = 0; i <= n; i++){
    const t = i * 1000 / fps;
    /* O punho de A: recolhido por padrão, e avançando na direção do tronco de B
       durante os 130ms de cada soco. Um soco humano leva isso. */
    let alvoDist = recolhido * alt;
    for(const s of socos){
      const u = (t - s) / 130;
      if(u >= 0 && u <= 1)
        alvoDist = Math.min(alvoDist, (recolhido + (alcance - recolhido) * u) * alt);
    }
    const cx = bx, cy = 0.5;                       // centro do tronco de B
    const punhoA = { x: cx - alvoDist / aspecto, y: cy };
    histA.push({ t, px: punhoA, pd: punhoA });
    /* B fica com os punhos junto ao PRÓPRIO tronco: não revida, e isso é de
       propósito — se a regra exigisse revide, briga com um lado só passaria. */
    histB.push({ t, px: { x: bx, y: 0.5 }, pd: { x: bx, y: 0.5 } });
    quadros.push({ agora: t,
      a: { ...mk(ax, histA.slice()), id: 1 },
      b: { ...mk(bx, histB.slice()), id: 2 } });
  }
  return quadros;
}

/* ---- verificação --------------------------------------------------------- */

let falhas = 0, total = 0;
function ok(nome, cond, detalhe = ''){
  total++;
  if(cond) console.log('  ok   ' + nome + (detalhe ? '   ' + detalhe : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + detalhe); }
}

console.log('\nCORRIDA');

/* Física: 1,70m a 1,3 m/s = 0,76 alturas/s. */
const vAndar = velocidadeCorrida(andando({ v: 0.76, alt: 0.5 }), 1000);
ok('andar não é corrida', vAndar < CORRE_VEL,
   'medido ' + vAndar.toFixed(2) + ' < limiar ' + CORRE_VEL);

/* Física: 1,70m a 3 m/s = 1,76 alturas/s. */
const vCorrer = velocidadeCorrida(andando({ v: 1.76, alt: 0.5 }), 1000);
ok('correr é corrida', vCorrer > CORRE_VEL,
   'medido ' + vCorrer.toFixed(2) + ' > limiar ' + CORRE_VEL);

/* O TESTE QUE DECIDE A ALEGAÇÃO DO PITCH.
   A mesma corrida, filmada perto (corpo ocupa 80% do quadro) e no fundo da sala
   (corpo ocupa 25%). Se a normalização funciona, os dois números são o mesmo. */
const perto = velocidadeCorrida(andando({ v: 1.76, alt: 0.80 }), 1000);
const longe = velocidadeCorrida(andando({ v: 1.76, alt: 0.25 }), 1000);
ok('mesma corrida perto e longe dá o mesmo número',
   Math.abs(perto - longe) < 0.01,
   'perto ' + perto.toFixed(3) + ' vs longe ' + longe.toFixed(3));

/* E a contraprova: sem dividir pela altura — que é como se mede em pixels por
   segundo — os mesmos dois cenários dão números muito diferentes, e é por isso
   que quem faz assim precisa calibrar por câmera. */
const cruaPerto = perto * 0.80, cruaLonge = longe * 0.25;
ok('sem normalizar, perto e longe divergem (é o problema que evitamos)',
   cruaPerto / cruaLonge > 3,
   'razão ' + (cruaPerto / cruaLonge).toFixed(1) + 'x');

/* Tremor de landmark com a pessoa parada. A 30fps o tremor soma caminho que não
   existe; a subamostragem de 100ms é o que o derruba. */
const parado30 = andando({ v: 0, alt: 0.5, jitter: 0.012 });
let cruaJit = 0;
for(let i = 1; i < parado30.length; i++)
  cruaJit += Math.hypot((parado30[i].qx - parado30[i-1].qx) * aspecto, 0);
cruaJit = cruaJit / 0.5 / (parado30[parado30.length-1].t / 1000);
const vJit = velocidadeCorrida(parado30, 1000);
ok('tremor de landmark não vira corrida', vJit < CORRE_VEL,
   'com subamostragem ' + vJit.toFixed(2) + ', sem ela ' + cruaJit.toFixed(2));
ok('e sem a subamostragem o tremor PASSARIA (é por isso que ela existe)',
   cruaJit > CORRE_VEL, 'cru ' + cruaJit.toFixed(2));

/* A queda é o movimento mais rápido que uma pessoa faz na frente da câmera.
   Sem a trava de "em pé", toda queda vira corrida junto. */
ok('quem está caindo não é acusado de correr',
   !emPe({ ang: 70, baixo: 0.35, quedaDesde: 0 }), 'tronco a 70°, corpo a 35% da altura');
ok('quem já está no chão não é acusado de correr',
   !emPe({ ang: 80, baixo: 0.30, quedaDesde: 5000 }), 'relógio de queda armado');
ok('quem corre em pé passa na trava',
   emPe({ ang: 8, baixo: 0.95, quedaDesde: 0 }));

console.log('\nBRIGA');

/* Briga: dois perto, socos repetidos com intervalo humano. */
const briga = rodarBriga(duelo({ dist: 0.8, socos: [200, 700, 1200] }));
ok('briga de verdade acusa', briga.acusou, JSON.stringify(briga.motivo));

/* FALSO POSITIVO 1 — abraço: o MESMO movimento em câmera lenta. O avanço do
   braço é o mesmo; o que muda é levar 1,2s em vez dos 130ms de um soco. Se a
   regra olhasse só "o braço foi na direção do outro", abraço e soco seriam
   indistinguíveis — é a velocidade que separa. */
function abracando({ dist, alt = 0.5, seg = 2.0, fps = 30 }){
  const quadros = [], n = Math.round(seg * fps);
  const bx = 0.5, ax = bx - dist * alt / aspecto;
  const histA = [], histB = [];
  for(let i = 0; i <= n; i++){
    const t = i * 1000 / fps;
    const u = Math.min(1, t / 1200);                 // avanço lento e único
    const d = (0.5 + (0.25 - 0.5) * u) * alt;
    const punho = { x: bx - d / aspecto, y: 0.5 };
    histA.push({ t, px: punho, pd: punho });
    histB.push({ t, px: { x: bx, y: 0.5 }, pd: { x: bx, y: 0.5 } });
    quadros.push({ agora: t,
      a: { qx: ax, qy: 0.55, ox: ax, oy: 0.45, altura: alt, hist: histA.slice(), id: 1 },
      b: { qx: bx, qy: 0.55, ox: bx, oy: 0.45, altura: alt, hist: histB.slice(), id: 2 } });
  }
  return quadros;
}
const abr = rodarBriga(abracando({ dist: 0.9 }));
ok('abraço não é briga', !abr.acusou, 'impulsos contados: ' + abr.toques);

/* FALSO POSITIVO 2 — conversa animada, gesticulando forte, mas LONGE. */
const longeSocos = rodarBriga(duelo({ dist: 3.0, socos: [200, 700, 1200] }));
ok('gesticular longe não é briga', !longeSocos.acusou,
   'distância 3,0 alturas > limiar ' + BRIGA_PERTO);

/* FALSO POSITIVO 3 — um empurrão só. Acontece, é indisciplina, não é briga.
   É este teste que justifica a exigência de repetição. */
const umSo = rodarBriga(duelo({ dist: 0.8, socos: [400] }));
ok('um empurrão só não é briga', !umSo.acusou,
   'impulsos: ' + umSo.toques + ' < exigidos ' + BRIGA_TOQUES);

/* FALSO POSITIVO 4 — perto e mexendo os braços, mas no PRÓPRIO espaço: o punho
   nunca entra no tronco do outro. É a interseção do DIFEM fazendo o trabalho. */
function gesticulando({ dist, alt = 0.5, seg = 2.0, fps = 30 }){
  const quadros = [], n = Math.round(seg * fps);
  const bx = 0.5, ax = bx - dist * alt / aspecto;
  const histA = [], histB = [];
  for(let i = 0; i <= n; i++){
    const t = i * 1000 / fps;
    /* punho de A oscilando rápido, mas sempre perto do tronco de A */
    const osc = Math.sin(t / 60) * 0.18 * alt;
    const punho = { x: ax + osc / aspecto, y: 0.5 };
    histA.push({ t, px: punho, pd: punho });
    histB.push({ t, px: { x: bx, y: 0.5 }, pd: { x: bx, y: 0.5 } });
    quadros.push({ agora: t,
      a: { qx: ax, qy: 0.55, ox: ax, oy: 0.45, altura: alt, hist: histA.slice(), id: 1 },
      b: { qx: bx, qy: 0.55, ox: bx, oy: 0.45, altura: alt, hist: histB.slice(), id: 2 } });
  }
  return quadros;
}
const ges = rodarBriga(gesticulando({ dist: 1.2 }));
ok('gesticular perto, sem alcançar o outro, não é briga', !ges.acusou,
   'o punho nunca cruza ' + BRIGA_TOQUE + ' alturas do tronco alheio');

/* E a interseção sozinha, conferida direto. */
const alvo = { qx: 0.5, qy: 0.55, ox: 0.5, oy: 0.45, altura: 0.5 };
const pertoDoAlvo = { qx: 0.4, hist: [{ px: { x: 0.49, y: 0.5 }, pd: { x: 0.2, y: 0.5 } }] };
const longeDoAlvo = { qx: 0.4, hist: [{ px: { x: 0.2, y: 0.5 }, pd: { x: 0.2, y: 0.5 } }] };
ok('interseção detecta punho no tronco alheio', tocando(pertoDoAlvo, alvo));
ok('interseção ignora punho recolhido', !tocando(longeDoAlvo, alvo));

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
