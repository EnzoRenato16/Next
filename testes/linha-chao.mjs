/* A linha do chão vale mesmo com o corpo cortado no quadro.
 *
 * Existe por causa de um bug que custou uma noite: a análise inteira desiste
 * quando o quadril não aparece — e cabeça no chão é justamente o enquadramento
 * em que o quadril some. A pessoa estava caída, com a cabeça abaixo da linha, e
 * a tela dizia "sem análise de queda: corpo cortado no quadro".
 *
 * A linha olha uma coisa só: onde está a cabeça no quadro. Não pode depender de
 * mais nada.
 *
 *     uv run servidor.py        (noutra janela)
 *     node testes/linha-chao.mjs
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
  await p.waitForFunction(() => document.getElementById('cam').videoWidth > 0, { timeout:190000 });
}catch{ await falhar('a sala não abriu'); }

const r = await p.evaluate(async () => {
  rodando = false;                       // congela o laço durante o teste
  linhaChao = 0.60;

  /* Um esqueleto com a CABEÇA no chão e o QUADRIL fora do quadro — o caso real.
     Os 33 pontos existem sempre; o que muda é a visibilidade. */
  const corpo = (cabecaY, quadrilVisivel) => {
    const lm = [];
    for(let i = 0; i < 33; i++) lm.push({ x:0.5, y:0.5, visibility:0 });
    lm[P.NARIZ]   = { x:0.5, y:cabecaY, visibility:0.9 };
    lm[P.OMBRO_E] = { x:0.45, y:cabecaY + 0.05, visibility:0.9 };
    lm[P.OMBRO_D] = { x:0.55, y:cabecaY + 0.05, visibility:0.9 };
    const v = quadrilVisivel ? 0.9 : 0.05;
    lm[P.QUADRIL_E] = { x:0.46, y:cabecaY + 0.2, visibility:v };
    lm[P.QUADRIL_D] = { x:0.54, y:cabecaY + 0.2, visibility:v };
    lm[P.PULSO_E] = { x:0.4, y:cabecaY + 0.1, visibility:0.9 };
    lm[P.PULSO_D] = { x:0.6, y:cabecaY + 0.1, visibility:0.9 };
    return lm;
  };

  const rodar = async (cabecaY, quadrilVisivel, ms) => {
    anomalias = [];
    const t = { id:1, firme:true, nasceu:performance.now() - 60000, nome:null,
                hist:[], lento:[], box:{ x:0, y:0, w:10, h:10 }, confirmado:-Infinity };
    const fim = performance.now() + ms;
    while(performance.now() < fim){
      analisar(t, corpo(cabecaY, quadrilVisivel), performance.now());
      await new Promise(r => setTimeout(r, 30));
    }
    return anomalias.filter(a => a.tipo === 'queda').length;
  };

  return {
    cortadoNoChao: await rodar(0.85, false, 1200),   // cabeça abaixo, sem quadril
    cortadoEmPe:   await rodar(0.20, false, 1200),   // cabeça acima, sem quadril
    inteiroNoChao: await rodar(0.85, true, 1200),    // cabeça abaixo, com quadril
  };
});

const dizer = (ok, msg) => { console.log((ok ? '  ok    ' : '  FALHA ') + msg); return ok; };
let bem = true;
bem &= dizer(r.cortadoNoChao > 0,
  'cabeça abaixo da linha COM O CORPO CORTADO acusa queda  (' + r.cortadoNoChao + ')');
bem &= dizer(r.cortadoEmPe === 0,
  'cabeça acima da linha, corpo cortado, não acusa nada    (' + r.cortadoEmPe + ')');
bem &= dizer(r.inteiroNoChao > 0,
  'cabeça abaixo da linha com o corpo inteiro acusa queda  (' + r.inteiroNoChao + ')');
if(erros.length){ console.error('\nERROS NA PÁGINA:\n' + erros.join('\n')); bem = false; }

await nav.close();
console.log(bem ? '\nA LINHA DO CHÃO PASSOU' : '\nFALHOU');
process.exit(bem ? 0 : 1);
