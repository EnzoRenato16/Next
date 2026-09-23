/* A prova sem rosto — roda com:  node testes/esqueleto.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. A AIBOX não manda foto: o alerta dela chegava ao painel
 * sem evidência nenhuma. Agora ele leva os 17 pontos do corpo nos segundos da
 * queda, e o painel desenha o corpo descendo. Dá para ver o que aconteceu, e
 * não dá para ver de quem é o corpo.
 */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const post = (rota, corpo) => fetch(BASE + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo) });

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

/* Um corpo descendo: 10 quadros, quadril indo de 0,5 a 0,85. */
const corpo = y => {
  const kp = Array(5).fill([0.9, y - 0.3, 0.9]);
  for(let i = 0; i < 3; i++) kp.push([0.8, y - 0.2, 0.9], [0.98, y - 0.2, 0.9]);
  kp.push([0.84, y, 0.9], [0.94, y, 0.9]);
  kp.push([0.84, y + 0.15, 0.9], [0.94, y + 0.15, 0.9], [0.84, y + 0.3, 0.9], [0.94, y + 0.3, 0.9]);
  return kp.slice(0, 17);
};
const poses = Array.from({length:10}, (_, i) => corpo(0.5 + i * 0.035));

const com = await (await post('/api/evento', { aluno_id:'corpo-4', tipo_evento:'queda',
  localizacao:'teste-esqueleto', chave:'esq' + Date.now(), poses })).json();
const sem = await (await post('/api/evento', { aluno_id:'corpo-5', tipo_evento:'queda',
  localizacao:'teste-esqueleto' })).json();

/* ---- 1. o servidor devolve o que guardou ------------------------------- */
const r = await fetch(BASE + '/api/esqueleto/' + com.id);
const d = await r.json();
ok('o esqueleto guardado volta inteiro', r.ok && d.poses.length === 10,
   (d.poses || []).length + ' quadros');
ok('evento sem esqueleto responde 404, e não um vazio',
   (await fetch(BASE + '/api/esqueleto/' + sem.id)).status === 404);

/* ---- 2. o painel desenha ------------------------------------------------ */
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);
const nav = await chromium.launch({ executablePath: exe,
  args:['--no-sandbox','--no-proxy-server'] });
const pg = await nav.newPage();
const erros = [];
pg.on('pageerror', e => erros.push(e.message));
await pg.goto(BASE + '/painel', { timeout:20000 });
await pg.waitForSelector('#tabela table', { timeout:15000 });

ok('o evento que veio da caixa ganha o botão "corpo"',
   await pg.$('[data-corpo="' + com.id + '"]') !== null);
ok('e o que não tem esqueleto NÃO ganha — botão que abre vazio é pior que nenhum',
   await pg.$('[data-corpo="' + sem.id + '"]') === null);

await pg.click('[data-corpo="' + com.id + '"]');
await pg.waitForFunction(() => document.querySelectorAll('#visor-corpo line').length > 0,
                         { timeout:5000 });
/* Visível NA TELA, pelo estilo calculado. Conferir `.hidden` num <svg> não
   prova nada: a propriedade não existe em SVG, e o teste passava com o
   esqueleto escondido. */
ok('o visor abre com o corpo desenhado e VISÍVEL na tela',
   await pg.$eval('#visor-corpo', s => getComputedStyle(s).display !== 'none'
     && s.getBoundingClientRect().height > 100 && s.querySelectorAll('line').length > 0),
   await pg.$eval('#visor-corpo', s => getComputedStyle(s).display + ', ' +
     Math.round(s.getBoundingClientRect().height) + 'px'));
/* O QUE APARECE NA TELA, e não o atributo. A primeira versão marcava a imagem
   como hidden e ela continuava visível — um ícone de imagem quebrada em cima do
   esqueleto — porque o display escrito no elemento vencia o atributo. Este
   teste conferia o atributo e passava. */
ok('e a imagem da câmera NÃO aparece na tela — aqui não tem foto nenhuma',
   await pg.$eval('#visor-img', i => getComputedStyle(i).display === 'none'),
   await pg.$eval('#visor-img', i => getComputedStyle(i).display));

/* Espera a sequência chegar ao último quadro: é o corpo no chão, em vermelho. */
await pg.waitForFunction(() => [...document.querySelectorAll('#visor-corpo line')]
  .some(l => (l.getAttribute('stroke') || '').includes('rubi')), { timeout:5000 });
ok('a sequência toca até o último quadro, em vermelho', true);
const rastro = await pg.$$eval('#visor-corpo line[stroke-opacity]', ls => ls.length);
ok('com o rastro dos quadros anteriores, para a descida aparecer parada',
   rastro > 0, rastro + ' linhas de rastro');
ok('o texto diz o que é e o que não é',
   /nenhuma imagem da câmera/.test(await pg.textContent('#visor-nota')));

await pg.keyboard.press('Escape');
ok('Esc fecha o visor', await pg.$eval('#visor', v => v.hidden));

/* Abrir o corpo e depois fechar não pode deixar o esqueleto preso na tela da
   próxima foto. */
ok('fechado, o palco do esqueleto some de verdade',
   await pg.$eval('#visor-corpo', s => getComputedStyle(s).display === 'none'));
ok('nenhum erro de JavaScript', erros.length === 0, erros.join(' | '));
await nav.close();

/* ---- 3. o lado da caixa (Python) ---------------------------------------- */
console.log('\n  -- o buffer de poses da caixa (Python) --');
const py = spawnSync('python3', ['testes/esqueleto_lado.py'], { encoding:'utf-8' });
process.stdout.write(py.stdout || '');
if(py.stderr) process.stderr.write(py.stderr);
ok('a prova sem rosto passou na caixa', py.status === 0);

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
