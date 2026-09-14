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
  /* RUÍDO por pixel, não tabuleiro.

     Duas versões anteriores deste teste usaram tabuleiro e cada uma falhou de
     um jeito: a de 8px tinha o tamanho do bloco do mosaico e media a si mesma;
     a de 2px só tem DUAS cores, então "sobraram poucas cores" seria verdade
     até para um véu translúcido por cima. Ruído tem milhares de cores e
     detalhe em cada pixel — se sobrar estrutura, aparece. Semente fixa para o
     teste não variar de rodada para rodada. */
  const desenhar = () => {
    const c = document.createElement('canvas');
    c.width = 200; c.height = 200;
    const x = c.getContext('2d');
    const img = x.createImageData(200, 200);
    let s = 12345;
    for(let i = 0; i < img.data.length; i += 4){
      /* Os bits BAIXOS de um LCG mal se mexem — a primeira versão gerou 11
         cores em 1.600 pixels e o "ruído" era quase liso. Bits altos. */
      s = (Math.imul(s, 1103515245) + 12345) & 0x7fffffff;
      img.data[i]   = (s >>> 23) & 255;
      img.data[i+1] = (s >>> 15) & 255;
      img.data[i+2] = (s >>> 7)  & 255;
      img.data[i+3] = 255;
    }
    x.putImageData(img, 0, 0);
    return c;
  };
  const ler = c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data;

  /* "Mudou muito" NÃO basta, e essa lição custou uma imagem com o rosto
     visível: um véu cinza translúcido sobre o tabuleiro muda cada pixel em
     mais de 80 e mesmo assim deixa enxergar tudo que está embaixo. Foi
     exatamente o que aconteceu, e este teste aprovou.

     O que um mosaico de verdade tem, e um véu não:
       - POUCAS cores na região (uma por bloco, contra milhares);
       - alfa 255 em todo pixel (véu é justamente alfa parcial).
     As duas juntas não têm como passar com o original aparecendo. */
  const cores = (c, x0, y0, lado) => {
    const d = c.getContext('2d').getImageData(x0, y0, lado, lado).data;
    const s = new Set();
    for(let i = 0; i < d.length; i += 4) s.add(d[i] + ',' + d[i+1] + ',' + d[i+2]);
    return s.size;
  };
  const opaco = (c, x0, y0, lado) => {
    const d = c.getContext('2d').getImageData(x0, y0, lado, lado).data;
    for(let i = 3; i < d.length; i += 4) if(d[i] !== 255) return false;
    return true;
  };
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
               fora:   mudou(antes1, d1, c, 5, 5, 40),
               cores:  cores(c, 75, 75, 50),
               coresFora: cores(c, 5, 5, 40),
               opaco:  opaco(c, 75, 75, 50) };

  /* 2. o detector acha alguém que a pose não viu — gente ao fundo, sem trilha */
  const c2 = desenhar();
  c2.cabecas = [];
  const antes2 = ler(c2);
  trocar(async () => [{ box:{ x:30, y:30, width:50, height:50 } }]);
  await borrarRostos(c2);
  const d2 = ler(c2);
  const r2 = { dentro: mudou(antes2, d2, c2, 35, 35, 40),
               fora:   mudou(antes2, d2, c2, 150, 150, 40),
               cores:  cores(c2, 35, 35, 40) };

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
  const r4 = { a: cores(c4, 15, 15, 40), b: cores(c4, 135, 135, 40),
               meio: mudou(antes4, d4, c4, 85, 85, 30) };

  /* 5. a caixa da cabeça não pode engolir o quadro. Aconteceu: com a pessoa
        perto da câmera o mosaico cobria um terço da imagem, e o que o mosaico
        cobre ninguém confere. */
  const lm = [];
  for(let i = 0; i < 33; i++) lm.push({ x:0.5, y:0.5, visibility:0 });
  // cabeça de orelha a orelha: 10% da largura, centrada em 0.5 / 0.30
  lm[0] = { x:0.50, y:0.30, visibility:1 };          // nariz
  lm[7] = { x:0.45, y:0.29, visibility:1 };          // orelha esquerda
  lm[8] = { x:0.55, y:0.29, visibility:1 };          // orelha direita
  lm[11] = { x:0.38, y:0.45, visibility:1 };         // ombro
  lm[12] = { x:0.62, y:0.45, visibility:1 };
  const cx5 = caixaDaCabeca(lm, 1000, 1000);
  const r5 = { larguraCabeca: 100, caixa: cx5.w, alturaCaixa: cx5.h,
               cobre: (cx5.w * cx5.h) / (1000 * 1000) };

  trocar(original);
  return { r1, r2, r3, r4, r5 };
});

if(erros.length){ console.error('erros na página:', erros); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };
const n = v => v.toFixed(0);

dizer(r.r1.url === 'data:image/jpeg;base64', 'sai um JPEG                              (' + r.r1.url + ')');
dizer(r.r1.cores <= 40 && r.r1.coresFora > 500,
      'com o detector CAÍDO, a pose apaga        (' + n(r.r1.cores) + ' cores, contra ' +
      n(r.r1.coresFora) + ' fora)');
dizer(r.r1.opaco,
      'o mosaico é OPACO, não um véu por cima    (alfa 255 em tudo)');
dizer(r.r1.fora < 1,
      'o resto do quadro fica intacto            (mudou ' + n(r.r1.fora) + ')');
dizer(r.r2.cores <= 40 && r.r2.fora < 1,
      'quem só o detector vê também some         (' + n(r.r2.cores) + ' cores dentro, ' +
      n(r.r2.fora) + ' de mudança fora)');
dizer(r.r3 === null,
      'ninguém identificado, imagem NÃO sai      (' + r.r3 + ')');
dizer(r.r4.a <= 40 && r.r4.b <= 40 && r.r4.meio < 1,
      'duas pessoas, as duas apagadas            (' + n(r.r4.a) + ' e ' + n(r.r4.b) +
      ' cores, meio intacto ' + n(r.r4.meio) + ')');

dizer(r.r5.caixa < 190,
      'a caixa não engole o quadro               (cabeça 100px -> caixa ' +
      n(r.r5.caixa) + 'x' + n(r.r5.alturaCaixa) + ', ' +
      (r.r5.cobre * 100).toFixed(1) + '% do quadro)');

console.log(bem ? '\nO DESFOQUE DE ROSTO PASSOU' : '\nFALHOU');
await nav.close();
process.exit(bem ? 0 : 1);
