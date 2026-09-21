/* Gera Auditix-slides.pptx a partir do mesmo conteúdo do deck em HTML.
 *
 * As duas animações não existem no PowerPoint, então elas entram como imagem no
 * instante em que dizem alguma coisa: a queda no momento do alerta, e o mapa de
 * calor já cheio. Os quadros são capturados do próprio deck em HTML (veja o
 * bloco de captura em Auditix-slides.html) e ficam em ppt/.
 *
 * As fontes são Arial, Calibri e Courier New de propósito: Bricolage Grotesque
 * e Chivo não existem na máquina de quem abrir o arquivo, e fonte ausente vira
 * substituição silenciosa que quebra o layout na hora da apresentação.
 *
 *     npm install pptxgenjs
 *     node slides-pptx.js
 */
const pptxgen = require('pptxgenjs');
const P = process.env.QUADROS || './ppt/';

const CHAO='0B100E', SUP='17211C', LINHA='24322B',
      TINTA='EDF3EF', T2='9DB0A6', T3='6A7D74',
      VERDE='3FBF5A', ALERTA='E4572E';
const TIT='Arial', TXT='Calibri', MONO='Courier New';
const W=13.333, H=7.5, M=0.75;

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.author = 'Auditix IA - grupo 11';
pres.title  = 'Auditix IA';

function nova(){
  const s = pres.addSlide();
  s.background = { color: CHAO };
  return s;
}
/* Um cartão arredondado: o mesmo motivo do deck em HTML, repetido no deck todo. */
function cartao(s, x, y, w, h){
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius:0.10,
    fill:{ color:SUP }, line:{ color:LINHA, width:1 } });
}
function olho(s, txt, cor){
  s.addText(txt.toUpperCase(), { x:M, y:0.42, w:W-2*M, h:0.3, isTextBox:true, margin:0,
    fontFace:MONO, fontSize:11, color:cor||VERDE, charSpacing:2 });
}
function titulo(s, txt, y){
  s.addText(txt, { x:M, y:y||0.82, w:W-2*M, h:1.55, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:36, bold:true, color:TINTA, lineSpacing:38 });
}
function apoio(s, runs, y, w, h){
  s.addText(runs, { x:M, y, w:w||9.6, h:h||0.8, isTextBox:true, margin:0,
    fontFace:TXT, fontSize:15, color:T2, lineSpacing:22 });
}
function rodape(s, n){
  s.addText('Auditix IA  ·  grupo 11', { x:M, y:H-0.62, w:6, h:0.3,
    isTextBox:true, margin:0, fontFace:MONO, fontSize:9, color:T3 });
  s.addText(String(n), { x:W-M-1, y:H-0.62, w:1, h:0.3, isTextBox:true, margin:0,
    fontFace:MONO, fontSize:9, color:T3, align:'right' });
}

/* ==================================================== 1. abertura ======== */
{
  const s = nova();
  s.addText([{ text:'AUDITIX IA', options:{ color:VERDE } },
             { text:'  ·  GRUPO 11  ·  2ECR', options:{ color:T3 } }],
    { x:M, y:0.7, w:7, h:0.3, isTextBox:true, margin:0, fontFace:MONO, fontSize:11, charSpacing:3 });
  s.addText('Ninguém\nestava\nolhando.', { x:M, y:1.25, w:6.2, h:3.1, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:54, bold:true, color:TINTA, lineSpacing:56 });
  apoio(s, 'Uma câmera comum grava a queda e guarda o arquivo. Alguém descobre horas depois, se descobrir. O Auditix vê no instante, avisa um humano e deixa um registro que não dá para alterar sem aparecer.', 4.35, 6.2, 1.45);
  s.addShape(pres.ShapeType.rect, { x:M, y:5.75, w:0.035, h:0.95, fill:{ color:VERDE } });
  s.addText('Alerta não é acusação.', { x:M+0.22, y:5.75, w:6, h:0.36, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:19, bold:true, color:TINTA });
  s.addText('O sistema mede pose e movimento. Ele não sabe o que aconteceu, nem quem tem razão.',
    { x:M+0.22, y:6.14, w:6, h:0.55, isTextBox:true, margin:0, fontFace:TXT, fontSize:13, color:T2 });
  s.addImage({ path:P+'queda-corte.png', x:7.35, y:2.0, w:5.25, h:2.97 });
  s.addText('A Sala, no instante do alerta. A faixa mostra o que o sistema mede.',
    { x:7.35, y:5.1, w:5.25, h:0.3, isTextBox:true, margin:0, fontFace:MONO, fontSize:9, color:T3 });
  s.addNotes('Abrir com a demonstração ao vivo, não com o slide. A queda dispara em 3 segundos na tela do notebook.');
  rodape(s, 1);
}

/* ==================================================== 2. o problema ====== */
{
  const s = nova();
  olho(s, 'O que existe hoje numa escola', ALERTA);
  titulo(s, 'Câmera não é vigilância.\nÉ arquivo morto.');
  apoio(s, 'Três coisas falham juntas, e sempre na mesma ordem.', 2.7);
  const itens = [
    ['FALHA 1', 'Ninguém olha ao vivo', 'O vídeo só é aberto depois que alguém reclama. Aí o socorro já não é socorro.'],
    ['FALHA 2', 'O registro é frágil', 'Vídeo se apaga, se corta, se sobrescreve. Numa disputa, ele vale o quanto a confiança nele permitir.'],
    ['FALHA 3', 'Vigiar é caro e invasivo', 'A saída comum é gravar mais, de todos, o tempo todo. Mais risco para o aluno, nenhuma resposta a mais.']
  ];
  itens.forEach((it, i) => {
    const x = M + i * 4.03;
    cartao(s, x, 3.3, 3.73, 2.35);
    s.addText(it[0], { x:x+0.28, y:3.55, w:3.2, h:0.25, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:10, color:VERDE, charSpacing:2 });
    s.addText(it[1], { x:x+0.28, y:3.85, w:3.2, h:0.4, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:17, bold:true, color:TINTA });
    s.addText(it[2], { x:x+0.28, y:4.35, w:3.2, h:1.1, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12.5, color:T2, lineSpacing:17 });
  });
  s.addText('A pergunta que guiou o projeto: dá para avisar na hora sem transformar a sala num estúdio de gravação?',
    { x:M, y:6.1, w:11.5, h:0.5, isTextBox:true, margin:0, fontFace:TXT, fontSize:15, italic:true, color:TINTA });
  rodape(s, 2);
}

/* ==================================================== 3. o que há ======== */
{
  const s = nova();
  olho(s, 'Não é maquete, está rodando');
  titulo(s, 'O que já funciona hoje');
  apoio(s, 'Medido nos 4.509 clipes do Fall Vision (Harvard Dataverse, CC0). Nada aqui é estimativa.', 2.3);
  const nums = [['89%','das quedas detectadas a 30 quadros por segundo', true],
                ['4.509','clipes com esqueleto quadro a quadro no treino', false],
                ['0','pedidos para fora: roda sem internet', false],
                ['11','arquivos de teste automático, do detector ao e-mail', false]];
  nums.forEach((n, i) => {
    const x = M + i * 3.02;
    s.addShape(pres.ShapeType.rect, { x, y:3.05, w:0.03, h:1.35,
      fill:{ color: n[2] ? VERDE : LINHA } });
    s.addText(n[0], { x:x+0.2, y:3.0, w:2.7, h:0.75, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:36, bold:true, color: n[2] ? VERDE : TINTA });
    s.addText(n[1], { x:x+0.2, y:3.75, w:2.6, h:0.7, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12, color:T2, lineSpacing:16 });
  });
  const linhas = [
    ['Sala auditada', 'Pose de até 6 pessoas, linha do chão calibrável, e um alerta por episódio, não dezenove.'],
    ['Três medidas', 'Queda por rede treinada. Corrida e briga por regra, e a tela diz qual é qual.'],
    ['Câmera IP', 'RTSP para ponte local para WebRTC. Fração de segundo de atraso, e a imagem não sai da escola.'],
    ['Dashboard', 'Integridade da cadeia, série por dia, mapa de ocupação e quem sumiu.'],
    ['Aviso', 'E-mail em segundos, com espera mínima entre avisos para a caixa continuar sendo lida.']
  ];
  linhas.forEach((l, i) => {
    const y = 4.60 + i * 0.42;
    s.addShape(pres.ShapeType.line, { x:M, y, w:11.8, h:0, line:{ color:LINHA, width:1 } });
    s.addText(l[0], { x:M, y:y+0.06, w:2.6, h:0.32, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:12.5, bold:true, color:TINTA });
    s.addText(l[1], { x:M+2.75, y:y+0.06, w:9, h:0.32, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12, color:T2 });
  });
  rodape(s, 3);
}

/* ==================================================== 4. camadas ========= */
{
  const s = nova();
  olho(s, 'Por dentro');
  titulo(s, 'Quatro camadas, e nenhuma\ndelas confia sozinha.');
  apoio(s, 'Cada uma erra de um jeito diferente. Por isso são quatro, e por isso cada corte foi medido, não escolhido no olho.', 2.7);
  const cam = [
    ['CAMADA 1 · POSE', '33 pontos do corpo', 'Ombro, quadril, joelho. A imagem vira geometria antes de qualquer decisão.', 'nenhum quadro é guardado nesta etapa'],
    ['CAMADA 2 · REGRAS', 'Tronco, altura, proporção', 'Caixa mais larga que alta, corpo abaixo da própria altura, tronco fora da vertical.', 'caixa > 1,2 = 89% das quedas, 10% de falso'],
    ['CAMADA 3 · REDE', 'Uma rede pequena', '12 atributos, 113 pesos. Fora do que viu no treino, ela se cala em vez de chutar.', 'o freio custa 0,2 ponto de revocação'],
    ['CAMADA 4 · CHÃO', 'A linha do chão', 'Com a câmera fixa, cabeça abaixo da linha é queda. Sem depender de mais nada.', 'vale por câmera; mexeu nela, marca de novo']
  ];
  cam.forEach((c, i) => {
    const x = M + i * 3.02;
    cartao(s, x, 3.3, 2.82, 2.9);
    s.addText(c[0], { x:x+0.24, y:3.5, w:2.4, h:0.25, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:9, color:VERDE, charSpacing:1.5 });
    s.addText(c[1], { x:x+0.24, y:3.78, w:2.4, h:0.62, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:15, bold:true, color:TINTA, lineSpacing:18 });
    s.addText(c[2], { x:x+0.24, y:4.46, w:2.4, h:1.0, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:11.5, color:T2, lineSpacing:15 });
    s.addText(c[3], { x:x+0.24, y:5.5, w:2.4, h:0.55, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:8.5, color:T3, lineSpacing:12 });
  });
  s.addText('Custo de quadros por segundo, medido:  30 fps = 89%   ·   15 fps = 87%   ·   10 fps = 86%',
    { x:M, y:6.45, w:11.5, h:0.3, isTextBox:true, margin:0, fontFace:MONO, fontSize:11, color:T3 });
  rodape(s, 4);
}

/* ==================================================== 5. a prova ========= */
{
  const s = nova();
  olho(s, 'A parte que ninguém copia');
  titulo(s, 'Cada evento fecha o anterior.');
  apoio(s, 'Cada linha guarda o resumo da anterior. Adulterar uma antiga quebra a corrente dali para a frente. As anteriores continuam válidas.', 2.4);
  s.addImage({ path:P+'cadeia.png', x:M, y:3.35, w:11.83, h:1.10 });
  s.addText('Adulterado o evento #223: ele e todos os seguintes deixam de fechar.',
    { x:M, y:4.55, w:11.5, h:0.3, isTextBox:true, margin:0, fontFace:MONO, fontSize:10, color:ALERTA });
  const l2 = [['Onde fica','PostgreSQL na nuvem. Se ele cair, o sistema vai para o banco local e avisa na tela.'],
              ['Para que serve','A escola não pede confiança: ela mostra a conta. Se alguém de dentro mexer, a conta denuncia.']];
  l2.forEach((l, i) => {
    const y = 5.25 + i * 0.62;
    s.addShape(pres.ShapeType.line, { x:M, y, w:11.8, h:0, line:{ color:LINHA, width:1 } });
    s.addText(l[0], { x:M, y:y+0.12, w:2.6, h:0.35, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:14, bold:true, color:TINTA });
    s.addText(l[1], { x:M+2.75, y:y+0.12, w:9, h:0.4, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:13, color:T2 });
  });
  s.addNotes('Aqui é o momento de abrir o deck em HTML e clicar num elo na frente da banca.');
  rodape(s, 5);
}

/* ==================================================== 6. privacidade ===== */
{
  const s = nova();
  olho(s, 'Privacidade por construção');
  titulo(s, 'A imagem só existe\nquando alguém precisa julgar.');
  apoio(s, 'Enquanto nada acontece, nada é gravado. Em alerta grave, o quadro é guardado já limitado.', 2.95);
  const g = [
    ['Rosto apagado','Mosaico sobre a cabeça de todas as pessoas, feito antes de a imagem sair.'],
    ['Falha fechado','Se não conseguir localizar ninguém para apagar, a imagem não é enviada.'],
    ['Prazo curto','A imagem se apaga sozinha em 7 dias. O evento e o hash ficam.'],
    ['Acesso registrado','Abrir a imagem vira linha no banco, inclusive para quem administra.'],
    ['Biometria com prazo','Com consentimento, e vence sozinho: 365 dias, ou 90 sem a pessoa aparecer.'],
    ['Mapa sem nome','Conta passagens por célula, não pessoas.']
  ];
  g.forEach((it, i) => {
    const col = i % 2, lin = Math.floor(i / 2);
    const x = M + col * 6.05, y = 3.5 + lin * 1.05;
    cartao(s, x, y, 5.75, 0.92);
    s.addText(it[0], { x:x+0.26, y:y+0.1, w:5.2, h:0.3, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:13.5, bold:true, color:VERDE });
    s.addText(it[1], { x:x+0.26, y:y+0.42, w:5.25, h:0.45, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:11.5, color:T2, lineSpacing:14 });
  });
  rodape(s, 6);
}

/* ==================================================== 7. o alerta ======== */
{
  const s = nova();
  olho(s, 'Do chão à caixa de entrada');
  titulo(s, 'Segundos, não turnos.');
  const et = [
    ['NA SALA','A queda vira evento','O evento entra na corrente antes de qualquer tentativa de avisar alguém.','o registro nunca depende da nuvem estar de pé'],
    ['NA NUVEM','Uma função envia','A escola não guarda senha de e-mail nenhuma. A credencial não existe como arquivo.','segredo compartilhado barra quem descobrir a URL'],
    ['NA COORDENAÇÃO','Um e-mail que se lê','O que houve, onde, quando, e que é um pedido de conferência.','um aviso a cada poucos segundos é um aviso que ninguém lê']
  ];
  et.forEach((c, i) => {
    const x = M + i * 4.03;
    cartao(s, x, 2.85, 3.73, 2.75);
    s.addText(c[0], { x:x+0.28, y:3.08, w:3.2, h:0.25, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:9.5, color:VERDE, charSpacing:1.5 });
    s.addText(c[1], { x:x+0.28, y:3.38, w:3.2, h:0.4, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:16, bold:true, color:TINTA });
    s.addText(c[2], { x:x+0.28, y:3.88, w:3.2, h:1.0, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12, color:T2, lineSpacing:16 });
    s.addText(c[3], { x:x+0.28, y:4.9, w:3.2, h:0.6, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:8.5, color:T3, lineSpacing:12 });
  });
  s.addText('O caminho tem teste automático, inclusive o que custa caro quando falha: e-mail sem segredo e e-mail em rajada.',
    { x:M, y:6.0, w:11.5, h:0.5, isTextBox:true, margin:0, fontFace:TXT, fontSize:14, color:T2 });
  rodape(s, 7);
}

/* ==================================================== 8. dashboard ======= */
{
  const s = nova();
  olho(s, 'Dashboard ligado ao banco por API');
  titulo(s, 'Um dashboard que lê o banco,\nnão um print de tela.');
  s.addText([{ text:'Sete rotas em FastAPI sobre o PostgreSQL. A única que escreve alguma coisa é a da imagem, e o que ela escreve é ', options:{ color:T2 } },
             { text:'quem olhou.', options:{ color:TINTA, bold:true } }],
    { x:M, y:2.75, w:11.5, h:0.55, isTextBox:true, margin:0, fontFace:TXT, fontSize:14 });
  s.addImage({ path:P+'calor.png', x:M, y:3.35, w:5.6, h:3.63 });
  const q = [['“Aconteceu alguma coisa?”','/api/painel','Último evento, onde, há quanto tempo. E a corrente em uma palavra.'],
             ['“Onde a sala aperta?”','/api/mapa','Mapa suavizado por vizinhança, com um anel em onde mais pararam.'],
             ['“Fulano sumiu?”','/api/pessoas','Quem foi reconhecido e há quantos dias não aparece.'],
             ['“Posso confiar nisto?”','/api/verificar','Recalcula a corrente desde a gênese, contra o hash recalculado.']];
  q.forEach((it, i) => {
    const y = 3.45 + i * 0.88;
    s.addText(it[0], { x:6.75, y, w:5.9, h:0.3, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:14, bold:true, color:TINTA });
    s.addText(it[1], { x:6.75, y:y+0.28, w:2.4, h:0.25, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:9.5, color:VERDE });
    s.addText(it[2], { x:6.75, y:y+0.52, w:5.9, h:0.3, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:11.5, color:T2 });
  });
  rodape(s, 8);
}

/* ==================================================== 9. a rota ========== */
{
  const s = nova();
  olho(s, 'Onde isto vai dar');
  titulo(s, 'De uma sala para a rede inteira.');
  const r = [
    ['HOJE','Uma sala, uma câmera, um alerta','DE PÉ','Queda ao vivo, evento na corrente, e-mail na coordenação, imagem com rosto apagado. Roda sem internet, numa máquina comum.'],
    ['PRÓXIMO','Escola-piloto','A VALIDAR','A medida que ainda não temos: quantos alertas por dia a coordenação aguenta. É esse número, e não a revocação, que decide se é usável.'],
    ['DEPOIS','Várias câmeras, uma corrente só','A CONSTRUIR','Cada sala com seu detector na borda, todas na mesma trilha auditável.'],
    ['A TESE','A mesma base, outros lugares','EM ESTUDO','Borda que decide mais prova que não se altera: portaria com consentimento, e a área da saúde.']
  ];
  r.forEach((it, i) => {
    const y = 2.55 + i * 1.12;
    s.addShape(pres.ShapeType.line, { x:M, y, w:11.8, h:0, line:{ color:LINHA, width:1 } });
    s.addText(it[0], { x:M, y:y+0.18, w:1.8, h:0.3, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:10, color: i === 0 ? VERDE : T3, charSpacing:1.5 });
    s.addText(it[1], { x:M+2.0, y:y+0.12, w:6.2, h:0.38, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:17, bold:true, color:TINTA });
    s.addShape(pres.ShapeType.roundRect, { x:M+8.35, y:y+0.15, w:1.75, h:0.32, rectRadius:0.16,
      fill:{ color:CHAO }, line:{ color: i === 0 ? VERDE : LINHA, width:1 } });
    s.addText(it[2], { x:M+8.35, y:y+0.17, w:1.75, h:0.28, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:8.5, color: i === 0 ? VERDE : T3, align:'center' });
    s.addText(it[3], { x:M+2.0, y:y+0.55, w:9.5, h:0.5, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12, color:T2, lineSpacing:16 });
  });
  rodape(s, 9);
}

/* ============================================= 10. valor para quem compra = */
{
  const s = nova();
  olho(s, 'Onde está o valor para quem compra');
  titulo(s, 'Três frentes, em ordem de\nforça para uma escola.');
  const fr = [
    ['O QUE FAZ ASSINAR', 'Risco jurídico,\nnão segurança',
     'O medo real de uma mantenedora não é perder uma queda. É o processo depois. Registro que denuncia adulteração, imagem com prazo, acesso rastreado e biometria com vencimento reduzem exposição.',
     'LGPD, e a disputa judicial que vem depois'],
    ['O QUE SALVA', 'Custo evitado',
     'Uma câmera comum só serve depois do fato. O valor está em chegar antes: socorro em segundos em vez de minutos, e uma queda vista no instante em que acontece.',
     'o alerta sai antes de alguém reclamar'],
    ['O QUE SUBSTITUI', 'Licença de nuvem',
     'Se a escola já paga mensalidade por câmera para algum sistema de nuvem, o nosso número entra no lugar dele. E, ao contrário do dele, dá para conferir de onde sai.',
     'comparável, e verificável linha a linha']
  ];
  fr.forEach((c, i) => {
    const x = M + i * 4.03;
    cartao(s, x, 3.3, 3.73, 3.05);
    s.addText(c[0], { x:x+0.28, y:3.55, w:3.2, h:0.25, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:9.5, color:VERDE, charSpacing:1.5 });
    s.addText(c[1], { x:x+0.28, y:3.85, w:3.2, h:0.75, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:17, bold:true, color:TINTA, lineSpacing:21 });
    s.addText(c[2], { x:x+0.28, y:4.68, w:3.2, h:1.35, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:12, color:T2, lineSpacing:16 });
    s.addText(c[3], { x:x+0.28, y:5.95, w:3.2, h:0.35, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:8.5, color:T3 });
  });
  s.addNotes('A primeira é a que fecha a venda. Segurança comove; risco jurídico faz a diretoria assinar.');
  rodape(s, 10);
}

/* ==================================================== 11. mercado ======== */
{
  const s = nova();
  olho(s, 'Valor econômico e entrada no mercado');
  titulo(s, 'O custo de cobrir mais\numa sala é uma câmera.');
  apoio(s, 'O concorrente cobra licença mensal POR CÂMERA, porque o vídeo dele roda na nuvem dele. O nosso roda na borda, e o que sobe para a nuvem é uma linha de texto.', 2.75, 11.5);

  /* coluna esquerda: o custo, que é o número que nós temos */
  s.addText('O que custa', { x:M, y:3.55, w:5.6, h:0.35, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:18, bold:true, color:TINTA });
  const custo = [['Câmera IP, por sala','R$ 200 a R$ 680', false],
                 ['Servidor','1 PC comum por escola', false],
                 ['Licença de software','R$ 0 por câmera', true],
                 ['Nuvem do alerta','centavos por mês', true]];
  custo.forEach((c, i) => {
    const y = 4.05 + i * 0.52;
    s.addShape(pres.ShapeType.line, { x:M, y, w:5.6, h:0, line:{ color:LINHA, width:1 } });
    s.addText(c[0], { x:M, y:y+0.09, w:3.3, h:0.35, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:13, bold:true, color:TINTA });
    s.addText(c[1], { x:M+3.3, y:y+0.11, w:2.3, h:0.32, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:11, color: c[2] ? VERDE : T2, align:'right' });
  });
  s.addShape(pres.ShapeType.line, { x:M, y:6.13, w:5.6, h:0, line:{ color:LINHA, width:1 } });
  s.addText('sem placa de vídeo, sem custo por fluxo, sem mensalidade que cresce com a escola',
    { x:M, y:6.22, w:5.6, h:0.4, isTextBox:true, margin:0, fontFace:MONO, fontSize:9, color:T3, lineSpacing:13 });

  /* coluna direita: como se entra */
  const XD = 7.1;
  s.addText('Como entra no mercado', { x:XD, y:3.55, w:5.5, h:0.35, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:18, bold:true, color:TINTA });
  const passos = [
    ['Uma escola, de graça','Em troca do dado que falta: quantos alertas por dia a coordenação aguenta, e quantos foram engano.'],
    ['O piloto vira carta','Um depoimento da coordenação abre a porta da segunda escola melhor que qualquer slide.'],
    ['Vender para a rede','Grupo educacional tem dezenas de unidades e um decisor só. É para ele que custo marginal quase zero é irresistível.']
  ];
  passos.forEach((pa, i) => {
    const y = 4.05 + i * 0.85;
    /* o número do passo num círculo: em pptxgenjs o círculo é `ellipse`, não `oval` */
    s.addShape(pres.ShapeType.ellipse,
      { x:XD, y:y+0.02, w:0.32, h:0.32, fill:{ color:CHAO }, line:{ color:LINHA, width:1 } });
    s.addText(String(i+1), { x:XD, y:y+0.05, w:0.32, h:0.26, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:10, color:VERDE, align:'center' });
    s.addText(pa[0], { x:XD+0.5, y, w:5.0, h:0.3, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:14, bold:true, color:TINTA });
    s.addText(pa[1], { x:XD+0.5, y:y+0.3, w:5.0, h:0.55, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:11.5, color:T2, lineSpacing:14 });
  });
  s.addText('Modelo: assinatura por escola, não por câmera. Expandir deixa de ser uma nova decisão de compra.',
    { x:XD, y:6.22, w:5.5, h:0.4, isTextBox:true, margin:0, fontFace:MONO, fontSize:9, color:T3, lineSpacing:13 });

  s.addNotes('Se perguntarem tamanho de mercado: dizer que o dado vem do Censo Escolar do INEP e que o preço praticado sai de conversa com escolas, e que nenhum dos dois foi estimado por nós.');
  rodape(s, 11);
}

/* =============================================== 12. o que falta medir === */
{
  const s = nova();
  olho(s, 'Honestidade intelectual', ALERTA);
  titulo(s, 'O que ainda não medimos,\ne não vamos inventar.');
  apoio(s, 'Quatro coisas que decidem se isto é negócio e se a detecção se sustenta, e que nenhuma planilha nossa pode responder.', 2.8, 11.5);
  /* A quarta entrou junto com a briga, e é o preço de ter sido honesto no
     código: briga hoje é regra sobre as features do DIFEM, sem classificador
     treinado, porque não temos dataset. Dizer isso aqui é mais forte do que
     deixar a banca descobrir perguntando. */
  const faltam = [
    ['Quanto uma escola paga hoje','por monitoramento eletrônico','fonte: ligar para três escolas'],
    ['Quantas escolas no recorte','rede, município ou grupo','fonte: Censo Escolar, INEP'],
    ['Alertas por dia que se aguenta','e quantos foram engano','fonte: o piloto, e só ele'],
    ['Acerto da briga em vídeo real','hoje é regra, não modelo treinado','fonte: RWF-2000, 2.000 clipes']
  ];
  faltam.forEach((f, i) => {
    const x = M + i * 3.01;
    s.addShape(pres.ShapeType.roundRect, { x, y:3.5, w:2.80, h:2.1, rectRadius:0.10,
      fill:{ color:CHAO }, line:{ color:LINHA, width:1, dashType:'dash' } });
    s.addText(f[0], { x:x+0.24, y:3.76, w:2.36, h:0.66, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:13.5, bold:true, color:TINTA, lineSpacing:17 });
    s.addText(f[1], { x:x+0.24, y:4.48, w:2.36, h:0.42, isTextBox:true, margin:0,
      fontFace:TXT, fontSize:11.5, color:T2, lineSpacing:14 });
    s.addText(f[2], { x:x+0.24, y:4.98, w:2.36, h:0.45, isTextBox:true, margin:0,
      fontFace:MONO, fontSize:8.5, color:ALERTA, lineSpacing:11 });
  });
  s.addText('Uma banca pergunta a fonte. “Estimativa nossa” derruba o slide, e com ele o resto da apresentação.',
    { x:M, y:6.1, w:11.5, h:0.45, isTextBox:true, margin:0, fontFace:TXT, fontSize:14, italic:true, color:T2 });
  rodape(s, 12);
}

/* ==================================================== 13. fecho ========== */
{
  const s = nova();
  olho(s, 'Para fechar');
  s.addText('Um sistema que avisa\ne responde pelo que disse.',
    { x:M, y:1.1, w:11.5, h:1.9, isTextBox:true, margin:0,
      fontFace:TIT, fontSize:44, bold:true, color:TINTA, lineSpacing:52 });
  s.addText([{ text:'Detectar queda é a parte fácil. O que torna o Auditix defensável numa escola é o que vem junto: ', options:{ color:T2 } },
             { text:'o registro que denuncia adulteração', options:{ color:TINTA } },
             { text:', ', options:{ color:T2 } },
             { text:'a imagem que se apaga', options:{ color:TINTA } },
             { text:', ', options:{ color:T2 } },
             { text:'o acesso que fica gravado', options:{ color:TINTA } },
             { text:' e ', options:{ color:T2 } },
             { text:'o alerta que pede conferência em vez de afirmar culpa', options:{ color:TINTA } },
             { text:'.', options:{ color:T2 } }],
    { x:M, y:3.25, w:11.3, h:1.3, isTextBox:true, margin:0, fontFace:TXT, fontSize:16, lineSpacing:24 });
  s.addShape(pres.ShapeType.rect, { x:M, y:4.95, w:0.04, h:1.1, fill:{ color:VERDE } });
  s.addText('Alerta não é acusação.', { x:M+0.25, y:4.95, w:9, h:0.45, isTextBox:true, margin:0,
    fontFace:TIT, fontSize:24, bold:true, color:TINTA });
  s.addText('É um pedido para alguém ir olhar, feito rápido o bastante para ainda valer a pena.',
    { x:M+0.25, y:5.45, w:9.5, h:0.5, isTextBox:true, margin:0, fontFace:TXT, fontSize:14, color:T2 });
  s.addText('Auditix IA  ·  grupo 11  ·  2ECR          Desafio DATEN x FIAP  ·  “Antes do NEXT”',
    { x:M, y:6.5, w:11.5, h:0.3, isTextBox:true, margin:0, fontFace:MONO, fontSize:10, color:T3 });
}

pres.writeFile({ fileName: '/home/user/Next/Auditix-slides.pptx' })
  .then(f => console.log('gerado:', f));
