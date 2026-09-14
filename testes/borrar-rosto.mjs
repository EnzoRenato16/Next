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
  /* Tabuleiro FINO, de 2px: detalhe menor que o bloco do mosaico. A primeira
     versão deste teste usava quadrados de 8px — do tamanho do bloco — e media
     a si mesma: o mosaico copiava o tabuleiro e o teste dava FALHA num código
     certo. */
  const desenhar = () => {
    const c = document.createElement('canvas');
    c.width = 200; c.height = 200;
    const x = c.getContext('2d');
    for(let j = 0; j < 200; j += 2) for(let i = 0; i < 200; i += 2){
      x.fillStyle = ((i + j) / 2) % 2 ? '#fff' : '#000';
      x.fillRect(i, j, 2, 2);
    }
    return c;
  };
  const ler = c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data;

  /* A pergunta certa não é "quanta textura sobrou" — num mosaico o contraste
     ENTRE blocos é alto e isso não é vazamento. É "o que está aqui ainda se
     parece com o que estava antes": diferença média por pixel contra o
     original. Perto de zero = intacto. Alto = a informação foi embora. */
  const mudou = (antes, depois, c, x0, y0, lado) => {
    let s = 0, n = 0;
    for(let j = y0; j < y0 + lado; j++) for(let i = x0; i < x0 + lado; i++){
      const k = (j * c.width + i) * 4;
      s += Math.abs(antes[k] - depois[k]); n++;
    }
    return s / n;
  };

  /* `faceapi.detectAllFaces` é propriedade não configurável: não dá para
     substituir. A página expõe `acharRostos` justamente para isto. */
  const original = acharRostos;
  const trocar = fn => { acharRostos = fn; };

  /* 1. a cabeça vem da POSE e o detector de rosto está QUEBRADO.
        Era exatamente aqui que a versão anterior entregava rosto nítido. */
  const c = desenhar();
  c.cabecas = [{ x:70, y:70, w:60, h:60 }];
  const antes1 = ler(c);
  trocar(async () => { throw new Error('detector fora do ar'); });
  const url = await borrarRostos(c);
  const d1 = ler(c);
  const r1 = { url: String(url).slice(0, 22),
               dentro: mudou(antes1, d1, c, 75, 75, 50),
               fora:   mudou(antes1, d1, c, 5, 5, 40) };

  /* 2. o detector acha alguém que a pose não viu — gente ao fundo, sem trilha */
  const c2 = desenhar();
  c2.cabecas = [];
  const antes2 = ler(c2);
  trocar(async () => [{ box:{ x:30, y:30, width:50, height:50 } }]);
  await borrarRostos(c2);
  const d2 = ler(c2);
  const r2 = { dentro: mudou(antes2, d2, c2, 35, 35, 40),
               fora:   mudou(antes2, d2, c2, 150, 150, 40) };

  /* 3. ninguém identificado por nenhum dos dois: NADA sai. */
  const c3 = desenhar();
  c3.cabecas = [];
  trocar(async () => []);
  const r3 = await borrarRostos(c3);

  /* 4. duas pessoas no quadro: as duas cabeças somem, não só a primeira. */
  const c4 = desenhar();
  c4.cabecas = [{ x:10, y:10, w:50, h:50 }, { x:130, y:130, w:50, h:50 }];
  const antes4 = ler(c4);
  trocar(async () => []);
  await borrarRostos(c4);
  const d4 = ler(c4);
  const r4 = { a: mudou(antes4, d4, c4, 15, 15, 40),
               b: mudou(antes4, d4, c4, 135, 135, 40),
               meio: mudou(antes4, d4, c4, 85, 85, 30) };

  trocar(original);
  return { r1, r2, r3, r4 };
});

if(erros.length){ console.error('erros na página:', erros); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };
const n = v => v.toFixed(0);

dizer(r.r1.url === 'data:image/jpeg;base64', 'sai um JPEG                              (' + r.r1.url + ')');
dizer(r.r1.dentro > 55,
      'com o detector CAÍDO, a pose apaga        (mudou ' + n(r.r1.dentro) + ' por pixel)');
dizer(r.r1.fora < 1,
      'o resto do quadro fica intacto            (mudou ' + n(r.r1.fora) + ')');
dizer(r.r2.dentro > 55 && r.r2.fora < 1,
      'quem só o detector vê também some         (' + n(r.r2.dentro) + ' dentro, ' + n(r.r2.fora) + ' fora)');
dizer(r.r3 === null,
      'ninguém identificado, imagem NÃO sai      (' + r.r3 + ')');
dizer(r.r4.a > 55 && r.r4.b > 55 && r.r4.meio < 1,
      'duas pessoas, as duas apagadas            (' + n(r.r4.a) + ' e ' + n(r.r4.b) +
      ', meio ' + n(r.r4.meio) + ')');

console.log(bem ? '\nO DESFOQUE DE ROSTO PASSOU' : '\nFALHOU');
await nav.close();
process.exit(bem ? 0 : 1);
