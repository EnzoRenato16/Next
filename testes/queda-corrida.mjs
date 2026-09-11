/* Teste das camadas de QUEDA e CORRIDA — node testes/queda-corrida.mjs
 *
 * Mesmo método do teste de agitação: cenários sintéticos a 30fps, em
 * coordenadas normalizadas como as do MediaPipe, medindo o MESMO número que a
 * Sala mede ao vivo.
 *
 * As funções abaixo são COPIADAS de auditix-sala.html. Mudou lá, cole aqui.
 *
 * LIMITE HONESTO: os cenários são sintéticos. Provam que a regra separa os
 * casos, não que os números batem com gente de verdade na sua sala.
 *
 * O teste CONFERE SOZINHO se esta cópia está sincronizada com a Sala, lendo os
 * limiares direto do auditix-sala.html. Isso existe porque já perdi um teste
 * inteiro rodando um harness montado a partir de uma versão anterior do código:
 * os números não mudavam depois de uma correção real, e quase conclui que a
 * correção não funcionava. Cópia que não avisa que está velha é pior que
 * nenhuma.
 */
import fs from 'node:fs';

const P = { NARIZ:0, OMBRO_E:11, OMBRO_D:12, COTOV_E:13, COTOV_D:14,
            PULSO_E:15, PULSO_D:16, QUADRIL_E:23, QUADRIL_D:24,
            JOELHO_E:25, JOELHO_D:26, TORN_E:27, TORN_D:28 };
const VIS_MIN = 0.40, HIST_MS = 2500;
const vis = p => (p && p.visibility != null) ? p.visibility : 1;
const meio = (lm,a,b) => ({ x:(lm[a].x+lm[b].x)/2, y:(lm[a].y+lm[b].y)/2 });

/* ===== REGRA ATUAL, copiada ============================================ */
const QUEDA_ANG = 55, QUEDA_CAI = 0.10, QUEDA_SEG = 1200;
const CORRE_VEL = 1.5, CORRE_SEG = 400;

function analisarAtual(t, lm, agora, disparo){
  if(vis(lm[P.QUADRIL_E]) < VIS_MIN || vis(lm[P.QUADRIL_D]) < VIS_MIN){
    t.quedaDesde = 0; t.correDesde = 0; return;
  }
  const q = meio(lm,P.QUADRIL_E,P.QUADRIL_D);
  const o = meio(lm,P.OMBRO_E,P.OMBRO_D);
  const pe = meio(lm,P.TORN_E,P.TORN_D);
  const tronco = Math.abs(o.y - q.y);
  const joelho = meio(lm,P.JOELHO_E,P.JOELHO_D);
  let altura;
  if(vis(lm[P.TORN_E]) > VIS_MIN || vis(lm[P.TORN_D]) > VIS_MIN)
    altura = Math.abs(pe.y - o.y) * 1.25;
  else if(vis(lm[P.JOELHO_E]) > VIS_MIN || vis(lm[P.JOELHO_D]) > VIS_MIN)
    altura = Math.abs(joelho.y - o.y) * 1.9;
  else altura = tronco * 3.2;
  altura = Math.max(0.08, altura);
  const ang = Math.abs(Math.atan2(o.x - q.x, q.y - o.y) * 180 / Math.PI);

  if(!t.hist) t.hist = [];
  t.hist.push({ t:agora, qx:q.x, qy:q.y, ang });
  t.hist = t.hist.filter(h => agora - h.t < HIST_MS);

  const jan = t.hist.filter(h => agora - h.t < 900);
  const maisAlto = Math.min.apply(null, jan.map(h => h.qy));
  const deitado = ang > QUEDA_ANG;
  if(deitado && (q.y - maisAlto) > QUEDA_CAI && !t.quedaDesde) t.quedaDesde = agora;
  if(!deitado) t.quedaDesde = 0;
  if(t.quedaDesde && agora - t.quedaDesde > QUEDA_SEG) disparo('queda');

  const ant = t.hist.find(h => agora - h.t < 320 && agora - h.t > 80);
  if(ant){
    const dt = (agora - ant.t)/1000;
    t.vel = Math.abs(q.x - ant.qx) / altura / dt;
    if(t.vel > CORRE_VEL){
      if(!t.correDesde) t.correDesde = agora;
      else if(agora - t.correDesde > CORRE_SEG) disparo('corrida');
    } else t.correDesde = 0;
  }
}


/* ===== REGRA NOVA ====================================================== */
/* O quadro é 4:3, e isso importa. As coordenadas do MediaPipe são normalizadas
   SEPARADAMENTE por largura e por altura, então 0,1 em x e 0,1 em y não são a
   mesma distância na sala. Dividir deslocamento horizontal pela altura do corpo
   (que é vertical) subestimava a velocidade pelo fator do formato: uma corrida
   real de 3 m/s aparecia como 1,33 alturas por segundo em vez de 1,77, e ficava
   logo abaixo do limiar de 1,5. */
const ASPECTO = 4/3;

const N_QUEDA_ANG   = 55;    // graus fora da vertical
const N_QUEDA_CAI   = 0.35;  // queda do quadril em ALTURAS DE CORPO, não da tela
const N_QUEDA_SEG   = 1200;
const N_QUEDA_TRONCO= 0.60;  // tronco encolheu para menos disto do próprio máximo
const N_CORRE_VEL   = 1.5;   // alturas de corpo por segundo, na horizontal
const N_CORRE_SEG   = 400;
const N_CORRE_CRESC = 0.55;  // o corpo CRESCE no quadro a esta taxa por segundo

function analisarNovo(t, lm, agora, disparo){
  if(vis(lm[P.QUADRIL_E]) < VIS_MIN || vis(lm[P.QUADRIL_D]) < VIS_MIN){
    t.quedaDesde = 0; t.correDesde = 0; return;
  }
  const q = meio(lm,P.QUADRIL_E,P.QUADRIL_D);
  const o = meio(lm,P.OMBRO_E,P.OMBRO_D);
  const pe = meio(lm,P.TORN_E,P.TORN_D);
  const tronco = Math.abs(o.y - q.y);
  const joelho = meio(lm,P.JOELHO_E,P.JOELHO_D);
  let altura;
  if(vis(lm[P.TORN_E]) > VIS_MIN || vis(lm[P.TORN_D]) > VIS_MIN)
    altura = Math.abs(pe.y - o.y) * 1.25;
  else if(vis(lm[P.JOELHO_E]) > VIS_MIN || vis(lm[P.JOELHO_D]) > VIS_MIN)
    altura = Math.abs(joelho.y - o.y) * 1.9;
  else altura = tronco * 3.2;
  altura = Math.max(0.08, altura);
  const ang = Math.abs(Math.atan2(o.x - q.x, q.y - o.y) * 180 / Math.PI);

  /* O tronco medido ao longo do PRÓPRIO EIXO, não só na vertical.

     A diferença vertical entre ombro e quadril encolhe de duas maneiras que não
     têm nada a ver uma com a outra: quando a pessoa se afasta da câmera, e
     quando ela apenas inclina o corpo para o lado. O teste pegou: uma pessoa
     perto da lente se abaixando e voltando fazia o tronco encolher e crescer, e
     a volta era lida como corrida em direção à câmera.

     Medindo pela diagonal, inclinar no plano da imagem não muda nada — só a
     distância muda. O ASPECTO entra porque x e y são normalizados por lados
     diferentes do quadro. */
  const eixo = Math.hypot((o.x - q.x) * ASPECTO, o.y - q.y);

  if(!t.hist) t.hist = [];
  t.hist.push({ t:agora, qx:q.x, qy:q.y, ang, altura, eixo });
  t.hist = t.hist.filter(h => agora - h.t < HIST_MS);

  /* --- queda --- */
  const jan = t.hist.filter(h => agora - h.t < 900);
  const maisAlto = Math.min.apply(null, jan.map(h => h.qy));
  const caiu = (q.y - maisAlto) / altura > N_QUEDA_CAI;

  /* DUAS formas de estar no chão, e a segunda faltava.

     Caindo de lado, o tronco inclina NA IMAGEM e o ângulo vê. Caindo na
     direção da câmera (ou de costas para ela), o tronco quase não inclina na
     imagem: ele ENCURTA, por perspectiva. O ângulo continua perto de zero e a
     regra antiga não via nada — a pessoa caía de frente para a câmera e o
     sistema não registrava.

     Encurtar o tronco também acontece quando alguém anda para longe, então o
     que separa é a JANELA: 40% em menos de 0,9s não é caminhada, é tombo.
     Agachar não entra aqui de propósito: agachar dobra as PERNAS e o tronco
     continua do mesmo tamanho. */
  const eixoMax = Math.max.apply(null, jan.map(h => h.eixo));
  const encurtou = eixo < eixoMax * N_QUEDA_TRONCO;

  /* TOMBO e CONTINUAR NO CHÃO são perguntas diferentes, e misturá-las quebrava
     a detecção de frente para a câmera.

     Encurtar o tronco é um sinal de MUDANÇA: ele existe enquanto a janela de
     0,9s ainda lembra do tronco inteiro, e some sozinho ~0,9s depois do tombo.
     Usá-lo como "continua no chão" zerava o relógio antes dos 1,2s exigidos —
     a queda era vista e depois esquecida, a menos de 50ms do alerta.

     A correção é congelar a referência: no momento do tombo guardamos o tamanho
     que o tronco TINHA, e daí em diante comparamos contra esse número, que não
     envelhece. */
  if((ang > N_QUEDA_ANG || encurtou) && caiu && !t.quedaDesde){
    t.quedaDesde = agora;
    t.eixoAntes = eixoMax;
  }
  const noChao = t.quedaDesde
    ? (ang > N_QUEDA_ANG || eixo < t.eixoAntes * N_QUEDA_TRONCO)
    : false;
  if(t.quedaDesde && !noChao) t.quedaDesde = 0;
  if(t.quedaDesde && agora - t.quedaDesde > N_QUEDA_SEG) disparo('queda');

  /* --- corrida --- */
  const ant = t.hist.find(h => agora - h.t < 320 && agora - h.t > 80);
  if(ant){
    const dt = (agora - ant.t)/1000;
    const lateral = Math.abs(q.x - ant.qx) * ASPECTO / altura / dt;

    /* APROXIMAÇÃO. Correr na direção da câmera não desloca ninguém de lado: o
       corpo só CRESCE no quadro. A regra antiga media apenas o eixo horizontal,
       então quem vinha correndo em direção à lente nunca era detectado — e num
       corredor de escola, a câmera na ponta é justamente o enquadramento comum.

       Só o crescimento conta, nunca o encolhimento, e isso é deliberado: cair
       na direção da câmera também encolhe o corpo depressa, e sem esse sinal
       toda queda de frente seria registrada como corrida. O preço é que correr
       PARA LONGE da câmera não é detectado por este caminho. */
    /* Cresce o TRONCO, não a altura inteira. Medir a altura reprovou no teste:
       levantar de um agachamento estica as pernas, o corpo cresce no quadro e
       a regra lia isso como alguém correndo em direção à lente — amarrar o
       sapato virava corrida. O tronco não muda de tamanho quando se agacha; só
       muda com a distância da câmera, que é exatamente o que se quer medir. */
    const cresc = (eixo - ant.eixo) / eixo / dt;

    if(lateral > N_CORRE_VEL || cresc > N_CORRE_CRESC){
      if(!t.correDesde) t.correDesde = agora;
      else if(agora - t.correDesde > N_CORRE_SEG) disparo('corrida');
    } else t.correDesde = 0;
  }
}

/* ===== fabricação de cenários ==========================================
   Um corpo em coordenadas normalizadas. `escala` é a altura do corpo em
   frações da tela — é ela que representa a distância da câmera. `incl` é a
   inclinação do tronco em graus (0 = em pé). `agacha` encurta as pernas sem
   inclinar, que é o que acontece de verdade quando alguém se agacha. */
function pose({ x=0.5, quadrilY=0.60, escala=0.55, incl=0, agacha=0, visPe=true }){
  const lm = Array.from({length:33}, () => ({x, y:quadrilY, visibility:0}));
  const p = (i,px,py,v=0.95) => lm[i] = {x:px, y:py, z:0, visibility:v};
  const rad = incl * Math.PI/180;
  const tronco = escala * 0.30;
  const ox = x + Math.sin(rad)*tronco, oy = quadrilY - Math.cos(rad)*tronco;
  const perna = escala * 0.50 * (1 - agacha);
  const ombro = escala * 0.20;

  p(P.NARIZ,   ox + Math.sin(rad)*escala*0.12, oy - Math.cos(rad)*escala*0.12);
  p(2, ox-0.01, oy-escala*0.14); p(5, ox+0.01, oy-escala*0.14);
  p(P.OMBRO_E, ox - ombro/2, oy); p(P.OMBRO_D, ox + ombro/2, oy);
  p(P.COTOV_E, ox - ombro*0.7, oy + tronco*0.5);
  p(P.COTOV_D, ox + ombro*0.7, oy + tronco*0.5);
  p(P.PULSO_E, ox - ombro*0.8, oy + tronco*0.9);
  p(P.PULSO_D, ox + ombro*0.8, oy + tronco*0.9);
  p(P.QUADRIL_E, x - ombro*0.35, quadrilY); p(P.QUADRIL_D, x + ombro*0.35, quadrilY);
  p(P.JOELHO_E, x - ombro*0.3, quadrilY + perna*0.55);
  p(P.JOELHO_D, x + ombro*0.3, quadrilY + perna*0.55);
  if(visPe){
    p(P.TORN_E, x - ombro*0.3, quadrilY + perna);
    p(P.TORN_D, x + ombro*0.3, quadrilY + perna);
  }
  return lm;
}

/* Uma cena: função do tempo (ms) para os parâmetros da pose. 30fps. */
function rodar(cena, dur, analisar){
  const t = {}; const vistos = new Set();
  for(let ms = 0; ms <= dur; ms += 33){
    const lm = pose(cena(ms));
    analisar(t, lm, ms, tipo => vistos.add(tipo));
  }
  return vistos;
}
const suave = (a,b,k) => a + (b-a) * (k<=0?0:k>=1?1:(1-Math.cos(k*Math.PI))/2);

const CENARIOS = [
  /* --- deve disparar QUEDA --- */
  { nome:'queda de lado (rápida)', espera:['queda'], dur:4000, cena: ms => {
      const k = (ms-500)/450;                       // tomba em ~0.45s
      return { quadrilY: suave(0.60,0.82,k), incl: suave(0,80,k) }; } },

  { nome:'queda para a frente da câmera', espera:['queda'], dur:4000, cena: ms => {
      /* Caindo NA DIREÇÃO da câmera o tronco quase não inclina na imagem: ele
         encurta. É o caso que a inclinação sozinha não vê. */
      const k = (ms-500)/450;
      return { quadrilY: suave(0.60,0.80,k), escala: suave(0.55,0.30,k),
               incl: suave(0,15,k) }; } },

  { nome:'queda de alguém longe da câmera', espera:['queda'], dur:4000, cena: ms => {
      const k = (ms-500)/450;
      return { quadrilY: suave(0.45,0.55,k), escala:0.22, incl: suave(0,80,k) }; } },

  /* Estes dois existem por causa de UM número: o quanto o quadril precisa
     descer. Ele era medido em fração da TELA, o que é a mesma armadilha que o
     resto do projeto já tinha resolvido em toda parte — quem está longe nunca
     desce 10% da tela, e quem está perto desce isso ao se mexer. Agora é medido
     em ALTURAS DE CORPO, e os dois casos saem certos. */
  { nome:'queda no fundo da sala', espera:['queda'], dur:4000, cena: ms => {
      const k = (ms-500)/450;
      return { quadrilY: suave(0.42,0.48,k), escala:0.15, incl: suave(0,80,k) }; } },

  /* --- NÃO deve disparar --- */
  { nome:'close: se abaixa um pouco', espera:[], dur:4000, cena: ms => {
      /* Pessoa perto da câmera, tronco inclinado, quadril descendo 0,11 da tela
         — mais que o limiar antigo de 0,10, e ainda assim é só se abaixar. */
      const k = (ms-500)/700, v = (ms-2800)/700;
      return { escala:0.90, quadrilY: suave(0.50,0.61,k) - suave(0,0.11,v),
               incl: suave(0,60,k) - suave(0,60,v) }; } },

  /* O ENQUADRAMENTO QUE A ESCOLA VAI USAR DE VERDADE: câmera no alto da sala,
     quadril visível, PÉS FORA DO QUADRO. Todos os cenários acima têm os pés à
     vista, que é o caso fácil — a régua de altura sai direto do tornozelo. Sem
     os pés ela é ESTIMADA pelo joelho, e é essa estimativa que precisa aguentar
     os limiares. Sem estes três cenários, o teste só provava o caso fácil. */
  { nome:'queda sem os pés no quadro', espera:['queda'], dur:4000, cena: ms => {
      const k = (ms-500)/450;
      return { quadrilY: suave(0.55,0.80,k), incl: suave(0,80,k), visPe:false }; } },

  { nome:'corrida sem os pés no quadro', espera:['corrida'], dur:3000, cena: ms =>
      ({ x: 0.12 + Math.min(0.80, ms/1000*0.73), visPe:false }) },

  { nome:'agachar sem os pés no quadro', espera:[], dur:4000, cena: ms => {
      const k = (ms-500)/700, v = (ms-2500)/700;
      return { quadrilY: suave(0.55,0.69,k) - suave(0,0.14,v), visPe:false,
               agacha: suave(0,0.55,k) - suave(0,0.55,v),
               incl: suave(0,35,k) - suave(0,35,v) }; } },

  { nome:'agachar para pegar algo', espera:[], dur:4000, cena: ms => {
      const k = (ms-500)/700, v = (ms-2500)/700;    // desce e volta
      return { quadrilY: suave(0.60,0.74,k) - suave(0,0.14,v),
               agacha: suave(0,0.55,k) - suave(0,0.55,v), incl: suave(0,35,k)-suave(0,35,v) }; } },

  { nome:'amarrar o sapato (agachado 3s)', espera:[], dur:5000, cena: ms => {
      const k = (ms-400)/600, v = (ms-4000)/600;
      return { quadrilY: suave(0.60,0.76,k) - suave(0,0.16,v),
               agacha: suave(0,0.7,k) - suave(0,0.7,v), incl: suave(0,45,k)-suave(0,45,v) }; } },

  { nome:'sentar na cadeira', espera:[], dur:5000, cena: ms => {
      const k = (ms-500)/900;
      return { quadrilY: suave(0.60,0.72,k), agacha: suave(0,0.45,k), incl: suave(0,12,k) }; } },

  { nome:'em pé, parado', espera:[], dur:3000, cena: () => ({}) },

  /* --- deve disparar CORRIDA --- */
  /* 0,73 da largura por segundo. A conta: uma pessoa de 1,70m ocupando 0,55 da
     altura da tela está a uma distância onde a tela cobre ~3,1m na vertical e
     ~4,1m na horizontal (quadro 4:3). Correr a 3 m/s é 0,73 dessas larguras por
     segundo. Vale escrever a conta porque a primeira versão deste cenário usava
     0,42 — que é trote, não corrida — e fazia a regra parecer quebrada. */
  { nome:'correndo de lado', espera:['corrida'], dur:3000, cena: ms => {
      return { x: 0.12 + Math.min(0.80, ms/1000 * 0.73) }; } },

  { nome:'correndo em direção à câmera', espera:['corrida'], dur:3000, cena: ms => {
      /* Sem deslocamento lateral nenhum: só o corpo crescendo no quadro. */
      const k = Math.min(1, ms/1800);
      return { escala: suave(0.20,0.75,k), quadrilY: suave(0.50,0.66,k) }; } },

  /* --- NÃO deve disparar --- */
  { nome:'andando normal', espera:[], dur:3000, cena: ms => ({ x: 0.25 + ms/1000*0.10 }) },
  { nome:'andando rápido', espera:[], dur:3000, cena: ms => ({ x: 0.20 + ms/1000*0.18 }) },
  { nome:'parado gesticulando', espera:[], dur:3000, cena: ms =>
      ({ x: 0.5 + Math.sin(ms/120)*0.006 }) },

  /* Andando em direção à câmera. O corpo cresce no quadro, igual à corrida —
     só que devagar. É o cenário que impede o novo sinal de aproximação de virar
     um detector de "alguém veio falar comigo". */
  { nome:'andando em direção à câmera', espera:[], dur:4000, cena: ms => {
      const k = Math.min(1, ms/3500);
      return { escala: suave(0.20,0.42,k), quadrilY: suave(0.50,0.60,k) }; } },

  /* Andando PARA LONGE. O corpo encolhe — e encolher rápido é o sinal que
     passa a detectar queda na direção da câmera. Aqui não pode disparar. */
  { nome:'andando para longe da câmera', espera:[], dur:4000, cena: ms => {
      const k = Math.min(1, ms/3500);
      return { escala: suave(0.55,0.24,k), quadrilY: suave(0.66,0.50,k) }; } },
];

/* ===== a cópia está velha? ============================================= */
{
  const sala = fs.readFileSync(new URL('../auditix-sala.html', import.meta.url), 'utf8');
  const daSala = nome => {
    const m = sala.match(new RegExp('const ' + nome + '\\s*=\\s*([0-9./]+)'));
    return m ? eval(m[1]) : null;
  };
  const conferir = {
    QUEDA_ANG:N_QUEDA_ANG, QUEDA_CAI:N_QUEDA_CAI, QUEDA_SEG:N_QUEDA_SEG,
    QUEDA_EIXO:N_QUEDA_TRONCO, CORRE_VEL:N_CORRE_VEL, CORRE_SEG:N_CORRE_SEG,
    CORRE_CRESC:N_CORRE_CRESC,
  };
  const fora = Object.entries(conferir)
    .filter(([nome, aqui]) => daSala(nome) !== aqui)
    .map(([nome, aqui]) => `${nome}: Sala=${daSala(nome)} teste=${aqui}`);
  if(fora.length){
    console.log('\nESTE TESTE ESTÁ DESSINCRONIZADO DA SALA:');
    fora.forEach(l => console.log('  ' + l));
    console.log('\nAtualize a cópia antes de acreditar no resultado.\n');
    process.exit(1);
  }
}

/* ===== execução ======================================================== */
const igual = (a,b) => a.size===b.length && b.every(x=>a.has(x));
let falhas = 0;
console.log('\ncenário                          esperado    antes       depois');
console.log('─'.repeat(70));
for(const c of CENARIOS){
  const antes = rodar(c.cena, c.dur, analisarAtual);
  const got   = rodar(c.cena, c.dur, analisarNovo);
  const ok = igual(got, c.espera);
  if(!ok) falhas++;
  const txt = x => (Array.from(x).join(',')||'—');
  console.log((ok?'OK    ':'FALHA ') + c.nome.padEnd(26) +
    (c.espera.join(',')||'—').padEnd(12) + txt(antes).padEnd(12) + txt(got) +
    (igual(antes,c.espera) ? '' : '   <- consertado'));
}
console.log('─'.repeat(64));
console.log(falhas ? `\n${falhas} de ${CENARIOS.length} cenários falharam\n`
                   : '\nTODOS OS CENÁRIOS PASSARAM\n');
process.exit(falhas ? 1 : 0);
