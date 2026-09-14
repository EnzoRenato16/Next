/* O mapa de calor: janela, suavização e escala.
 *
 * A escala é a parte que engana sem avisar. Uma sala real é 95% de gente
 * passando e 5% de gente parada; escala errada mostra a sala inteira quente
 * (e não responde nada) ou a sala inteira fria com um pixel aceso. Aqui se
 * confere que o piso de trânsito fica embaixo e a zona parada sobe.
 *
 *     node testes/mapa.mjs
 */
import { spawn } from 'node:child_process';
import { unlinkSync } from 'node:fs';

const PORTA = 8793;
const BASE = `http://127.0.0.1:${PORTA}`;
const BANCO = '/tmp/auditix-teste-mapa.db';
try{ unlinkSync(BANCO); }catch{}

const srv = spawn('uv', ['run', 'servidor.py'], { env: { ...process.env,
  PORTA: String(PORTA), DATABASE_URL: '', WEBHOOK_URL: '',
  SQLITE_ARQUIVO: BANCO }, stdio:'ignore' });

const dormir = ms => new Promise(r => setTimeout(r, ms));
const pegar = async u => (await fetch(BASE + u)).json();
const mandar = celulas => fetch(BASE + '/api/calor', { method:'POST',
  headers:{ 'Content-Type':'application/json' },
  body: JSON.stringify({ camera:'sala-teste', celulas }) });

let pronto = false;
for(let i = 0; i < 60 && !pronto; i++){
  try{ await fetch(BASE + '/'); pronto = true; }catch{ await dormir(500); }
}
const encerrar = c => { srv.kill(); process.exit(c); };
if(!pronto){ console.error('FALHOU: o servidor de teste não subiu'); encerrar(1); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };

/* Uma sala de 20x15: trânsito parelho em tudo, e UMA zona onde alguém ficou. */
const celulas = [];
for(let y=0; y<15; y++) for(let x=0; x<20; x++) celulas.push({x, y, n:3});
for(let y=10; y<13; y++) for(let x=3; x<6; x++) celulas.push({x, y, n:90});
await mandar(celulas);

const d = await pegar('/api/mapa?camera=sala-teste');
const em = (x,y) => d.celulas.find(c => c.x === x && c.y === y);

dizer(em(4,11).n === 93, 'a contagem crua chega inteira            (' + em(4,11).n + ')');
dizer(em(4,11).z > em(0,0).z * 5,
      'a zona parada se separa do trânsito      (' + em(4,11).z + ' vs ' + em(0,0).z + ')');
/* A borda não pode esfriar por não ter vizinho: seria um corredor gelado em
   volta da sala que não existe no mundo. */
dizer(Math.abs(em(0,0).z - em(10,7).z) < 0.01,
      'a borda não esfria por falta de vizinho  (' + em(0,0).z + ')');

const cortes = d.cortes;
dizer(cortes.length === 4 && cortes.every((c,i) => i === 0 || c > cortes[i-1]),
      'os quatro cortes sobem                   (' + cortes.join(', ') + ')');
const tom = z => cortes.reduce((a,c) => a + (z > c ? 1 : 0), 0);
dizer(tom(em(4,11).z) === 4, 'a zona parada recebe o tom mais quente');
dizer(tom(em(15,2).z) === 0, 'o trânsito parelho fica no tom mais frio');
/* Se o piso inteiro subisse de tom, o mapa estaria dizendo que a sala toda é
   ponto de parada — que é o defeito que a escala por quantil tinha. */
const quentes = d.celulas.filter(c => tom(c.z) >= 3).length;
dizer(quentes < d.celulas.length * 0.15,
      'menos de 15% da sala fica quente         (' + quentes + ' de ' + d.celulas.length + ')');

/* Janela: o que foi gravado hoje aparece em 1 dia; nada some da base inteira. */
const hoje = await pegar('/api/mapa?camera=sala-teste&dias=1');
dizer(hoje.total === d.total, 'a janela de 1 dia pega o que é de hoje');
dizer(d.pico === 93, 'o pico é a célula mais alta              (' + d.pico + ')');

console.log(bem ? '\nO MAPA DE CALOR PASSOU' : '\nFALHOU');
encerrar(bem ? 0 : 1);
