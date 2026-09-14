/* O rosto sai borrado do recorte do alerta.
 *
 * A promessa que a tela faz é forte: "o recorte vai sem rosto". Se ela falhar
 * em silêncio, o sistema passa a distribuir rosto de menor de idade dizendo
 * que não distribui — que é pior do que nunca ter prometido. Então o que se
 * testa aqui é a promessa, não o detector.
 *
 *     uv run servidor.py        (noutra janela)
 *     node testes/borrar-rosto.mjs
 */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';

const CAMINHOS = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'];
const executablePath = CAMINHOS.find(existsSync);

const nav = await chromium.launch({ executablePath,
  args:['--no-sandbox','--no-proxy-server',
        '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'] });
const ctx = await nav.newContext({ permissions:['camera'] });
const p = await ctx.newPage();
const erros = [];
p.on('pageerror', e => erros.push(e.message));

const falhar = async m => { console.error('FALHOU: ' + m); await nav.close(); process.exit(1); };

try{ await p.goto('http://127.0.0.1:8000/', { timeout:20000 }); }
catch{ await falhar('o servidor não está no ar (uv run servidor.py)'); }
await p.click('#ligar');
try{
  await p.waitForFunction(() => typeof borrarRostos === 'function', { timeout:190000 });
}catch{ await falhar('a sala não carregou'); }

const r = await p.evaluate(async () => {
  /* Tabuleiro de alto contraste: borrar é justamente perder contraste, então
     a medida do teste é a variação entre pixels vizinhos. */
  const desenhar = () => {
    const c = document.createElement('canvas');
    c.width = 200; c.height = 200;
    const x = c.getContext('2d');
    for(let j = 0; j < 200; j += 8) for(let i = 0; i < 200; i += 8){
      x.fillStyle = ((i + j) / 8) % 2 ? '#fff' : '#000';
      x.fillRect(i, j, 8, 8);
    }
    return c;
  };
  const variacao = (c, x0, y0, lado) => {
    const d = c.getContext('2d').getImageData(x0, y0, lado, lado).data;
    let s = 0, s2 = 0, n = 0;
    for(let i = 0; i < d.length; i += 4){ s += d[i]; s2 += d[i]*d[i]; n++; }
    return Math.sqrt(s2/n - (s/n)*(s/n));
  };

  /* `faceapi.detectAllFaces` é propriedade não configurável: não dá para
     substituir. A página expõe `acharRostos` justamente para isto. */
  const original = acharRostos;
  const trocar = fn => { acharRostos = fn; };

  /* 1. com um rosto detectado na região 70..130 */
  const c = desenhar();
  const antesDentro = variacao(c, 80, 80, 40);
  const antesFora   = variacao(c, 5, 5, 30);
  trocar(async () => [{ box:{ x:70, y:70, width:60, height:60 } }]);
  const url = await borrarRostos(c);
  const r1 = { url: String(url).slice(0, 22),
               antesDentro, depoisDentro: variacao(c, 80, 80, 40),
               antesFora, depoisFora: variacao(c, 5, 5, 30) };

  /* 2. sem rosto nenhum: a imagem sai intacta, não sai vazia */
  const c2 = desenhar();
  trocar(async () => []);
  const url2 = await borrarRostos(c2);
  const r2 = { ok: typeof url2 === 'string' && url2.startsWith('data:image/jpeg'),
               variacao: variacao(c2, 80, 80, 40) };

  /* 3. detector quebrado: NADA sai. Falhar fechado é o ponto todo. */
  trocar(async () => { throw new Error('detector fora do ar'); });
  const r3 = await borrarRostos(desenhar());

  trocar(original);
  return { r1, r2, r3 };
});

if(erros.length){ console.error('erros na página:', erros); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };

dizer(r.r1.url === 'data:image/jpeg;base64', 'sai um JPEG                              (' + r.r1.url + ')');
dizer(r.r1.depoisDentro < r.r1.antesDentro * 0.35,
      'o rosto perde o contraste                (' +
      r.r1.antesDentro.toFixed(0) + ' -> ' + r.r1.depoisDentro.toFixed(0) + ')');
dizer(Math.abs(r.r1.depoisFora - r.r1.antesFora) < 1,
      'o resto do quadro fica intacto           (' + r.r1.depoisFora.toFixed(0) + ')');
dizer(r.r2.ok && r.r2.variacao > 100,
      'sem rosto detectado, a imagem vai inteira (' + r.r2.variacao.toFixed(0) + ')');
dizer(r.r3 === null,
      'detector quebrado NÃO manda a imagem     (' + r.r3 + ')');

console.log(bem ? '\nO DESFOQUE DE ROSTO PASSOU' : '\nFALHOU');
await nav.close();
process.exit(bem ? 0 : 1);
