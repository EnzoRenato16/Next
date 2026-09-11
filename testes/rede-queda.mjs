/* Trava o porte da rede de queda para JavaScript — node testes/rede-queda.mjs
 *
 * O treino acontece em Python; quem decide ao vivo é o JavaScript da Sala. Se
 * as duas implementações divergirem, o sistema não dá erro: dá número plausível
 * e errado. Nesta base de código isso já aconteceu antes, com um tensor lido no
 * formato errado, e custou horas.
 *
 * Então este teste pega janelas REAIS do dataset (treino/provas.json), roda o
 * caminho inteiro em JS — as 12 características e a rede — e compara com o que
 * o Python calculou, número a número.
 */
import fs from 'node:fs';

const sala = fs.readFileSync(new URL('../auditix-sala.html', import.meta.url), 'utf8');
const ini = sala.indexOf('const QUEDA_MU');
const fim = sala.indexOf('/* ---- queda: fim da rede ----');
if(ini < 0 || fim < 0){ console.log('não achei a rede dentro do auditix-sala.html'); process.exit(1); }
const { caracteristicasQueda, redeQueda, QUEDA_LIMIAR } =
  new Function(sala.slice(ini, fim) +
    '\nreturn { caracteristicasQueda, redeQueda, QUEDA_LIMIAR };')();

const provas = JSON.parse(fs.readFileSync(new URL('../treino/provas.json', import.meta.url), 'utf8'));

let piorCar = 0, piorNota = 0, ruins = 0;
for(const c of provas.casos){
  /* os quadros vêm na mesma ordem e com os mesmos campos que a Sala guarda */
  const h = c.quadros.map(q => ({ qx:q[0], qy:q[1], altura:q[2], eixo:q[3],
                                  ang:q[4], ombro:q[5], prop:q[6] }));
  const car = caracteristicasQueda(h, provas.fps);
  if(!car){ console.log('FALHA: características nulas em ' + c.clipe); ruins++; continue; }
  for(let i = 0; i < car.length; i++){
    const e = Math.abs(car[i] - c.car[i]);
    if(e > piorCar){ piorCar = e; }
    if(e > 2e-4){ ruins++;
      console.log(`FALHA ${c.clipe} característica ${i}: JS ${car[i].toFixed(6)} vs Python ${c.car[i]}`); }
  }
  const nota = redeQueda(car);
  const en = Math.abs(nota - c.nota);
  if(en > piorNota) piorNota = en;
  if(en > 2e-4){ ruins++;
    console.log(`FALHA ${c.clipe} nota: JS ${nota.toFixed(6)} vs Python ${c.nota}`); }
}

console.log(`\n${provas.casos.length} janelas reais do dataset conferidas`);
console.log(`  maior diferença nas características: ${piorCar.toExponential(2)}`);
console.log(`  maior diferença na nota do modelo:   ${piorNota.toExponential(2)}`);

/* E uma conferência de sentido, não só de aritmética: as janelas de clipes com
   queda têm que pontuar mais alto que as de clipes sem. Bater com o Python não
   adianta se os dois estiverem errados juntos. */
const q = provas.casos.filter(c => c.queda).map(c => c.nota);
const n = provas.casos.filter(c => !c.queda).map(c => c.nota);
const med = a => a.length ? a.reduce((s,v)=>s+v,0)/a.length : NaN;
console.log(`\n  nota média em clipes COM queda:  ${med(q).toFixed(3)}`);
console.log(`  nota média em clipes SEM queda:  ${med(n).toFixed(3)}   (limiar ${QUEDA_LIMIAR})`);
if(!(med(q) > med(n))){ console.log('FALHA: a rede não separa os dois grupos'); ruins++; }

console.log(ruins ? `\n${ruins} DIVERGÊNCIA(S)\n` : '\nJS e Python calculam a mesma coisa\n');
process.exit(ruins ? 1 : 0);
