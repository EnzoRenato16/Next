/* Conferência de layout do Auditix-slides.pptx — roda com:
 *     node slides-pptx.js && node testes/slides.mjs
 *
 * POR QUE ISTO EXISTE, e não é preciosismo.
 *
 * O LibreOffice deste ambiente não abre nem um .pptx vazio, então não há como
 * olhar os slides antes de entregar. Sem inspeção visual, o jeito de não
 * mandar um deck torto para uma apresentação é MEDIR: abrir o arquivo gerado,
 * ler a posição e o tamanho de cada caixa, estimar quantas linhas o texto
 * ocupa e reclamar do que não cabe.
 *
 * Na primeira vez que este cálculo rodou ele achou três caixas estourando, uma
 * delas precisando do DOBRO da altura declarada. Nenhuma tinha sido notada lendo
 * o código.
 *
 * O QUE ELE NÃO É: não é renderização. A estimativa de largura de caractere é
 * aproximada e conservadora, então ele erra para o lado de reclamar demais.
 * Uma reclamação isolada pode ser folga real; um estouro de 1,5x não é.
 */
import fs from 'node:fs';
import JSZip from 'jszip';

const EMU = 914400;                 // EMUs por polegada
const W = 13.333, H = 7.5;
/* Overscan de projetor come uns 3% da borda, o que num slide de 7,5" dá 0,22".
   0,4" é folga de quase o dobro disso, e é onde a sobrancelha de cada slide
   mora (y = 0,42) de propósito, desde antes desta conferência existir. */
const MARGEM = 0.4;

/* Largura média de caractere como fração do corpo da fonte. Medido grosso, e de
   propósito por baixo do real para Arial/Calibri: subestimar a largura faz o
   teste reclamar de menos, e um teste que reclama de menos é inútil. Então o
   número é o maior dos plausíveis. */
const LARG_CAR = 0.52;
/* Só vale quando o slide NÃO declara entrelinha. Quando declara, o número
   declarado é o que manda — ignorá-lo foi o primeiro bug deste teste: ele
   acusava 1,18x em todo título de duas linhas, sempre o mesmo fator, e fator
   repetido é assinatura de erro sistemático, não de nove problemas diferentes. */
const ENTRELINHA = 1.22;

const zip = await JSZip.loadAsync(fs.readFileSync('Auditix-slides.pptx'));
const nomes = Object.keys(zip.files)
  .filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n))
  .sort((a, b) => (+a.match(/\d+/)[0]) - (+b.match(/\d+/)[0]));

let estouros = 0, fora = 0, caixas = 0;

for(const nome of nomes){
  const n = +nome.match(/\d+/)[0];
  const xml = await zip.file(nome).async('string');

  /* Cada forma com texto: a geometria vem de <a:off>/<a:ext>, o texto e o corpo
     da fonte vêm dos <a:r> dentro dela. */
  for(const sp of xml.split('<p:sp>').slice(1)){
    const off = sp.match(/<a:off x="(-?\d+)" y="(-?\d+)"\/>/);
    const ext = sp.match(/<a:ext cx="(\d+)" cy="(\d+)"\/>/);
    if(!off || !ext) continue;
    const x = +off[1]/EMU, y = +off[2]/EMU, w = +ext[1]/EMU, h = +ext[2]/EMU;

    /* Fora da margem de segurança. Projetor corta borda, e um rodapé colado no
       canto some na sala. */
    if(x < MARGEM - 1e-6 || y < MARGEM - 1e-6 ||
       x + w > W - MARGEM + 1e-6 || y + h > H - MARGEM + 1e-6){
      /* O rodapé mora abaixo da margem de propósito: é o único. */
      const ehRodape = y > H - 0.9 && h < 0.4;
      if(!ehRodape){
        fora++;
        console.log(`  slide ${n}: forma em (${x.toFixed(2)}, ${y.toFixed(2)}) ` +
                    `${w.toFixed(2)}x${h.toFixed(2)} sai da margem de ${MARGEM}"`);
      }
    }

    const textos = [...sp.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map(m => m[1]);
    if(!textos.length) continue;
    const szs = [...sp.matchAll(/sz="(\d+)"/g)].map(m => +m[1]/100);
    if(!szs.length) continue;
    const pt = Math.max(...szs);
    if(!textos.join('').length) continue;
    caixas++;

    /* CADA SEGMENTO QUEBRA SOZINHO. Somar todos os caracteres e dividir pela
       largura supõe que o texto flui contínuo, e um "\n" no meio do título
       reinicia a linha: contando junto, "Ninguém / estava / olhando." virava
       quatro linhas em vez de três. Era o segundo bug deste teste. */
    const bruto = sp.replace(/<a:br\/>/g, '\u0001')
                    .replace(/<\/a:p>\s*<a:p>/g, '\u0001');
    const segs = [...bruto.matchAll(/<a:t>([^<]*)<\/a:t>|\u0001/g)]
      .reduce((acc, m) => { m[0] === '\u0001' ? acc.push('')
                                              : acc[acc.length-1] += (m[1] || ''); return acc; }, ['']);

    const porLinha = Math.max(1, Math.floor(w * 72 / (pt * LARG_CAR)));
    const linhas = segs.reduce((n, seg) => n + Math.max(1, Math.ceil(seg.length / porLinha)), 0);

    /* A entrelinha declarada vence a estimativa. */
    const lnSpc = sp.match(/<a:spcPts val="(\d+)"\/>/);
    const alturaLinha = lnSpc ? +lnSpc[1]/100 : pt * ENTRELINHA;
    const preciso = linhas * alturaLinha / 72;

    if(preciso > h * 1.02){
      estouros++;
      console.log(`  slide ${n}: "${textos.join('').slice(0, 44)}…" precisa de ` +
                  `${preciso.toFixed(2)}" e tem ${h.toFixed(2)}" ` +
                  `(${(preciso/h).toFixed(2)}x)`);
    }
  }
}

console.log(`\n${nomes.length} slides, ${caixas} caixas de texto medidas`);
console.log(`${estouros} estourando, ${fora} fora da margem de ${MARGEM}"`);
if(nomes.length !== 14){
  console.log(`FALHA: esperava 14 slides`);
  process.exit(1);
}
process.exit(estouros || fora ? 1 : 0);
