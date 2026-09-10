/* Teste da poda de corpos falsos — roda com:  node testes/corpos.mjs
 *
 * Existe porque a tela mostrava, com UMA pessoa na frente da câmera:
 *   "Corpo #2"  em cima do rosto dela,
 *   "Corpo #4"  em cima da mão levantada,
 *   "Corpo #10" em cima de uma orelha,
 *   "Corpo #16" em cima da faca que ela segurava.
 * Os IDs subiram de 2 para 37 em três minutos, e cada pedaço entrava na lista
 * como se fosse mais um aluno. Com a agitação ligada isso é uma pessoa
 * brigando com a própria mão.
 *
 * O detector de pose faz isso mesmo: foi treinado para achar gente, então
 * qualquer coisa com silhueta parecida (uma cabeça em close, uma mão fechada)
 * ganha um esqueleto inteiro por cima. O conserto não é trocar de modelo — é
 * conferir a ANATOMIA do que ele devolve.
 *
 * As funções abaixo são COPIADAS de auditix-sala.html. Mudou lá, cole aqui e
 * rode de novo. (Já perdi um teste inteiro por rodar a cópia velha.)
 *
 * DUAS TENTATIVAS FORAM REPROVADAS AQUI, e vale saber quais:
 *
 *  1. Podar só por sobreposição de caixas, ficando com a pose mais NÍTIDA (era
 *     a regra que estava no ar). Falha duas vezes: a mão esticada cai FORA da
 *     caixa do corpo, e quando o fantasma cai dentro ele costuma ser mais
 *     nítido que o corpo real com as pernas fora do quadro — então a regra
 *     chegava a apagar a PESSOA e manter a mão.
 *  2. "O centro do fantasma cai em cima de um punho do corpo verdadeiro."
 *     Cobre a mão, mas não a cabeça: num close a caixa do corpo começa no
 *     ombro, e não existe ponto de esqueleto nenhum onde o rosto está.
 *
 * O QUE PASSOU foram três regras, todas exigindo que o suspeito seja MUITO
 * menor que o outro: (a) cai dentro da caixa; (b) cai em cima de um ponto do
 * esqueleto; (c) o corpo grande está SEM CABEÇA e o suspeito está bem em cima
 * do pescoço dele. A (c) só vale para corpo sem cabeça, e é isso que impede de
 * apagar alguém que está ao fundo.
 *
 * LIMITE HONESTO: os cenários são sintéticos e as proporções foram modeladas a
 * partir dos prints, não medidas pixel a pixel. Provam que as regras separam os
 * casos, não que os números batem com a sua sala. Se algum corpo de verdade
 * sumir da tela, é aqui que se mexe.
 */

const LARG = 1280, ALT = 960;
const P = { NARIZ:0, OMBRO_E:11, OMBRO_D:12, COTOV_E:13, COTOV_D:14,
            PULSO_E:15, PULSO_D:16, QUADRIL_E:23, QUADRIL_D:24,
            JOELHO_E:25, JOELHO_D:26, TORN_E:27, TORN_D:28 };
const VIS_MIN = 0.40;
const vis = p => (p && p.visibility != null) ? p.visibility : 1;

function caixaDe(lm, larg, alt){
  for(const i of [P.OMBRO_E, P.OMBRO_D])
    if(vis(lm[i]) < VIS_MIN) return null;
  let x0 = 1, y0 = 1, x1 = 0, y1 = 0, n = 0;
  for(const p of lm){
    if(vis(p) < VIS_MIN) continue;
    x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x);
    y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); n++;
  }
  if(n < 6 || x1 <= x0 || y1 <= y0) return null;
  const fx = (x1 - x0) * 0.06, fy = (y1 - y0) * 0.04;
  return { x:(x0 - fx)*larg, y:(y0 - fy)*alt,
           w:(x1 - x0 + 2*fx)*larg, h:(y1 - y0 + 2*fy)*alt };
}
function ios(a, b){
  const x1 = Math.max(a.x, b.x), y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w), y2 = Math.min(a.y + a.h, b.y + b.h);
  const w = x2 - x1, h = y2 - y1;
  if(w <= 0 || h <= 0) return 0;
  return (w * h) / Math.max(1, Math.min(a.w * a.h, b.w * b.h));
}

/* ===== COPIADO DE auditix-sala.html ==================================== */
/* Interseção sobre a UNIÃO — o IoU comum. Serve para a outra pergunta: "estas
   duas poses são a mesma pessoa duplicada?". Duas poses duplicadas têm caixas
   quase iguais, e o IoU delas fica perto de 1.

   Aqui o `ios` acima seria errado, e o teste provou: ele dá 1.00 para uma caixa
   PEQUENA dentro de uma grande, então uma pessoa ao fundo, atrás de quem está
   na frente, era tratada como pose duplicada e sumia da sala. O IoU não cai
   nessa: caixa pequena dentro de grande dá IoU baixo. */
function iou(a, b){
  const x1 = Math.max(a.x, b.x), y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w), y2 = Math.min(a.y + a.h, b.y + b.h);
  const w = x2 - x1, h = y2 - y1;
  if(w <= 0 || h <= 0) return 0;
  const inter = w * h;
  return inter / Math.max(1, a.w*a.h + b.w*b.h - inter);
}
const IOU_MESMO = 0.65;
const nitidez = d => d.lm.reduce((s, p) => s + vis(p), 0) / d.lm.length;

/* Duas poses são da MESMA PESSOA quando as duas cabeças estão no mesmo lugar.

   Comparar caixas não bastava, e a tela provou isso: a caixa muda de forma
   conforme o que está no quadro (sentado, de lado, meio corpo), então duas
   poses da mesma pessoa às vezes se sobrepõem pouco e escapavam do IOU_MESMO.
   Duas cabeças, não: pessoa tem uma só.

   A escala é a MAIOR largura de ombro do par, de propósito. A pose falsa que
   nasce em cima de uma cabeça inventa ombros no queixo, e a largura dela sai
   minúscula; medir por ela deixaria a folga perto de zero e o fantasma
   sobreviveria. Pela maior, duas pessoas de verdade lado a lado ainda ficam
   separadas: ombro colado com ombro dá distância de nariz perto de UMA largura
   de ombro, bem acima de 0.6. */
const CABECA_MESMA = 0.6;
function mesmaCabeca(a, b, larg, alt){
  const na = pontoPx(a.lm[P.NARIZ], larg, alt), nb = pontoPx(b.lm[P.NARIZ], larg, alt);
  if(!na || !nb) return false;
  const escala = Math.max(ombroPx(a, larg, alt), ombroPx(b, larg, alt));
  if(!(escala > 0)) return false;
  return Math.hypot(na.x - nb.x, na.y - nb.y) < CABECA_MESMA * escala;
}

/* Fantasma de PARTE DE CORPO: o detector monta um esqueleto inteiro em cima de
   um pedaço da pessoa — a cabeça, uma orelha, a mão segurando um objeto. Na
   tela isso virava "Corpo #4", "Corpo #10", "Corpo #16", com ID novo a cada
   poucos segundos, e cada um deles concorria como se fosse gente.

   Duas assinaturas denunciam o fantasma, e as duas precisam do tamanho: só é
   candidato a parte quem for MUITO menor que o outro. Sem isso, uma pessoa
   parcialmente atrás de outra seria engolida. */
const PARTE_TAM    = 0.35;   // área da pequena sobre a área da grande
const PARTE_PERTO  = 0.45;   // distância até o punho, em larguras de ombro
const CABECA_ACIMA = 1.50;   // até onde acima do ombro a cabeça pode estar

function ehParte(peq, gr, larg, alt){
  const area = b => Math.max(1, b.w * b.h);
  if(area(peq.box) / area(gr.box) > PARTE_TAM) return false;

  /* FANTASMA DE MÃO: o centro da pose falsa cai em cima de um PUNHO do corpo
     verdadeiro. É o caso do "Corpo #4" e do "Corpo #16" (a mão segurando a
     faca), e escapa de qualquer regra por caixa porque o braço está esticado
     para fora dela.

     Só o punho, e isso é deliberado. Duas versões mais amplas foram reprovadas
     pelo teste, as duas por apagarem GENTE DE VERDADE:

       · "cai dentro da caixa do outro" — num close a caixa de uma pessoa cobre
         quase o quadro inteiro, então qualquer um ao fundo cai dentro dela.
       · "cai perto de QUALQUER ponto do esqueleto" — quem está atrás do ombro
         de alguém fica, por definição, em cima do ombro dessa pessoa.

     O punho é diferente dos outros pontos: a mão de quem está na frente fica
     perto da câmera, e ninguém fica em pé em cima da mão de outro. */
  const o = ombroPx(gr, larg, alt);
  if(!(o > 0)) return false;
  const cx = peq.box.x + peq.box.w/2, cy = peq.box.y + peq.box.h/2;
  for(const i of [P.PULSO_E, P.PULSO_D]){
    const p = pontoPx(gr.lm[i], larg, alt);
    if(p && Math.hypot(cx - p.x, cy - p.y) < PARTE_PERTO * o) return true;
  }

  /* A CABEÇA QUE FALTA. Numa webcam de perto a pessoa entra cortada e o corpo
     verdadeiro sai SEM pontos de cabeça — a caixa dele começa no ombro. Aí o
     detector monta uma pose separada em cima do rosto, e ela não cai dentro da
     caixa (fica acima dela) nem perto de um ponto do esqueleto (não há ponto
     nenhum ali). Foi exatamente o "Corpo #2" do print.

     A regra só vale quando o corpo grande está mesmo SEM cabeça. Isso é o que
     a torna segura: se ele tem cabeça, a pose de cima é outra pessoa e fica.
     Uma pessoa ao fundo, atrás de alguém de rosto visível, nunca é apagada. */
  if(temCabeca(gr, larg, alt)) return false;
  const oe = pontoPx(gr.lm[P.OMBRO_E], larg, alt);
  const od = pontoPx(gr.lm[P.OMBRO_D], larg, alt);
  if(!oe || !od) return false;
  const mx = (oe.x + od.x)/2, my = (oe.y + od.y)/2;
  return cy < my                                   // está acima da linha do ombro
      && Math.abs(cx - mx) < 0.60 * o              // e centrado nela
      && (my - cy) < CABECA_ACIMA * o;             // a uma distância de pescoço
}

/* Pontos de cabeça: nariz, olhos, orelhas. São os índices 0 a 10 do MediaPipe. */
function temCabeca(d, larg, alt){
  for(let i = 0; i <= 10; i++) if(pontoPx(d.lm[i], larg, alt)) return true;
  return false;
}

const pontoPx = (p, larg, alt) =>
  (p && vis(p) >= VIS_MIN) ? { x:p.x*larg, y:p.y*alt } : null;

function ombroPx(d, larg, alt){
  const e = pontoPx(d.lm[P.OMBRO_E], larg, alt), r = pontoPx(d.lm[P.OMBRO_D], larg, alt);
  return (e && r) ? Math.hypot(e.x - r.x, e.y - r.y) : 0;
}

/* O detector às vezes devolve duas ou três poses para a MESMA pessoa, ou para
   um pedaço dela. Sem podar isso vira três corpos na lista, os IDs disparam e a
   agitação acusa alguém brigando consigo mesmo.

   Duas decisões diferentes, e a diferença importa:
     · mesma pessoa duas vezes  -> fica a pose mais NÍTIDA;
     · pedaço de uma pessoa     -> o pedaço SEMPRE perde.
   Antes havia só a primeira, e ela decidia pela nitidez. Um fantasma de mão em
   close costuma ser mais nítido que o corpo de verdade com as pernas fora do
   quadro — então a regra da nitidez chegava a manter o fantasma e descartar a
   pessoa. */
function podar(dets, larg, alt){
  const fora = new Set();
  for(let i = 0; i < dets.length; i++){
    for(let j = 0; j < dets.length; j++){
      if(i === j || fora.has(i) || fora.has(j)) continue;
      const A = dets[i], B = dets[j];

      if(mesmaCabeca(A, B, larg, alt) || iou(A.box, B.box) > IOU_MESMO){
        fora.add(nitidez(A) >= nitidez(B) ? j : i);
        continue;
      }

      const areaA = A.box.w * A.box.h, areaB = B.box.w * B.box.h;
      const peq = areaA <= areaB ? A : B;
      if(ehParte(peq, peq === A ? B : A, larg, alt)) fora.add(peq === A ? i : j);
    }
  }
  return dets.filter((_, i) => !fora.has(i));
}

/* ===== fim da cópia ==================================================== */

/* A regra ANTIGA, guardada só para a coluna "antes" da tabela. */
function podarAntigo(dets){
  const fora = new Set();
  for(let i = 0; i < dets.length; i++){
    if(fora.has(i)) continue;
    for(let j = i + 1; j < dets.length; j++){
      if(fora.has(j)) continue;
      if(ios(dets[i].box, dets[j].box) > 0.65)
        fora.add(nitidez(dets[i]) >= nitidez(dets[j]) ? j : i);
    }
  }
  return dets.filter((_, i) => !fora.has(i));
}

/* ---- fabricação de poses ----------------------------------------------
   Um corpo em pixels, com tudo proporcional à largura do ombro, do jeito que
   um corpo humano é. As opções existem porque os casos difíceis são justamente
   os corpos INCOMPLETOS:
     cabeca:false  -> a pessoa entrou cortada (close de webcam). É o caso que
                      derrubou a segunda tentativa de regra.
     pernas:false  -> normal em webcam de notebook, e o motivo de o corpo real
                      ser MENOS nítido que o fantasma.                       */
function corpo(cx, cy, ombro, { pernas = false, cabeca = true, nitido = 0.95 } = {}){
  const lm = Array.from({ length:33 }, () => ({ x:cx/LARG, y:cy/ALT, visibility:0 }));
  const pos = (i, px, py, v = nitido) =>
    lm[i] = { x:px/LARG, y:py/ALT, z:0, visibility:v };
  if(cabeca){
    pos(P.NARIZ, cx,              cy - 0.95*ombro);
    pos(2,       cx - 0.18*ombro, cy - 1.05*ombro);
    pos(5,       cx + 0.18*ombro, cy - 1.05*ombro);
    pos(7,       cx - 0.42*ombro, cy - 0.95*ombro);
    pos(8,       cx + 0.42*ombro, cy - 0.95*ombro);
  }
  pos(P.OMBRO_E,   cx - 0.50*ombro, cy);
  pos(P.OMBRO_D,   cx + 0.50*ombro, cy);
  pos(P.COTOV_E,   cx - 0.70*ombro, cy + 0.80*ombro);
  pos(P.COTOV_D,   cx + 0.70*ombro, cy + 0.80*ombro);
  pos(P.PULSO_E,   cx - 0.85*ombro, cy + 1.60*ombro);
  pos(P.PULSO_D,   cx + 0.85*ombro, cy + 1.60*ombro);
  pos(P.QUADRIL_E, cx - 0.30*ombro, cy + 2.10*ombro);
  pos(P.QUADRIL_D, cx + 0.30*ombro, cy + 2.10*ombro);
  if(pernas){
    pos(P.JOELHO_E, cx - 0.30*ombro, cy + 3.30*ombro);
    pos(P.JOELHO_D, cx + 0.30*ombro, cy + 3.30*ombro);
    pos(P.TORN_E,   cx - 0.30*ombro, cy + 4.40*ombro);
    pos(P.TORN_D,   cx + 0.30*ombro, cy + 4.40*ombro);
  }
  return lm;
}
function maoEm(lm, lado, px, py){
  lm[lado === 'E' ? P.PULSO_E : P.PULSO_D] =
    { x:px/LARG, y:py/ALT, z:0, visibility:0.95 };
  return lm;
}
const det = lm => ({ lm, box:caixaDe(lm, LARG, ALT) });

/* ---- cenários ---------------------------------------------------------- */
const CENARIOS = [];

/* Print 1: close de webcam. A pessoa entra CORTADA — a caixa dela começa no
   ombro — e o detector monta uma pose só para a cabeça, logo acima. O fantasma
   é mais nítido porque cabe inteiro no quadro. */
CENARIOS.push({ nome:'close cortado + fantasma na cabeça', pessoas:1, dets:[
  det(corpo(640, 620, 430, { cabeca:false })),
  det(corpo(660, 330, 105, { nitido:0.99 })) ]});

/* Print 2 e 4: mão levantada segurando um objeto, com esqueleto inventado em
   cima dela. A mão está esticada para FORA da caixa do corpo. */
CENARIOS.push({ nome:'fantasma na mão levantada', pessoas:1, dets:[
  det(maoEm(corpo(880, 520, 330), 'E', 300, 560)),
  det(corpo(300, 560, 80, { nitido:0.99 })) ]});

/* Print 3: orelha, bem dentro da caixa do corpo. */
/* Print 3: orelha. A orelha do corpo de baixo fica em (532, 90) — o fantasma
   nasce ALI, não num ponto qualquer dentro da caixa. Colocado no lugar errado,
   este cenário vira um teste de mentira que passa por acidente. */
CENARIOS.push({ nome:'fantasma na orelha', pessoas:1, dets:[
  det(corpo(700, 470, 400)),
  det(corpo(532, 150, 70, { nitido:0.99 })) ]});

/* Duas pessoas de verdade. Nenhuma pode sumir. */
CENARIOS.push({ nome:'duas pessoas lado a lado', pessoas:2, dets:[
  det(corpo(430, 480, 240)), det(corpo(850, 480, 240)) ]});

/* Ombro com ombro: o caso mais apertado da regra da cabeça. Se ela for frouxa
   demais, some um aluno. */
CENARIOS.push({ nome:'duas pessoas ombro a ombro', pessoas:2, dets:[
  det(corpo(590, 480, 230)), det(corpo(830, 480, 230)) ]});

/* Alguém ao fundo, pequeno, longe de quem está na frente. */
CENARIOS.push({ nome:'alguém ao fundo, ao lado', pessoas:2, dets:[
  det(corpo(800, 520, 360)), det(corpo(200, 330, 90, { pernas:true })) ]});

/* O CASO QUE MAIS ARRISCA APAGAR GENTE: alguém pequeno ao fundo, logo acima do
   ombro de quem está na frente. É a mesma posição do fantasma do print 1. O que
   separa os dois é que aqui o corpo da frente TEM CABEÇA — então a pose de cima
   é outra pessoa, e fica. */
CENARIOS.push({ nome:'alguém ao fundo, atrás do ombro', pessoas:2, dets:[
  det(corpo(640, 620, 430)),
  det(corpo(985, 430, 100, { pernas:true })) ]});

CENARIOS.push({ nome:'uma pessoa, uma pose', pessoas:1, dets:[
  det(corpo(640, 480, 300)) ]});

CENARIOS.push({ nome:'mesma pessoa, pose tremida', pessoas:1, dets:[
  det(corpo(640, 480, 300)), det(corpo(648, 486, 296, { nitido:0.80 })) ]});

/* ---- limite conhecido --------------------------------------------------
   Este caso a geometria NÃO resolve, e o teste existe para dizer isso em voz
   alta em vez de deixar um buraco calado.

   Nos prints, a caixa do corpo verdadeiro NÃO incluía a mão levantada — ou
   seja, o punho estava com visibilidade baixa e o esqueleto verdadeiro nem
   sabia onde a mão estava. Sem esse ponto, não há a que comparar: o fantasma
   da mão é, num quadro só, indistinguível de uma pessoa pequena ao lado.

   O que segura este caso é TEMPO, não geometria: FIRME_MS exige meio segundo
   de tela antes de uma trilha virar pessoa, e fantasma de mão pisca. Se ele
   aparecer mesmo assim na sua sala, é o FIRME_MS que se aumenta — não estas
   regras, que aí passariam a apagar gente de verdade. */
const LIMITE = { nome:'fantasma na mão, punho invisível', pessoas:1, dets:[
  det(corpo(880, 520, 330)),
  det(corpo(300, 560, 80, { nitido:0.99 })) ]};

/* ---- execução ---------------------------------------------------------- */
let falhas = 0;
console.log('\ncenário                              real   antes   depois');
console.log('─'.repeat(60));
for(const c of CENARIOS){
  const dets = c.dets.filter(d => d.box);
  if(dets.length !== c.dets.length){ console.log('FALHA ' + c.nome + ': caixa nula'); falhas++; continue; }
  const antes  = podarAntigo(dets).length;
  const depois = podar(dets, LARG, ALT).length;
  const ok = depois === c.pessoas;
  if(!ok) falhas++;
  console.log((ok ? 'OK    ' : 'FALHA ') + c.nome.padEnd(30) +
    String(c.pessoas).padStart(4) + String(antes).padStart(8) +
    String(depois).padStart(9) + (antes === c.pessoas ? '' : '   <- consertado'));
}
console.log('─'.repeat(60));
{
  const d = LIMITE.dets.filter(x => x.box);
  console.log('\nlimite conhecido (não conta como falha):');
  console.log('      ' + LIMITE.nome.padEnd(30) +
    String(LIMITE.pessoas).padStart(4) + String(podarAntigo(d).length).padStart(8) +
    String(podar(d, LARG, ALT).length).padStart(9) +
    '   <- só FIRME_MS segura');
}
console.log(falhas ? `\n${falhas} CENÁRIO(S) FALHARAM\n` : '\nTODOS OS CENÁRIOS PASSARAM\n');
process.exit(falhas ? 1 : 0);
