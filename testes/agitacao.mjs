/* Teste da camada de agitação — roda com:  node testes/agitacao.mjs
 *
 * Existe porque o limiar AGITA_GOLPE não pode ser um número escolhido no olho.
 * Ele separa "alguém foi atingido" de "alguém está abraçando", e errar para
 * mais acusa uma pessoa inocente.
 *
 * O teste monta sequências de pose sintéticas (30fps, coordenadas normalizadas
 * como as do MediaPipe) e mede o mesmo número que a Sala mede ao vivo. As
 * funções abaixo são COPIADAS de auditix-sala.html — se você mudar lá, cole
 * aqui e rode de novo.
 *
 * Duas tentativas anteriores foram reprovadas por este teste, e vale saber
 * quais, porque as duas parecem certas no papel:
 *
 *   · "punho apontado para o outro" (cosseno): abraço deu 0.97, mais dirigido
 *     que um soco. Reprovado.
 *   · "pico de aceleração do punho": dança deu 15.9 sem nada acontecer.
 *     Reprovado.
 *
 * O que passou foi a combinação — velocidade NA DIREÇÃO do outro, medida como
 * encurtamento da distância punho→tronco alheio, com o pico tomado num trecho
 * curto e não na média da janela.
 *
 * LIMITE HONESTO: estes cenários são sintéticos. Eles provam que a fórmula
 * separa os casos, não que os números batem com gente de verdade na sua sala.
 * Para calibrar de verdade, ligue a Sala, faça os gestos na frente da câmera e
 * leia os valores que o console imprime quando o par está perto e agitado.
 */

const AGITA_GOLPE = 1.0, AGITA_FECHA = 0.6, AGITA_PERTO = 0.9, AGITA_ENER = 1.1;

/* O quanto o punho de `t` avança SOBRE o tronco de `alvo`, em alturas por
   segundo. Devolve o melhor dos dois punhos.

   É o encurtamento da distância punho→tronco alheio dividido pelo tempo. Junta
   velocidade e direção num número só, que é o ponto: rápido sem direção é
   dança, dirigido sem velocidade é abraço, e nenhum dos dois passa daqui. */
function golpeDirigido(t, alvo, agora){
  if(alvo.qx == null || alvo.ox == null) return 0;
  const tx = (alvo.qx + alvo.ox) / 2, ty = (alvo.qy + alvo.oy) / 2;
  const h = t.hist.filter(x => agora - x.t < 420);
  if(h.length < 2) return 0;
  const alt = t.altura || 1;
  let melhor = 0;

  /* O PICO num trecho curto, não a média da janela inteira. Um soco dura uns
     130ms; medido de ponta a ponta de uma janela de 400ms ele aparece pela
     metade, e foi assim que a primeira versão desta função deixou um soco
     passar por baixo do limiar. O trecho fica entre 90 e 200ms: abaixo disso é
     tremor de landmark, acima dilui o avanço de novo. */
  for(const esq of [true, false]){
    for(let i = 0; i < h.length; i++){
      const p0 = esq ? h[i].px : h[i].pd;
      const d0 = Math.hypot(tx - p0.x, ty - p0.y);
      for(let j = i + 1; j < h.length; j++){
        const dt = (h[j].t - h[i].t) / 1000;
        if(dt < 0.09) continue;
        if(dt > 0.20) break;
        const p1 = esq ? h[j].px : h[j].pd;
        const d1 = Math.hypot(tx - p1.x, ty - p1.y);
        melhor = Math.max(melhor, (d0 - d1) / alt / dt);
      }
    }
  }
  return melhor;
}

/* Aproximação: a distância entre os dois encurtando, em alturas por segundo.
   Positivo = se aproximando. Não decide nada sozinho — abraço também se
   aproxima — mas entra no texto para quem for conferir. */
function aproximacao(a, b, agora){
  const ha = a.hist.filter(x => agora - x.t < 500);
  const hb = b.hist.filter(x => agora - x.t < 500);
  if(ha.length < 2 || hb.length < 2) return 0;
  const a0 = ha[0], a1 = ha[ha.length-1], b0 = hb[0], b1 = hb[hb.length-1];
  const dt = (Math.min(a1.t, b1.t) - Math.max(a0.t, b0.t)) / 1000;
  if(dt <= 0) return 0;
  const escala = (a.altura + b.altura) / 2 || 1;
  const d0 = Math.hypot(a0.qx - b0.qx, a0.qy - b0.qy);
  const d1 = Math.hypot(a1.qx - b1.qx, a1.qy - b1.qy);
  return (d0 - d1) / escala / dt;
}

const H=0.6;
function corpo(qx,qy){ return {qx,qy,ox:qx,oy:qy-0.25,altura:H,hist:[]}; }
function encher(t,n,t0,punho,mover){
  for(let i=0;i<n;i++){
    const p=punho(i), q=mover?mover(i):{x:t.qx,y:t.qy};
    t.hist.push({t:t0+i*33,qx:q.x,qy:q.y,ang:5,px:p.e,pd:p.d});
  }
  const u=t.hist[t.hist.length-1]; t.qx=u.qx; t.qy=u.qy; t.ox=t.qx; t.oy=t.qy-0.25;
}
const T0=100000,N=20,AGORA=T0+N*33;
function cenario(nome,montar,energia,esperado){
  const a=corpo(0.40,0.60), b=corpo(0.60,0.60);
  montar(a,b); a.energia=energia; b.energia=energia;
  const escala=(a.altura+b.altura)/2;
  const perto=Math.hypot(a.qx-b.qx,a.qy-b.qy)<AGITA_PERTO*escala;
  const bravo=a.energia>AGITA_ENER&&b.energia>AGITA_ENER;
  const golpe=Math.max(golpeDirigido(a,b,AGORA),golpeDirigido(b,a,AGORA));
  const fecha=aproximacao(a,b,AGORA);
  const antes=perto&&bravo;
  const depois=perto&&bravo&&golpe>AGITA_GOLPE;
  const ok = depois===esperado ? 'OK ' : 'ERRO';
  console.log(ok+' '+nome.padEnd(24)+
    'golpe '+golpe.toFixed(2).padStart(6)+'/'+AGITA_GOLPE+
    ' | aprox '+fecha.toFixed(2).padStart(5)+
    ' || antes '+(antes?'DISPARA':'  -    ')+'  depois '+(depois?'DISPARA':'  -    '));
  return depois===esperado;
}
let tudo=true;
tudo &= cenario('soco (briga)',(a,b)=>{
  const ax=(b.qx+b.ox)/2, ay=(b.qy+b.oy)/2;
  encher(a,N,T0,i=>{const f=i<12?0:Math.min(1,(i-12)/4);
    return {e:{x:0.36,y:0.45},d:{x:0.45+(ax-0.45)*f*0.92,y:0.42+(ay-0.42)*f*0.92}};});
  encher(b,N,T0,i=>({e:{x:0.64,y:0.45+0.01*Math.sin(i)},d:{x:0.68,y:0.45}}));
},2.0,true);
tudo &= cenario('empurrão (rápido)',(a,b)=>{
  const ax=(b.qx+b.ox)/2, ay=(b.qy+b.oy)/2;
  encher(a,N,T0,i=>{const f=i<11?0:Math.min(1,(i-11)/6);
    return {e:{x:0.42+(ax-0.42)*f*0.8,y:0.46+(ay-0.46)*f*0.8},
            d:{x:0.46+(ax-0.46)*f*0.8,y:0.46+(ay-0.46)*f*0.8}};});
  encher(b,N,T0,i=>({e:{x:0.64,y:0.46},d:{x:0.68,y:0.46}}));
},1.6,true);
tudo &= cenario('abraço',(a,b)=>{
  encher(a,N,T0,i=>({e:{x:0.36+0.004*i,y:0.45},d:{x:0.44+0.004*i,y:0.45}}),
                 i=>({x:0.40+0.003*i,y:0.60}));
  encher(b,N,T0,i=>({e:{x:0.56-0.004*i,y:0.45},d:{x:0.64-0.004*i,y:0.45}}),
                 i=>({x:0.60-0.003*i,y:0.60}));
},1.4,false);
tudo &= cenario('dança / comemoração',(a,b)=>{
  encher(a,N,T0,i=>({e:{x:0.34,y:0.42+0.06*Math.sin(i*0.9)},d:{x:0.46,y:0.42+0.06*Math.cos(i*0.9)}}));
  encher(b,N,T0,i=>({e:{x:0.56,y:0.42+0.06*Math.cos(i*0.9)},d:{x:0.68,y:0.42+0.06*Math.sin(i*0.9)}}));
},2.2,false);
tudo &= cenario('conversando parados',(a,b)=>{
  encher(a,N,T0,i=>({e:{x:0.36,y:0.50},d:{x:0.45,y:0.50}}));
  encher(b,N,T0,i=>({e:{x:0.56,y:0.50},d:{x:0.65,y:0.50}}));
},0.3,false);
tudo &= cenario('aceno de longe',(a,b)=>{
  encher(a,N,T0,i=>({e:{x:0.34,y:0.40+0.05*Math.sin(i)},d:{x:0.46,y:0.40+0.05*Math.sin(i)}}));
  encher(b,N,T0,i=>({e:{x:0.56,y:0.40},d:{x:0.68,y:0.40}}));
},1.5,false);
cenario('empurrão lento (ambíguo)',(a,b)=>{
  const ax=(b.qx+b.ox)/2, ay=(b.qy+b.oy)/2;
  encher(a,N,T0,i=>{const f=Math.min(1,i/16);
    return {e:{x:0.42+(ax-0.42)*f*0.8,y:0.46+(ay-0.46)*f*0.8},
            d:{x:0.46+(ax-0.46)*f*0.8,y:0.46+(ay-0.46)*f*0.8}};});
  encher(b,N,T0,i=>({e:{x:0.64,y:0.46},d:{x:0.68,y:0.46}}));
},1.6,false);
console.log('\n'+(tudo?'TODOS OS CENÁRIOS PASSARAM':'>>> ALGUM CENÁRIO FALHOU'));
