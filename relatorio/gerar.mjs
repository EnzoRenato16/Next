/* Gera o PDF do relatório a partir de relatorio.html, pelo Chromium.
 *
 *     node relatorio/gerar.mjs
 *
 * Duas passadas: a primeira gera o PDF só para descobrir em que página cada
 * seção caiu (lido com o pypdf), e a segunda escreve esses números no sumário.
 * O Chromium não tem target-counter(), que faria isso sozinho.
 *
 * As fotos do laboratório (img/lab-*.jpg) e o PDF ficam FORA do Git: têm o
 * rosto dos integrantes. Para gerar de novo em outra máquina, ponha as fotos
 * em relatorio/img/ com esses nomes.
 */
import { chromium } from 'playwright';
import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const SAIDA = join(AQUI, 'Auditix-IA-Checkpoint-Grupo11-2ECR.pdf');
const exe = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(existsSync);

/* Servido por HTTP, e não aberto como arquivo, para as imagens carregarem do
   mesmo jeito em qualquer máquina. */
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
const faltando = await pg.evaluate(() =>
  [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.getAttribute('src')));
if (faltando.length) { console.error('imagens faltando:', faltando.join(', ')); process.exit(1); }

/* O sumário é montado a partir dos títulos, com a página ainda em branco. */
const secoes = await pg.evaluate(() => {
  const ol = document.getElementById('sumario');
  const hs = [...document.querySelectorAll('h2[id], h3[id]')];
  for (const h of hs) {
    const li = document.createElement('li');
    if (h.tagName === 'H3') li.className = 'sub';
    li.innerHTML = '<span></span><span class="pontos"></span><span class="pg" data-alvo="' + h.id + '"></span>';
    li.firstChild.textContent = h.textContent;
    ol.appendChild(li);
  }
  return hs.map(h => ({ id: h.id, texto: h.textContent.replace(/\s+/g, ' ').trim() }));
});

await pg.pdf({ path: SAIDA, preferCSSPageSize: true, printBackground: true });

/* Em que página caiu cada título. Pula as duas primeiras (capa e sumário),
   onde o mesmo texto aparece na lista. */
const py = spawnSync('python3', ['-c', `
import sys, json
from pypdf import PdfReader
paginas = [" ".join((p.extract_text() or "").split()) for p in PdfReader(sys.argv[1]).pages]
saida = {}
for s in json.loads(sys.argv[2]):
    for i in range(2, len(paginas)):
        if s["texto"] in paginas[i]:
            saida[s["id"]] = i + 1
            break
print(json.dumps(saida))
`, SAIDA, JSON.stringify(secoes)], { encoding: 'utf-8' });
if (py.status !== 0) { console.error('não consegui ler as páginas (precisa do pypdf):', py.stderr); process.exit(1); }
const paginas = JSON.parse(py.stdout);
const semPagina = secoes.filter(s => !paginas[s.id]).map(s => s.texto);
if (semPagina.length) { console.error('títulos não encontrados no PDF:', semPagina); process.exit(1); }

await pg.evaluate(p => {
  for (const el of document.querySelectorAll('.sumario .pg')) el.textContent = p[el.dataset.alvo];
}, paginas);
await pg.pdf({ path: SAIDA, preferCSSPageSize: true, printBackground: true });
await nav.close();
srv.close();
console.log('gerado:', SAIDA);
console.log('sumário:', secoes.map(s => s.texto.split(' ')[0] + '=' + paginas[s.id]).join(' '));
