/* O cadastro pela câmera da caixa — roda com:  node testes/balcao.mjs
 *
 * Sobe o PRÓPRIO servidor (porta 8797, banco temporário) e uma caixa de
 * mentira (porta 8798: o balcão de verdade, com câmera e motor falsos).
 *
 * POR QUE ISTO EXISTE. No laboratório a tela /cadastro dizia "a câmera não
 * abriu": ela usa a webcam do PC, e o PC do laboratório não tem. As câmeras de
 * lá são IP (a .108 no alto vigia a sala, a .109 na altura do rosto), e
 * navegador não lê RTSP. Além disso o motor do navegador mede o rosto num
 * formato que a caixa não lê. Agora a tela pede e a caixa faz: ver
 * aibox/balcao.py. Este arquivo cobra o caminho inteiro, do clique até o
 * cadastro gravado como "sface", que é o motor que reconhece na sala.
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
const PORTA = 8797, B = 'http://127.0.0.1:' + PORTA;
const CAIXA = 8798;

/* ---- 1. o balcão por dentro, sem tela ----------------------------------- */
console.log('== o balcão, por dentro ==');
const lado = spawnSync('python3', ['testes/balcao_lado.py'], { encoding:'utf-8' });
process.stdout.write(lado.stdout.split('\n').filter(l => !l.startsWith('RESULTADO'))
  .map(l => l.replace(/^  /, '  [caixa] ')).join('\n'));
ok('o lado da caixa passa inteiro', lado.status === 0, (lado.stderr || '').slice(-300));

/* ---- 2. a tela, de ponta a ponta ---------------------------------------- */
console.log('\n== a tela /cadastro com a câmera da caixa ==');
const dir = mkdtempSync(join(tmpdir(), 'auditix-balcao-'));
const srv = spawn('uv', ['run', 'servidor.py'], { env:{ ...process.env,
  PORTA:String(PORTA), SQLITE_ARQUIVO: join(dir, 'b.db'), DATABASE_URL:'',
  WEBHOOK_URL:'', QUEM_ESCREVE:'' }, stdio:'ignore' });
let caixa = null, nav = null;
try{
  let subiu = false;
  for(let i = 0; i < 60 && !subiu; i++){
    try{ await fetch(B + '/api/verificar'); subiu = true; }catch{ await dormir(500); }
  }
  if(!subiu) throw new Error('servidor de teste não subiu');

  caixa = spawn('python3', ['testes/balcao_lado.py', '--servir', String(CAIXA), B],
                { stdio:['ignore', 'pipe', 'inherit'] });
  await new Promise((res, rej) => {
    caixa.stdout.on('data', d => { if(String(d).includes('pronto')) res(); });
    setTimeout(() => rej(new Error('a caixa falsa não subiu')), 10000);
  });

  /* A caixa avisa no batimento a porta do balcão; o IP é o de quem bateu. */
  await fetch(B + '/api/batimento', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ caixa:'aibox-t', local:'sala-t', estado:'ok', intervalo_s:5,
                           balcao: CAIXA }) });
  const saude = (await (await fetch(B + '/api/saude')).json()).caixas[0];
  ok('o servidor diz onde está o balcão, com o IP de quem bateu',
     saude && saude.balcao === 'http://127.0.0.1:' + CAIXA, saude && saude.balcao);

  const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
  nav = await chromium.launch(exe ? { executablePath: exe } : {});
  const pg = await nav.newPage();
  const errosJs = [];
  pg.on('pageerror', e => errosJs.push(e.message));
  /* SEM ?caixa= na barra: a tela tem de achar o balcão sozinha, pelo servidor. */
  await pg.goto(B + '/cadastro');
  await pg.waitForFunction(() => !document.getElementById('fonte').hidden, null, { timeout: 8000 })
    .catch(() => {});
  const visivel = sel => pg.$eval(sel, el => getComputedStyle(el).display !== 'none');
  ok('a tela achou a caixa sozinha e mostra a escolha de câmera', await visivel('#fonte'));
  ok('e a câmera da caixa já vem escolhida',
     await pg.$eval('#fonteSel', s => s.value) === 'caixa');
  ok('a nota diz a verdade sobre este modo (sem prova de vida)',
     await visivel('#notaCaixa') && !(await visivel('#notaVida')));

  await pg.click('#ligar');
  await pg.waitForFunction(() => {
    const i = document.getElementById('camip');
    return i.complete && i.naturalWidth > 0;
  }, null, { timeout: 8000 }).catch(() => {});
  ok('ligar a câmera mostra a imagem da caixa (MJPEG)',
     await pg.$eval('#camip', i => i.naturalWidth) > 0);
  ok('e esconde o vídeo da webcam', !(await visivel('#cam')));
  ok('o botão de cadastrar espera o nome',
     await pg.$eval('#salvar', b => b.disabled));

  await pg.fill('#nome', 'Teste Tela Caixa');
  await pg.waitForFunction(() => !document.getElementById('salvar').disabled, null,
    { timeout: 5000 }).catch(() => {});
  ok('com nome, o botão libera', !(await pg.$eval('#salvar', b => b.disabled)));
  await pg.click('#salvar');
  await pg.waitForFunction(() => /cadastrado/.test(document.getElementById('dica').textContent),
    null, { timeout: 10000 }).catch(() => {});
  const dica = await pg.$eval('#dica', d => d.textContent);
  ok('a caixa colhe e grava, e a tela diz', /Teste Tela Caixa cadastrado/.test(dica), dica);

  const lista = (await (await fetch(B + '/api/cadastros')).json()).cadastros;
  const ficha = lista.find(c => c.nome === 'Teste Tela Caixa');
  ok('o cadastro foi gravado como sface, o motor que reconhece na sala',
     ficha && ficha.tipo === 'sface' && ficha.amostras === 6, JSON.stringify(ficha));
  await pg.waitForFunction(() => /Teste Tela Caixa/.test(document.getElementById('lista').textContent),
    null, { timeout: 5000 }).catch(() => {});
  const linha = await pg.$eval('#lista', l => l.textContent);
  ok('e a lista da tela mostra a pessoa, dizendo que vale na caixa',
     /Teste Tela Caixa/.test(linha) && /caixa/.test(linha));
  ok('o campo de nome limpa para o próximo', await pg.$eval('#nome', i => i.value) === '');

  /* Trocar para a webcam desliga a imagem da caixa: tirar o src fecha o MJPEG,
     e é isso que deixa a caixa desligar a câmera sozinha. */
  await pg.selectOption('#fonteSel', 'pc');
  ok('trocar para a webcam fecha a imagem da caixa',
     await pg.$eval('#camip', i => !i.getAttribute('src')));
  ok('e volta a explicar a prova de vida', await visivel('#notaVida'));

  ok('nenhum erro de JavaScript', errosJs.length === 0, errosJs.join(' | '));
}catch(e){
  ok('o teste rodou até o fim', false, e.message);
}finally{
  if(nav) await nav.close();
  if(caixa) caixa.kill();
  /* Fecha o episódio da caixa de mentira, para o servidor não ficar esperando
     batida; o servidor é deste teste e morre junto, mas sai limpo. */
  try{
    await fetch(B + '/api/batimento', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ caixa:'aibox-t', local:'sala-t', estado:'parada' }) });
  }catch{}
  srv.kill();
}
console.log(`\n${total - falhas}/${total} ok`);
process.exit(falhas ? 1 : 0);
