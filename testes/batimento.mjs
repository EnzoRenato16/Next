/* A caixa cega não pode parecer tranquila — roda com:  node testes/batimento.mjs
 *
 * Sobe o PRÓPRIO servidor (porta 8795, banco temporário, SEM_SINAL_S=3), porque
 * o que se testa aqui é o silêncio, e silêncio de 30 s deixaria o teste lento.
 *
 * POR QUE ISTO EXISTE. Antes, caixa travada, cabo solto ou lente tampada davam
 * um painel quieto — igual ao de um dia sem nenhuma ocorrência. Agora o
 * silêncio vira linha da cadeia e toca a sirene, UMA vez por episódio.
 */
import { chromium } from 'playwright';
import { existsSync, mkdtempSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const dormir = ms => new Promise(r => setTimeout(r, ms));
/* Uma nova tentativa: o uvicorn fecha conexão parada depois de 5 s, e o fetch
   do Node às vezes reaproveita justo a que está sendo fechada. */
const fetch = async (...a) => { try{ return await globalThis.fetch(...a); }
  catch{ await dormir(200); return globalThis.fetch(...a); } };
const PORTA = 8795, B = 'http://127.0.0.1:' + PORTA;
const post = (rota, corpo) => fetch(B + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo) });
const bate = estado => post('/api/batimento', { caixa:'aibox-t', local:'sala-t',
  estado, intervalo_s:1, detalhe: estado === 'tampada' ? 2 : 40, fps:8.6 });
const eventos = async () => (await (await fetch(B + '/api/eventos?limite=100&completo=1')).json());
const tipos = async () => (await eventos()).map(e => e.tipo_evento).reverse();
const saude = async () => (await (await fetch(B + '/api/saude')).json()).caixas;

const dir = mkdtempSync(join(tmpdir(), 'auditix-bat-'));
const srv = spawn('uv', ['run', 'servidor.py'], { env:{ ...process.env,
  PORTA:String(PORTA), SQLITE_ARQUIVO: join(dir, 'b.db'), DATABASE_URL:'',
  SEM_SINAL_S:'3', WEBHOOK_URL:'', QUEM_ESCREVE:'' }, stdio:'ignore' });
let subiu = false;
for(let i = 0; i < 60 && !subiu; i++){
  try{ await fetch(B + '/api/verificar'); subiu = true; }catch{ await dormir(500); }
}
if(!subiu){ srv.kill(); console.error('servidor de teste não subiu'); process.exit(1); }

try{
  /* ---- 1. batida normal não vira linha ---------------------------------- */
  await bate('ok'); await bate('ok');
  ok('batida "ok" NÃO grava nada na cadeia (não é fato, é pulso)',
     (await tipos()).length === 0);
  const s1 = (await saude())[0];
  ok('mas o estado da caixa aparece em /api/saude', s1 && s1.estado === 'ok' &&
     s1.local === 'sala-t', JSON.stringify(s1));

  /* ---- 2. tampada: uma linha por episódio -------------------------------- */
  await bate('tampada'); await bate('tampada'); await bate('tampada');
  ok('lente tampada vira UMA linha, mesmo com três batidas dizendo isso',
     JSON.stringify(await tipos()) === '["camera_tampada"]', JSON.stringify(await tipos()));
  await bate('ok');
  ok('e quando destampa, "sinal voltou" fecha o episódio',
     (await tipos()).at(-1) === 'sinal_voltou');

  /* ---- 3. o silêncio: a caixa morta não avisa, o servidor percebe -------- */
  const n0 = (await tipos()).length;
  await dormir(5500);
  const depois = await tipos();
  ok('caixa que parou de bater vira "sem_sinal" sozinha',
     depois.at(-1) === 'sem_sinal', JSON.stringify(depois.slice(n0)));
  ok('uma vez só, mesmo depois de vários passos da vigia',
     depois.length === n0 + 1);
  ok('e /api/saude diz SEM SINAL', (await saude())[0].estado === 'sem_sinal');

  /* ---- 4. o alarme e o "estou ciente" valem para o silêncio -------------- */
  const semSinal = (await eventos()).find(e => e.tipo_evento === 'sem_sinal');
  const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
  const nav = await chromium.launch({ executablePath: exe,
    args:['--no-sandbox','--no-proxy-server'] });
  const pg = await nav.newPage();
  await pg.goto(B + '/painel');
  await pg.waitForFunction(() => getComputedStyle(document.getElementById('alarme')).display !== 'none',
                           null, { timeout: 8000 }).catch(() => {});
  const tela = await pg.evaluate(() => ({
    alarme: getComputedStyle(document.getElementById('alarme')).display !== 'none',
    titulo: document.getElementById('alarme-tit').textContent,
    onde: document.getElementById('alarme-onde').textContent,
    selo: document.getElementById('s-caixas').textContent }));
  /* O mais ANTIGO vem primeiro: a lente tampada de antes ainda espera alguém
     ficar ciente — tampar a câmera é, por si, um fato de segurança. */
  ok('o painel toma a tela, começando pela lente tampada (a mais antiga)',
     tela.alarme && tela.titulo === 'câmera tampada ou no escuro', tela.titulo);
  await pg.click('#alarme-ciente');
  await pg.waitForFunction(() => document.getElementById('alarme-tit').textContent === 'caixa sem sinal',
                           null, { timeout: 5000 }).catch(() => {});
  const tit2 = await pg.evaluate(() => document.getElementById('alarme-tit').textContent);
  ok('e depois do ciente, "caixa sem sinal"', tit2 === 'caixa sem sinal', tit2);
  ok('e diz que o sistema não está vendo a sala', /NÃO está vendo/.test(tela.onde), tela.onde);
  ok('o selo da câmera fica à vista no topo', /sala-t · SEM SINAL/.test(tela.selo), tela.selo);
  await pg.click('#alarme-ciente');
  await pg.waitForTimeout(800);
  const ci = (await eventos()).find(e => e.id === semSinal.id);
  ok('"estou ciente" funciona para o silêncio também', ci.ciente_s != null);

  /* ---- 5. voltou ---------------------------------------------------------- */
  await bate('ok');
  ok('a primeira batida depois do silêncio grava "sinal voltou"',
     (await tipos()).at(-1) === 'sinal_voltou');
  await pg.waitForTimeout(2500);
  const selo2 = await pg.evaluate(() => document.getElementById('s-caixas').textContent);
  ok('e o selo volta para "vendo"', /sala-t · vendo/.test(selo2), selo2);
  await nav.close();

  /* ---- 6. parada de propósito não é alarme -------------------------------- */
  await bate('parada');
  await dormir(5000);
  const fim = await tipos();
  ok('Ctrl+C na caixa vira "caixa_parada", e NÃO "sem_sinal" depois',
     fim.at(-1) === 'caixa_parada', JSON.stringify(fim.slice(-2)));

  ok('estado inventado é recusado', (await bate('explodiu')).status === 422);

  /* ---- 7. o lado da caixa ------------------------------------------------- */
  const py = spawnSync('python3', ['testes/batimento_lado.py', B], { encoding:'utf-8' });
  process.stdout.write(py.stdout.split('\n').filter(l => !l.startsWith('RESULTADO'))
    .map(l => l.replace(/^  /, '  [caixa] ')).join('\n'));
  ok('o lado da caixa passa inteiro', py.status === 0, (py.stderr || '').slice(-300));
  const real = (await saude()).find(c => c.caixa === 'caixa-real');
  ok('e a caixa de verdade aparece no servidor, parada ao fechar',
     real && real.estado === 'parada', JSON.stringify(real));

  const v = await (await fetch(B + '/api/verificar')).json();
  ok('a cadeia continua fechando com as linhas de saúde no meio', v.integra, v.total + ' linhas');
}finally{
  srv.kill();
}
console.log(`\n${total - falhas}/${total} ok`);
process.exit(falhas ? 1 : 0);
