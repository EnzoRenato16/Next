/* Registro de calibração — roda com:  node testes/calibracao.mjs
 *
 * Precisa do servidor no ar COM o registro ligado:
 *     CALIBRACAO=1 uv run servidor.py
 *
 * POR QUE ESTE REGISTRO EXISTE, que é o que o teste tem de proteger:
 *
 * O Auditix só deixava rastro quando disparava. Isso responde "quantos alertas
 * houve" e não responde a pergunta que decide se ele serve numa escola: QUANTAS
 * VEZES ELE QUASE DISPAROU SEM MOTIVO. Num dia comum de aula, a maior nota que
 * NÃO virou alerta é a margem de segurança real. Limiar 0,50 com pico do dia em
 * 0,31 é folga; pico em 0,49 é um quadro ruim de distância de um alarme falso —
 * e isso não aparece em lugar nenhum se só o que dispara for registrado.
 *
 * O INVARIANTE MAIS IMPORTANTE, e o primeiro do arquivo:
 * amostra de calibração NÃO entra na cadeia de hash. A cadeia é a nossa
 * afirmação sobre o que ACONTECEU, e uma amostra é uma medida do que o sistema
 * VIU. Misturar as duas encheria a corrente de dezenas de milhares de elos por
 * aula e destruiria a coisa que o projeto tem de mais defensável. É também o
 * que autoriza podar esta tabela: a de eventos nunca perde linha, esta pode e
 * deve.
 */
const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const CAM = 'teste-calib-' + Date.now();

let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};

const amostra = (o = {}) => ({
  corpo:1, fps:30, analisavel:1, nota:0, fora:0, geo:0,
  vel:0, ang:5, baixo:1, prop:0.5, alertou:'', ...o });

const mandar = async (amostras, camera = CAM) => {
  const r = await fetch(BASE + '/api/calibracao', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ camera, amostras }) });
  return { status: r.status, corpo: await r.json().catch(() => null) };
};

const resumo = async (camera = CAM) =>
  (await fetch(BASE + '/api/calibracao?camera=' + camera)).json();

const cadeia = async () => (await fetch(BASE + '/api/verificar')).json();

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE +
                     ' (CALIBRACAO=1 uv run servidor.py)'); process.exit(1); }

const primeiro = await mandar([amostra()]);
if(primeiro.status === 403){
  console.error('o registro está DESLIGADO neste servidor.\n' +
                'suba com:  CALIBRACAO=1 uv run servidor.py');
  process.exit(1);
}

/* ---- 1. o invariante: amostra não vira elo da corrente ------------------- */
const antes = await cadeia();
await mandar(Array.from({length: 50}, (_, i) => amostra({ corpo:i % 4, nota:i/100 })));
const depois = await cadeia();
ok('50 amostras NÃO viram elos na cadeia de hash',
   depois.total === antes.total && depois.integra,
   'elos ' + antes.total + ' -> ' + depois.total + ', íntegra: ' + depois.integra);

/* ---- 2. a margem: o pico entre as amostras CALMAS ------------------------ */
const cam2 = CAM + '-margem';
await mandar([
  amostra({ nota:0.12 }),
  amostra({ nota:0.44 }),            // o pico calmo: a margem real
  amostra({ nota:0.31 }),
  /* Esta passou de 0,50 mas ACUSOU — então não é margem, é acerto (ou erro já
     conhecido). Se ela entrasse na conta, o pico calmo viria 0,93 e diria que
     o sistema viveu à beira do limiar o dia todo, o que é falso. */
  amostra({ nota:0.93, alertou:'queda' }),
], cam2);
const r2 = await resumo(cam2);
ok('a margem é o maior valor entre as amostras que NÃO acusaram',
   Math.abs(r2.margem.maior_nota_sem_alerta - 0.44) < 1e-6,
   'pico calmo ' + r2.margem.maior_nota_sem_alerta + ' (e não 0.93, que acusou)');
ok('e a amostra que acusou é contada como alerta',
   r2.alertas.queda === 1, JSON.stringify(r2.alertas));

/* ---- 3. o corpo cortado no quadro conta, e conta separado ---------------- */
const cam3 = CAM + '-cego';
await mandar([ amostra(), amostra({ analisavel:0 }), amostra({ analisavel:0 }),
               amostra() ], cam3);
const r3 = await resumo(cam3);
ok('a fração de tempo sem poder julgar é medida',
   r3.cegas_pct === 50.0, r3.cegas_pct + '% de amostras cegas');
/* E ela não pode envenenar a margem: sem quadril à vista, `nota` é lixo. */
const cam3b = CAM + '-cego2';
await mandar([ amostra({ nota:0.20 }), amostra({ nota:0.99, analisavel:0 }) ], cam3b);
const r3b = await resumo(cam3b);
ok('amostra cega não entra no cálculo da margem',
   Math.abs(r3b.margem.maior_nota_sem_alerta - 0.20) < 1e-6,
   'pico calmo ' + r3b.margem.maior_nota_sem_alerta + ', ignorando o 0.99 sem quadril');

/* ---- 4. fora do treino é contado ----------------------------------------- */
const cam4 = CAM + '-fora';
await mandar([ amostra({ fora:1 }), amostra({ fora:9 }), amostra({ fora:2 }),
               amostra({ fora:7 }) ], cam4);
const r4 = await resumo(cam4);
ok('as janelas em que a rede foi descartada por extrapolação são contadas',
   r4.fora_do_treino_pct === 50.0, r4.fora_do_treino_pct + '%');

/* ---- 5. histograma ------------------------------------------------------- */
const cam5 = CAM + '-faixas';
await mandar([ amostra({ nota:0.05 }), amostra({ nota:0.15 }),
               amostra({ nota:0.17 }), amostra({ nota:0.45 }) ], cam5);
const r5 = await resumo(cam5);
ok('o histograma separa as faixas de nota',
   r5.faixas_de_nota['0.1-0.2'] === 2 && r5.faixas_de_nota['0.0-0.1'] === 1 &&
   r5.faixas_de_nota['0.4-0.5'] === 1,
   JSON.stringify(r5.faixas_de_nota['0.1-0.2']) + ' na faixa 0.1-0.2');

/* ---- 6. velocidade de corrida tem a própria margem ----------------------- */
const cam6 = CAM + '-vel';
await mandar([ amostra({ vel:0.71 }), amostra({ vel:0.98 }),
               amostra({ vel:1.90, alertou:'corrida' }) ], cam6);
const r6 = await resumo(cam6);
ok('a corrida tem margem própria, e também ignora quem acusou',
   Math.abs(r6.margem.maior_velocidade_sem_alerta - 0.98) < 1e-6,
   'pico calmo ' + r6.margem.maior_velocidade_sem_alerta + ' contra limiar ' +
   r6.margem.limiar_velocidade);

/* ---- 6b. a folga vem pronta, e avisa quando é negativa ------------------
   Quem lê este resumo está decidindo se pode instalar numa escola. Obrigá-lo a
   subtrair dois campos de cabeça para saber se o dia foi tranquilo ou por um
   fio é transferir para ele o trabalho que o servidor pode fazer. */
const cam6b = CAM + '-folga';
await mandar([ amostra({ nota:0.10, vel:0.3 }), amostra({ nota:0.47, vel:0.4 }) ], cam6b);
const r6b = await resumo(cam6b);
ok('a folga até o limiar vem calculada',
   Math.abs(r6b.margem.folga_nota - 0.03) < 1e-6,
   'folga de ' + r6b.margem.folga_nota);
ok('e a leitura em português avisa que está apertado',
   /chegou a .* do limiar/.test(r6b.margem.leitura), r6b.margem.leitura);

const cam6c = CAM + '-passou';
await mandar([ amostra({ nota:0.05, vel:1.45 }) ], cam6c);
const r6c = await resumo(cam6c);
ok('e quando alguma janela PASSA do limiar sem alertar, a leitura diz isso',
   r6c.margem.folga_velocidade < 0 && /PASSOU do limiar/.test(r6c.margem.leitura),
   r6c.margem.leitura);

const cam6d = CAM + '-calmo';
await mandar([ amostra({ nota:0.04, vel:0.2 }) ], cam6d);
ok('e num período calmo ela diz que há folga',
   /folga confortável/.test((await resumo(cam6d)).margem.leitura));

/* ---- 7. planilha --------------------------------------------------------- */
const rcsv = await fetch(BASE + '/api/calibracao.csv?camera=' + cam5);
const csv = await rcsv.text();
const linhas = csv.trim().split('\n');
ok('o CSV sai com cabeçalho e uma linha por amostra',
   linhas.length === 5 && linhas[0].startsWith('momento,corpo,fps'),
   linhas.length - 1 + ' linhas de dados');
ok('e vem como anexo, para o Excel abrir',
   /attachment/.test(rcsv.headers.get('content-disposition') || ''));

/* ---- 7b. o CSV não se desalinha com texto vindo de fora ------------------ */
const cam7b = CAM + '-virgula';
await mandar([ amostra({ alertou:'que,da\nx' }) ], cam7b);
const csv2 = (await (await fetch(BASE + '/api/calibracao.csv?camera=' + cam7b)).text()).trim();
const corpoCsv = csv2.split('\n');
ok('vírgula vinda de fora não parte a linha do CSV',
   corpoCsv.length === 2 &&
   corpoCsv[1].split(',').length === corpoCsv[0].split(',').length,
   corpoCsv[1].split(',').length + ' colunas contra ' +
   corpoCsv[0].split(',').length + ' no cabeçalho');

/* ---- 8. teto de lote ----------------------------------------------------- */
const grande = await mandar(Array.from({length: 501}, () => amostra()), CAM + '-teto');
ok('lote acima do teto é recusado', grande.status === 413, 'HTTP ' + grande.status);

/* ---- 9. câmera sem amostra não inventa número --------------------------- */
const vazio = await resumo(CAM + '-nunca-usada');
ok('câmera sem amostra responde "sem amostras", não zeros',
   vazio.status === 'sem_amostras', JSON.stringify(vazio.status));

/* ---- 10. a SALA de verdade coleta e envia -------------------------------
   Tudo acima prova o servidor. Isto prova o outro lado, e é onde um teste
   preguiçoso mentiria: dá para o servidor estar perfeito e o navegador nunca
   mandar nada — foi exatamente assim que a foto do alerta ficou um dia sem
   subir, com o endpoint respondendo 200 para ninguém.

   A câmera não enxerga gente num vídeo sintético, então não haveria trilha
   firme nenhuma. Em vez de fingir uma pessoa, o teste chama a função REAL do
   arquivo com uma trilha montada à mão e confere o que sai na rede. */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/', { timeout:20000 });
await pg.waitForFunction(() => typeof amostrarCalibracao === 'function', { timeout:10000 });

/* A Sala grava sob o nome fixo da própria câmera (LOCAL_CAMERA é const, e está
   certo que seja). Então o teste lê desse nome em vez de forçar outro — e por
   isso conta a diferença de amostras, não o total. */
const camSala = 'sala-12';
const antesSala = await resumo(camSala);
const jaTinha = antesSala.status === 'ok' ? antesSala.amostras : 0;
const enviado = await pg.evaluate(async () => {
  servidorVivo = true;
  const t = { id:7, firme:true, fps:24, notaQueda:0.37, foraDoTreino:2.1,
              quedaDesde:0, velocidade:0.88, ang:9, baixo:0.96, prop:0.44 };
  // duas chamadas coladas: a segunda tem de ser recusada pelo intervalo
  amostrarCalibracao(t, 1000, true);
  amostrarCalibracao(t, 1100, true);
  const naFila = calibFila.length;
  amostrarCalibracao(t, 3000, true);   // passou de CALIB_MS, entra
  const depois = calibFila.length;
  mandarCalibracao();
  await new Promise(r => setTimeout(r, 800));
  return { naFila, depois, sobrou: calibFila.length };
});

ok('a Sala respeita o intervalo entre amostras do mesmo corpo',
   enviado.naFila === 1 && enviado.depois === 2,
   'duas chamadas em 100ms deram ' + enviado.naFila + ' amostra, ' +
   'e a de 2s depois virou a ' + enviado.depois + 'ª');
ok('e a fila é esvaziada ao enviar', enviado.sobrou === 0);

const rSala = await resumo(camSala);
ok('os números da Sala chegam inteiros ao servidor',
   rSala.amostras === jaTinha + 2 &&
   Math.abs(rSala.margem.maior_nota_sem_alerta - 0.37) < 1e-6 &&
   Math.abs(rSala.margem.maior_velocidade_sem_alerta - 0.88) < 1e-6,
   (rSala.amostras - jaTinha) + ' amostras novas, nota ' +
   rSala.margem.maior_nota_sem_alerta +
   ', velocidade ' + rSala.margem.maior_velocidade_sem_alerta);
ok('nenhum erro de JavaScript na Sala', erros.length === 0, erros.join(' | '));

/* E o desligamento: com o servidor recusando, a Sala tem de PARAR de tentar em
   vez de insistir a cada 15s pelo resto da aula. */
await pg.route('**/api/calibracao', r => r.fulfill({ status:403, body:'{}' }));
const parou = await pg.evaluate(async () => {
  calibrando = true;
  const t = { id:8, firme:true, notaQueda:0.1 };
  amostrarCalibracao(t, 90000, true);
  mandarCalibracao();
  await new Promise(r => setTimeout(r, 600));
  return { calibrando, fila: calibFila.length };
});
ok('recusado pelo servidor, a Sala para de tentar',
   parou.calibrando === false && parou.fila === 0,
   'calibrando=' + parou.calibrando + ', fila=' + parou.fila);

await nav.close();

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : 'todos os ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
