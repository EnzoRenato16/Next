/* Biometria cancelável — roda com:  node testes/biometria.mjs
 *
 * Precisa do servidor no ar:  uv run servidor.py
 *
 * POR QUE ISTO EXISTE. O pedido foi "reconhecer sem guardar a cara". A imagem
 * já não era guardada — o cadastro grava 128 números medidos do rosto. Só que
 * 128 números AINDA identificam uma pessoa: quem levar o banco pode cruzar com
 * outro banco de rostos e saber que fulano está nos dois.
 *
 * A solução é girar esses números com uma chave que não mora no banco. Girar
 * não muda distância nenhuma, então o reconhecimento sai idêntico; mas os
 * números guardados passam a estar num sistema de eixos que só a chave conhece.
 *
 * É ISSO QUE ESTE ARQUIVO COBRA, e cada asserção existe porque a versão errada
 * dela é silenciosa: um giro que vazasse os números crus continuaria
 * reconhecendo perfeitamente, e um giro que quebrasse a distância só apareceria
 * na frente da banca, com a pessoa cadastrada e o sistema dizendo que não a
 * conhece.
 */
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

/* Um rosto sintético estável, para dar para repetir a pergunta. */
let semente = 12345;
const aleatorio = () => (semente = (semente * 1103515245 + 12345) % 2147483648)
                        / 2147483648;
const rosto = () => Array.from({length:128}, () => aleatorio() - 0.5);
const somar = (d, r) => d.map(x => x + (Math.random() - 0.5) * r);
const dist = (a, b) => Math.sqrt(a.reduce((s, x, i) => s + (x-b[i])**2, 0));

const NOME = 'Bio ' + Date.now();
const CARA = rosto();

/* ---- 1. o banco NÃO guarda os números que subiram ------------------------ */
const r1 = await post('/api/cadastro', { nome: NOME, descritores:[CARA] });
ok('o cadastro é aceito', r1.ok, 'HTTP ' + r1.status);

const lista = await (await fetch(BASE + '/api/cadastros?descritores=1')).json();
const meu = lista.cadastros.find(c => c.nome === NOME);
ok('o servidor se declara protegido', lista.protegidos === true);
ok('a ficha existe e tem uma amostra', !!meu && meu.descritores.length === 1);

const guardado = meu.descritores[0];
ok('o que está guardado tem 128 números, como antes', guardado.length === 128);
/* A asserção central. Se isto passar com os números iguais, o giro não
   aconteceu e todo o resto é encenação. */
const iguais = guardado.filter((x, i) => Math.abs(x - CARA[i]) < 1e-9).length;
ok('e NÃO é o rosto que subiu — os números são outros',
   iguais < 3, iguais + ' de 128 coincidem');
ok('e está longe do original, não é um empurrãozinho',
   dist(guardado, CARA) > 1, 'distância ' + dist(guardado, CARA).toFixed(2));

/* ---- 2. e mesmo assim reconhece ----------------------------------------- */
/* O ponto todo do giro: distância não muda. Se este bloco falhar, trocamos
   privacidade por um sistema que não reconhece ninguém. */
const q1 = await (await post('/api/reconhecer', { descritor: CARA })).json();
ok('o mesmo rosto é reconhecido', q1.nome === NOME, JSON.stringify(q1));
ok('e com distância praticamente zero', q1.distancia < 1e-6, String(q1.distancia));

/* ---- 3. a distância foi preservada, não só o caso exato ------------------ */
/* Um rosto NUNCA volta com os mesmos 128 números: volta parecido. Reconhecer é
   medir esse "parecido", então o que importa é a distância sobreviver ao giro —
   e é aqui que um hash teria destruído tudo. */
const perto = somar(CARA, 0.04);
const qp = await (await post('/api/reconhecer', { descritor: perto })).json();
ok('o mesmo rosto um pouco diferente continua sendo reconhecido',
   qp.nome === NOME, JSON.stringify(qp));
const esperado = dist(perto, CARA);
ok('e a distância medida pelo servidor bate com a real',
   Math.abs(qp.distancia - esperado) < 1e-3,
   'servidor ' + qp.distancia + ' vs real ' + esperado.toFixed(4));

/* ---- 4. não inventa nome ------------------------------------------------- */
const qo = await (await post('/api/reconhecer', { descritor: rosto() })).json();
ok('um rosto de outra pessoa NÃO recebe nome', qo.nome === null,
   JSON.stringify(qo));
ok('e mesmo assim a distância volta, para dar para calibrar o limiar',
   typeof qo.distancia === 'number');

/* ---- 5. descritor torto é recusado na entrada ---------------------------- */
const rt = await post('/api/reconhecer', { descritor:[1,2,3] });
ok('descritor de tamanho errado é recusado ao reconhecer', rt.status === 400,
   'HTTP ' + rt.status);

/* ---- 6. remover o cadastro apaga o reconhecimento junto ------------------ */
/* Retirar o consentimento e continuar sendo reconhecido seria o pior defeito
   possível desta tela. */
await post('/api/cadastro/remover', { nome: NOME });
const qr = await (await post('/api/reconhecer', { descritor: CARA })).json();
ok('depois de remover, o mesmo rosto deixa de ser reconhecido',
   qr.nome === null, JSON.stringify(qr));

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
