/* Reconhecimento facial na caixa — roda com:  node testes/rosto.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * DOIS MOTORES DE ROSTO, E ELES NÃO SE FALAM. O navegador mede com o
 * face-api.js e compara por distância euclidiana (menor = mais parecido); a
 * caixa mede com o SFace e compara por cosseno (MAIOR = mais parecido).
 *
 * Os dois devolvem 128 números, e é exatamente por isso que misturar é
 * perigoso: nada estoura, a comparação roda, e o resultado é ruído. Um sistema
 * que reconhece a pessoa errada é pior que um que não reconhece ninguém.
 *
 * Este arquivo cobra a separação, e cobra o sinal — inverter "maior é melhor"
 * em silêncio daria exatamente o pior caso acima.
 */
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
const v = () => Array.from({length:128}, () => Math.random() - 0.5);

try{ await fetch(BASE + '/api/verificar'); }
catch{ console.error('o servidor não está no ar em ' + BASE); process.exit(1); }

const NOME = 'Caixa ' + Date.now();
const CARA = v();

/* ---- 1. o cadastro da caixa é aceito e marcado ------------------------- */
const r1 = await (await post('/api/cadastro',
  { nome: NOME, tipo:'sface', descritores:[CARA] })).json();
ok('um cadastro do tipo sface é aceito', r1.tipo === 'sface', JSON.stringify(r1));

/* ---- 2. reconhece por cosseno ----------------------------------------- */
const q1 = await (await post('/api/reconhecer',
  { descritor: CARA, tipo:'sface' })).json();
ok('o mesmo rosto é reconhecido', q1.nome === NOME, JSON.stringify(q1));
ok('e o limiar usado é o do SFace, não o do navegador',
   q1.limiar === 0.363, String(q1.limiar));
/* Cosseno de um vetor com ele mesmo é 1. Se isto vier perto de 0, o giro da
   chave deixou de preservar ângulo — e aí o reconhecimento da caixa some. */
ok('o giro da chave preserva o cosseno (1 = idêntico)',
   Math.abs(q1.distancia - 1) < 1e-6, String(q1.distancia));

/* ---- 3. AS DUAS LISTAS NÃO SE MISTURAM -------------------------------- */
/* A asserção mais importante do arquivo. O mesmo vetor, perguntado no outro
   motor, não pode achar ninguém — os números são incomparáveis. */
const q2 = await (await post('/api/reconhecer',
  { descritor: CARA, tipo:'faceapi' })).json();
ok('o MESMO vetor, perguntado como faceapi, não acha ninguém',
   q2.nome === null, JSON.stringify(q2));

/* E a mesma pessoa pode estar nos dois, que é o que se quer: um vale na tela
   do PC, o outro na caixa. */
await post('/api/cadastro', { nome: NOME, tipo:'faceapi', descritores:[v()] });
const lista = await (await fetch(BASE + '/api/cadastros')).json();
const meus = lista.cadastros.filter(c => c.nome === NOME);
ok('a mesma pessoa pode estar cadastrada nos dois motores',
   meus.length === 2 && new Set(meus.map(c => c.tipo)).size === 2,
   JSON.stringify(meus.map(c => c.tipo)));

/* ---- 4. rosto de outra pessoa não recebe nome ------------------------- */
const q3 = await (await post('/api/reconhecer',
  { descritor: v(), tipo:'sface' })).json();
ok('outro rosto NÃO recebe nome', q3.nome === null, JSON.stringify(q3));

/* ---- 5. tipo inventado é recusado ------------------------------------- */
const r5 = await post('/api/cadastro', { nome:'X', tipo:'seiLa', descritores:[v()] });
ok('tipo de motor inventado é recusado', r5.status === 400, 'HTTP ' + r5.status);
const r5b = await post('/api/reconhecer', { descritor: v(), tipo:'seiLa' });
ok('e também ao reconhecer', r5b.status === 400, 'HTTP ' + r5b.status);

/* ---- 6. retirar o consentimento tira dos DOIS ------------------------- */
/* Sair do cadastro e continuar sendo reconhecido pela caixa seria o pior
   defeito possível desta tela. */
await post('/api/cadastro/remover', { nome: NOME });
const q4 = await (await post('/api/reconhecer',
  { descritor: CARA, tipo:'sface' })).json();
ok('removido de um lado, some dos dois', q4.nome === null, JSON.stringify(q4));

/* ---- 7. a cola do lado do Python -------------------------------------- */
console.log('\n  -- a cola entre o motor e as trilhas (Python) --');
const py = spawnSync('python3', ['testes/rosto_lado.py'], { encoding:'utf-8' });
process.stdout.write(py.stdout || '');
if(py.stderr) process.stderr.write(py.stderr);
ok('a cola do rosto passou no Python', py.status === 0);

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
