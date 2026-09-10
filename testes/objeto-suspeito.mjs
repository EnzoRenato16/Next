/* Teste da camada de objeto suspeito — roda com:  node testes/objeto-suspeito.mjs
 *
 * A saída do YOLOv8 vem CRUA, sem NMS, e num formato que engana: o tensor é
 * (1, 4+classes, 8400) e está organizado por LINHA, não por caixa. Ou seja, o
 * cx de todas as 8400 caixas vem primeiro, depois todos os cy, e assim por
 * diante. Quem lê como se fosse [caixa][campo] não recebe erro nenhum — recebe
 * números plausíveis e errados, e um detector de arma que aponta para o lugar
 * errado é pior que detector nenhum.
 *
 * Por isso o teste planta caixas em posições conhecidas e exige que o
 * decodificador as devolva de volta, com o letterbox desfeito.
 *
 * A leitura do JS já foi conferida contra a do Python (daten/app/armas.py) no
 * tensor real do modelo: as 10 caixas de maior confiança bateram índice a
 * índice, com erro de no máximo 0.0005 px. Este arquivo guarda a regra; aquela
 * conferência guardou o acordo entre as duas implementações.
 *
 * As funções abaixo são COPIADAS de auditix-sala.html. Mudou lá, cole aqui.
 */

const ARMA_LADO = 640, ARMA_CONF = 0.60, ARMA_NMS = 0.45;
const ARMA_HITS = 4, ARMA_SILENCIO = 30000;
const ARMA_CLASSES = ['pistol', 'knife'];
const ARMA_ROTULO = { pistol:'objeto tipo arma de fogo', knife:'objeto tipo lâmina' };

/* ===== COPIADO de auditix-sala.html ==================================== */
function nmsArma(caixas, scores, limiar){
  const ordem = scores.map((s, i) => i).sort((a, b) => scores[b] - scores[a]);
  const ficam = [];
  while(ordem.length){
    const i = ordem.shift();
    ficam.push(i);
    for(let k = ordem.length - 1; k >= 0; k--){
      const a = caixas[i], b = caixas[ordem[k]];
      const x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]);
      const x2 = Math.min(a[0]+a[2], b[0]+b[2]), y2 = Math.min(a[1]+a[3], b[1]+b[3]);
      const w = x2 - x1, h = y2 - y1;
      if(w <= 0 || h <= 0) continue;
      const inter = w * h;
      if(inter / (a[2]*a[3] + b[2]*b[3] - inter) > limiar) ordem.splice(k, 1);
    }
  }
  return ficam;
}
/* O miolo do verArmas(), sem o ONNX: recebe o tensor e devolve os achados. */
function decodificar(d, dims, escala, dx, dy){
  const nc = dims[1] - 4, n = dims[2];
  const caixas = [], scores = [], classes = [];
  for(let i = 0; i < n; i++){
    let melhor = 0, conf = d[4*n + i];
    for(let c = 1; c < nc; c++)
      if(d[(4+c)*n + i] > conf){ conf = d[(4+c)*n + i]; melhor = c; }
    if(conf < ARMA_CONF) continue;
    const cx = d[i], cy = d[n + i], w = d[2*n + i], h = d[3*n + i];
    caixas.push([ (cx - w/2 - dx)/escala, (cy - h/2 - dy)/escala, w/escala, h/escala ]);
    scores.push(conf); classes.push(melhor);
  }
  return nmsArma(caixas, scores, ARMA_NMS).map(i => ({
    classe: ARMA_CLASSES[classes[i]] || '?',
    rotulo: ARMA_ROTULO[ARMA_CLASSES[classes[i]]] || 'objeto suspeito',
    conf: scores[i], box: caixas[i] }));
}
/* ===== fim da cópia ==================================================== */

/* O letterbox de um vídeo 1280x960 dentro de 640x640. */
const V_LARG = 1280, V_ALT = 960;
const ESCALA = Math.min(ARMA_LADO/V_LARG, ARMA_LADO/V_ALT);
const DX = (ARMA_LADO - Math.round(V_LARG*ESCALA)) >> 1;
const DY = (ARMA_LADO - Math.round(V_ALT*ESCALA)) >> 1;

const N = 8400, DIMS = [1, 6, N];
function tensor(caixas){
  const d = new Float32Array(6 * N);
  caixas.forEach(({ i, cx, cy, w, h, classe, conf }) => {
    d[i] = cx; d[N+i] = cy; d[2*N+i] = w; d[3*N+i] = h;
    d[(4+classe)*N + i] = conf;
  });
  return d;
}
/* Converte uma caixa do VÍDEO para a escala 640 do letterbox — o caminho
   inverso do que o decodificador faz. Se os dois concordam, o letterbox está
   sendo desfeito certo. */
function paraModelo(x, y, w, h){
  return { cx:(x + w/2)*ESCALA + DX, cy:(y + h/2)*ESCALA + DY,
           w:w*ESCALA, h:h*ESCALA };
}

let falhas = 0;
const teste = (nome, cond, detalhe='') => {
  if(!cond) falhas++;
  console.log((cond ? 'OK    ' : 'FALHA ') + nome + (detalhe ? '   ' + detalhe : ''));
};
const perto = (a, b, tol=0.01) => Math.abs(a-b) <= tol;

console.log('\n— decodificação ——————————————————————————————————————');
{
  /* Uma lâmina em (300, 400), 120x40 px no vídeo. */
  const alvo = { x:300, y:400, w:120, h:40 };
  const m = paraModelo(alvo.x, alvo.y, alvo.w, alvo.h);
  const r = decodificar(tensor([{ i:1234, ...m, classe:1, conf:0.91 }]), DIMS, ESCALA, DX, DY);
  teste('acha a caixa plantada', r.length === 1, `achou ${r.length}`);
  if(r.length === 1){
    const [bx, by, bw, bh] = r[0].box;
    teste('desfaz o letterbox e volta à escala do vídeo',
      perto(bx, alvo.x) && perto(by, alvo.y) && perto(bw, alvo.w) && perto(bh, alvo.h),
      `[${bx.toFixed(1)}, ${by.toFixed(1)}, ${bw.toFixed(1)}, ${bh.toFixed(1)}]`);
    teste('lê a classe certa', r[0].classe === 'knife', r[0].classe);
    teste('rótulo nunca afirma "arma"', !/^arma/i.test(r[0].rotulo), `"${r[0].rotulo}"`);
  }
}
{
  /* A ARMADILHA, e ela é pior do que "não funciona": lendo o tensor como
     [caixa][campo], os valores de coordenada (que estão na escala 0..640) caem
     nas posições de confiança e passam folgadamente do limiar de 0.60. O
     detector não fica cego — fica ALUCINANDO, apontando caixas onde não há
     nada. Numa camada que alerta a escola sobre arma, esse é o pior modo de
     falha possível, e ele é silencioso. */
  const m = paraModelo(300, 400, 120, 40);
  const d = tensor([{ i:1234, ...m, classe:1, conf:0.91 }]);
  const errado = [];
  for(let i = 0; i < N; i++){
    const conf = Math.max(d[i*6 + 4] || 0, d[i*6 + 5] || 0);
    if(conf >= ARMA_CONF) errado.push(i);
  }
  teste('a leitura errada INVENTA achados (é por isso que este teste existe)',
    errado.length > 0, `${errado.length} caixas fantasmas`);
  teste('a leitura certa acha só a caixa plantada',
    decodificar(d, DIMS, ESCALA, DX, DY).length === 1);
}
{
  const m = paraModelo(300, 400, 120, 40);
  const r = decodificar(tensor([{ i:1234, ...m, classe:1, conf:0.59 }]), DIMS, ESCALA, DX, DY);
  teste('confiança abaixo de ' + ARMA_CONF + ' é descartada', r.length === 0);
}

console.log('\n— supressão de não-máximos ——————————————————————————');
{
  /* O mesmo objeto detectado três vezes, com deslocamentos de poucos pixels. */
  const base = paraModelo(300, 400, 120, 40);
  const r = decodificar(tensor([
    { i:10, ...base, classe:1, conf:0.91 },
    { i:11, ...paraModelo(304, 402, 120, 40), classe:1, conf:0.88 },
    { i:12, ...paraModelo(297, 398, 122, 41), classe:1, conf:0.85 },
  ]), DIMS, ESCALA, DX, DY);
  teste('um objeto não vira três alertas', r.length === 1, `sobraram ${r.length}`);
  teste('sobra a leitura de maior confiança', r[0] && perto(r[0].conf, 0.91, 1e-6));
}
{
  /* Dois objetos separados continuam dois. */
  const r = decodificar(tensor([
    { i:10, ...paraModelo(100, 200, 100, 40), classe:1, conf:0.80 },
    { i:11, ...paraModelo(800, 700,  90, 90), classe:0, conf:0.75 },
  ]), DIMS, ESCALA, DX, DY);
  teste('dois objetos separados continuam dois', r.length === 2, `sobraram ${r.length}`);
}

console.log('\n— travas contra alarme falso ————————————————————————');
{
  /* Réplica da regra do confirmarArmas(), com relógio controlado. */
  const seguidas = {}, avisado = {};
  let alertas = 0;
  function passo(classes, agora){
    const vistos = new Set(classes);
    vistos.forEach(c => {
      seguidas[c] = (seguidas[c] || 0) + 1;
      if(seguidas[c] !== ARMA_HITS) return;
      if(agora - (avisado[c] || -1e12) < ARMA_SILENCIO) return;
      avisado[c] = agora; alertas++;
    });
    Object.keys(seguidas).forEach(c => {
      if(!vistos.has(c)) seguidas[c] = Math.max(0, seguidas[c] - 1);
    });
  }

  let t = 0;
  passo(['knife'], t+=100); passo(['knife'], t+=100); passo(['knife'], t+=100);
  teste('3 leituras seguidas ainda não alertam', alertas === 0, `${alertas} alertas`);
  passo(['knife'], t+=100);
  teste('a 4ª leitura seguida alerta', alertas === 1, `${alertas} alertas`);

  for(let k = 0; k < 50; k++) passo(['knife'], t+=100);
  teste('objeto parado não alerta a cada quadro', alertas === 1, `${alertas} alertas`);

  passo([], t+=100);
  teste('sumiu do quadro: o contador DESCE, não zera',
    seguidas['knife'] === ARMA_HITS + 50 - 1);
}
{
  /* Um reflexo que pisca: aparece, some, aparece. Nunca chega a 4 seguidas. */
  const seguidas = {}; let alertas = 0;
  function passo(classes){
    const vistos = new Set(classes);
    vistos.forEach(c => {
      seguidas[c] = (seguidas[c] || 0) + 1;
      if(seguidas[c] === ARMA_HITS) alertas++;
    });
    Object.keys(seguidas).forEach(c => {
      if(!vistos.has(c)) seguidas[c] = Math.max(0, seguidas[c] - 1);
    });
  }
  for(let k = 0; k < 30; k++) passo(k % 2 ? ['knife'] : []);
  teste('reflexo que pisca nunca vira evento', alertas === 0, `${alertas} alertas`);
}

console.log('\n' + (falhas ? `${falhas} TESTE(S) FALHARAM\n` : 'TODOS OS TESTES PASSARAM\n'));
process.exit(falhas ? 1 : 0);
