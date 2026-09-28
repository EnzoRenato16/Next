/* Gera o PDF do relatório a partir de relatorio.html, pelo Chromium.
 *
 *     node relatorio/gerar.mjs
 *
 * As fotos do laboratório (img/lab-*.jpg) e o PDF ficam FORA do Git: têm o
 * rosto dos integrantes. Para gerar de novo em outra máquina, ponha as fotos
 * em relatorio/img/ com esses nomes.
 */
import { chromium } from 'playwright';
import { existsSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const SAIDA = join(AQUI, 'Auditix-IA-Checkpoint-Grupo11-2ECR.pdf');
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);

/* Servido por HTTP, e nao aberto como arquivo: por file:// o Chromium recusa as
   fontes de vendor/fontes (outra pasta = outra origem) e cai para Liberation
   sem avisar nada. */
const RAIZ = join(AQUI, '..');
const TIPO = { '.html':'text/html; charset=utf-8', '.css':'text/css', '.woff2':'font/woff2',
               '.jpg':'image/jpeg', '.png':'image/png' };
const srv = createServer((req, res) => {
  const alvo = normalize(join(RAIZ, decodeURIComponent(req.url.split('?')[0])));
  if (!alvo.startsWith(RAIZ) || !existsSync(alvo)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TIPO[extname(alvo)] || 'application/octet-stream' });
  res.end(readFileSync(alvo));
});
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${srv.address().port}`;

const nav = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const pg = await nav.newPage();
await pg.goto(BASE + '/relatorio/relatorio.html', { waitUntil: 'networkidle' });
await pg.evaluate(() => document.fonts.ready);
const fontes = await pg.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded')
  .map(f => f.family.replace(/"/g, '') + ' ' + f.weight));
if (!fontes.some(f => f.startsWith('Public Sans'))) {
  console.error('as fontes do projeto nao carregaram:', fontes); process.exit(1); }
const faltando = await pg.evaluate(() =>
  [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.getAttribute('src')));
if (faltando.length) { console.error('imagens faltando:', faltando.join(', ')); process.exit(1); }
await pg.pdf({ path: SAIDA, preferCSSPageSize: true, printBackground: true });
await nav.close();
srv.close();
console.log('gerado:', SAIDA);
console.log('fontes:', [...new Set(fontes)].join(', '));
