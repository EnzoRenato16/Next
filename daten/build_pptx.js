const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";               // 13.33 x 7.5
const W = 13.33, H = 7.5;

// ---- paleta ----
const C = {
  ground:"0B1220", panel:"111E33", panel2:"0D1728", line:"22344F",
  ink:"EAF1FB", dim:"9FB2CE", faint:"6B809F",
  teal:"2EE6C5", amber:"FFB648", red:"FF6B7A"
};
const FONT = "Calibri";
const MONO = "Consolas";

// NADA de transparência em formas (o QuickLook do iOS renderiza mal): calculamos
// o tom sólido = accent misturado sobre o fundo, para o mesmo efeito visual.
function tint(hex, ratio){
  const g=[0x0B,0x12,0x20];
  const a=[parseInt(hex.slice(0,2),16),parseInt(hex.slice(2,4),16),parseInt(hex.slice(4,6),16)];
  return a.map((v,i)=>Math.round(v*ratio+g[i]*(1-ratio)).toString(16).padStart(2,"0")).join("").toUpperCase();
}
const BRACKET = tint(C.teal,0.5);   // teal fosco sólido para os cantos

// em array de runs, a formatação PRECISA ir em options:{}
function T(arr){ return arr.map(r=>{ const {text, ...opt}=r; return {text, options:opt}; }); }

function bg(s){ s.background = { color: C.ground }; }

function brackets(s){
  const L=0.55, Tp=0.45, len=0.55, th=0.045;
  const pairs=[
    [L,Tp,len,th],[L,Tp,th,len],
    [W-L-len,Tp,len,th],[W-L-th,Tp,th,len],
    [L,H-Tp-th,len,th],[L,H-Tp-len,th,len],
    [W-L-len,H-Tp-th,len,th],[W-L-th,H-Tp-len,th,len]
  ];
  pairs.forEach(([x,y,w,h])=>s.addShape(p.ShapeType.rect,{x,y,w,h,fill:{color:BRACKET},line:{type:"none"}}));
}

function eyebrow(s,txt){
  s.addText("● "+txt,{x:0.9,y:0.6,w:11,h:0.35,isTextBox:true,margin:0,
    fontFace:MONO,fontSize:12,charSpacing:3,bold:true,color:C.teal});
}

function chrome(s,n){
  s.addText("Auditix AI",{x:0.9,y:H-0.85,w:6,h:0.3,isTextBox:true,margin:0,
    fontFace:MONO,fontSize:11,bold:true,color:C.dim});
  s.addText(T([{text:`${n}`,color:C.teal,bold:true},{text:" / 5",color:C.dim}]),
    {x:W-2.4,y:H-0.85,w:1.5,h:0.3,isTextBox:true,margin:0,align:"right",fontFace:MONO,fontSize:11});
}

// cartão com marcador + título + descrição (fills sólidos)
function iconRow(s,{x,y,w,mk,markColor,title,desc}){
  const h=1.0;
  s.addShape(p.ShapeType.roundRect,{x,y,w,h,rectRadius:0.08,fill:{color:C.panel},line:{color:C.line,width:1.25}});
  const sq=0.66;
  s.addShape(p.ShapeType.roundRect,{x:x+0.3,y:y+(h-sq)/2,w:sq,h:sq,rectRadius:0.06,
    fill:{color:tint(markColor,0.2)},line:{color:markColor,width:1.25}});
  s.addText(mk,{x:x+0.3,y:y+(h-sq)/2,w:sq,h:sq,isTextBox:true,margin:0,align:"center",valign:"middle",
    fontFace:FONT,fontSize:19,bold:true,color:markColor});
  const tx=x+1.25, tw=w-1.55;
  s.addText(title,{x:tx,y:y+0.13,w:tw,h:0.36,isTextBox:true,margin:0,fontFace:FONT,fontSize:16,bold:true,color:C.ink});
  s.addText(desc,{x:tx,y:y+0.5,w:tw,h:0.42,isTextBox:true,margin:0,fontFace:FONT,fontSize:12,color:C.dim});
}

// ============================ SLIDE 1 — CAPA ============================
(()=>{ const s=p.addSlide(); bg(s); brackets(s);
  eyebrow(s,"DATEN × FIAP  ·  ANTES DO NEXT");
  s.addText(T([{text:"Auditix ",color:C.ink},{text:"AI",color:C.teal}]),
    {x:0.85,y:2.35,w:11.5,h:1.6,isTextBox:true,margin:0,fontFace:FONT,fontSize:66,bold:true});
  s.addText(T([{text:"Segurança patrimonial com ",color:C.ink},
             {text:"visão de IA",color:C.teal,bold:true},
             {text:" que reconhece, em tempo real, quem pode estar ali.",color:C.ink}]),
    {x:0.9,y:4.2,w:10.5,h:1.0,isTextBox:true,margin:0,fontFace:FONT,fontSize:23,lineSpacingMultiple:1.1});
  s.addText(T([{text:"grupo11",color:C.dim,bold:true},{text:"   ·   Edge AI no AIBOX   ·   DATEN × FIAP",color:C.faint}]),
    {x:0.9,y:5.8,w:11,h:0.4,isTextBox:true,margin:0,fontFace:MONO,fontSize:14,charSpacing:1});
  chrome(s,1);
  s.addNotes("Abertura. Somos o grupo Auditix AI. Nosso projeto: transformar uma câmera comum em um sistema de segurança patrimonial que reconhece pessoas em tempo real, rodando localmente no AIBOX.");
})();

// ============================ SLIDE 2 — PROBLEMA ============================
(()=>{ const s=p.addSlide(); bg(s); brackets(s);
  eyebrow(s,"O PROBLEMA");
  s.addText("Câmera todo mundo tem.\nVigilância de verdade, não.",
    {x:0.9,y:1.0,w:11.5,h:1.4,isTextBox:true,margin:0,fontFace:FONT,fontSize:36,bold:true,color:C.ink,lineSpacingMultiple:1.0});
  s.addText(T([{text:"A segurança patrimonial ainda depende de ",color:C.dim},
             {text:"olho humano",color:C.ink,bold:true},
             {text:" vigiando dezenas de câmeras ao mesmo tempo.",color:C.dim}]),
    {x:0.9,y:2.4,w:11,h:0.5,isTextBox:true,margin:0,fontFace:FONT,fontSize:16});
  const rows=[
    ["!","Olho humano cansa","Muitas telas para poucos vigilantes: distração e fadiga deixam passar o que importa."],
    ["!","Estranho passa despercebido","Pessoas não autorizadas circulam sem ninguém notar até ser tarde."],
    ["!","Sem prova do que aconteceu","Sem registro confiável de quem entrou e quando, a câmera só mostra o passado."]
  ];
  rows.forEach((r,i)=>iconRow(s,{x:0.9,y:3.05+i*1.15,w:11.5,mk:r[0],markColor:C.red,title:r[1],desc:r[2]}));
  chrome(s,2);
  s.addNotes("O problema de negócio: vigilância humana falha. Cansaço, câmeras demais, e no fim não há prova confiável de quem entrou.");
})();

// ============================ SLIDE 3 — SOLUÇÃO ============================
(()=>{ const s=p.addSlide(); bg(s); brackets(s);
  eyebrow(s,"A SOLUÇÃO");
  s.addText("Uma câmera que entende quem está no ambiente.",
    {x:0.9,y:1.0,w:11.5,h:0.85,isTextBox:true,margin:0,fontFace:FONT,fontSize:33,bold:true,color:C.ink});
  s.addText(T([{text:"O ",color:C.dim},{text:"Auditix AI",color:C.teal,bold:true},
             {text:" roda a IA no próprio local (AIBOX) e ",color:C.dim},
             {text:"reconhece pessoas",color:C.ink,bold:true},{text:" em tempo real.",color:C.dim}]),
    {x:0.9,y:1.9,w:11.4,h:0.5,isTextBox:true,margin:0,fontFace:FONT,fontSize:16});
  const rows=[
    ["✓","Reconhece os autorizados","Sabe quem faz parte da equipe cadastrada e confirma sua presença."],
    ["?","Sinaliza desconhecidos","Rosto sem cadastro vira um evento de segurança para revisão."],
    ["●","Registra tudo localmente","Nome, horário e imagem salvos no próprio aparelho, sem depender de nuvem."]
  ];
  rows.forEach((r,i)=>iconRow(s,{x:0.9,y:2.6+i*1.13,w:11.5,mk:r[0],markColor:C.teal,title:r[1],desc:r[2]}));
  s.addShape(p.ShapeType.roundRect,{x:0.9,y:6.02,w:11.5,h:0.5,rectRadius:0.06,fill:{color:tint(C.amber,0.14)},line:{color:C.amber,width:1.25}});
  s.addText(T([{text:"Ética:  ",color:C.amber,bold:true},
             {text:"alerta não é acusação. Todo evento fica pendente de validação humana.",color:C.dim}]),
    {x:1.15,y:6.02,w:11,h:0.5,isTextBox:true,margin:0,valign:"middle",fontFace:FONT,fontSize:13});
  chrome(s,3);
  s.addNotes("A solução processa no próprio local (Edge/AIBOX): rápido e privado (LGPD). Reforçar a ética: sinalizamos, não acusamos.");
})();

// ============================ SLIDE 4 — COMO FUNCIONA (grid 2x2) ============================
(()=>{ const s=p.addSlide(); bg(s); brackets(s);
  eyebrow(s,"COMO FUNCIONA");
  s.addText("Do rosto na sala ao nome na tela.",
    {x:0.9,y:1.0,w:11.5,h:0.9,isTextBox:true,margin:0,fontFace:FONT,fontSize:34,bold:true,color:C.ink});
  s.addText(T([{text:"Cenário: um ambiente com ",color:C.dim},{text:"pessoas",color:C.ink,bold:true},
             {text:". O sistema precisa reconhecer cada uma e decidir se é autorizada.",color:C.dim}]),
    {x:0.9,y:1.95,w:11.4,h:0.5,isTextBox:true,margin:0,fontFace:FONT,fontSize:16});
  const steps=[
    ["1","Cadastro",'A foto de cada pessoa autorizada vira uma "assinatura" numérica do rosto.'],
    ["2","Câmera no ambiente","YOLO nano localiza cada rosto no vídeo, mesmo com várias pessoas juntas."],
    ["3","Segue e compara","ByteTrack mantém o ID de cada um; o rosto é comparado com o cadastro."],
    ["4","Decisão","Autorizado (nome na tela) ou desconhecido (alerta e registro do evento)."]
  ];
  const cw=5.6, ch=1.75, gx=0.9, gy=2.6, gapx=0.3, gapy=0.3;
  const amberTint=tint(C.amber,0.2);
  steps.forEach((st,i)=>{
    const col=i%2, row=Math.floor(i/2);
    const x=gx+col*(cw+gapx), y=gy+row*(ch+gapy);
    s.addShape(p.ShapeType.roundRect,{x,y,w:cw,h:ch,rectRadius:0.08,fill:{color:C.panel},line:{color:C.line,width:1.25}});
    const sq=0.75;
    s.addShape(p.ShapeType.roundRect,{x:x+0.35,y:y+0.35,w:sq,h:sq,rectRadius:0.06,fill:{color:amberTint},line:{color:C.amber,width:1.25}});
    s.addText(st[0],{x:x+0.35,y:y+0.35,w:sq,h:sq,isTextBox:true,margin:0,align:"center",valign:"middle",fontFace:FONT,fontSize:22,bold:true,color:C.amber});
    s.addText(st[1],{x:x+1.3,y:y+0.4,w:cw-1.6,h:0.5,isTextBox:true,margin:0,fontFace:FONT,fontSize:18,bold:true,color:C.ink});
    s.addText(st[2],{x:x+0.35,y:y+1.05,w:cw-0.7,h:0.6,isTextBox:true,margin:0,fontFace:FONT,fontSize:13,color:C.dim});
  });
  chrome(s,4);
  s.addNotes("O fluxo em 4 passos: cadastro; YOLO nano detecta os rostos; ByteTrack segue cada pessoa (sem contar 2x) e compara com o cadastro; decide autorizado x desconhecido.");
})();

// ============================ SLIDE 5 — TECNOLOGIA + STATUS ============================
(()=>{ const s=p.addSlide(); bg(s); brackets(s);
  eyebrow(s,"TECNOLOGIA E PRÓXIMOS PASSOS");
  s.addText("Roda no local, sem nuvem.",
    {x:0.9,y:1.0,w:11.5,h:0.9,isTextBox:true,margin:0,fontFace:FONT,fontSize:34,bold:true,color:C.ink});
  s.addText(T([{text:"Processar no ",color:C.dim},{text:"AIBOX",color:C.ink,bold:true},
             {text:" (Edge AI) deixa a resposta rápida e mantém as imagens no próprio ambiente (privacidade e LGPD).",color:C.dim}]),
    {x:0.9,y:1.95,w:11.4,h:0.5,isTextBox:true,margin:0,fontFace:FONT,fontSize:16});

  const panelY=2.65, panelH=3.85, pw=5.6;
  const drawPanel=(x,label,labelColor,items,marker,chips)=>{
    s.addShape(p.ShapeType.roundRect,{x,y:panelY,w:pw,h:panelH,rectRadius:0.09,fill:{color:C.panel},line:{color:C.line,width:1.25}});
    s.addShape(p.ShapeType.roundRect,{x:x+0.4,y:panelY+0.4,w:3.1,h:0.5,rectRadius:0.25,fill:{color:tint(labelColor,0.18)},line:{color:labelColor,width:1.25}});
    s.addText(label,{x:x+0.4,y:panelY+0.4,w:3.1,h:0.5,isTextBox:true,margin:0,align:"center",valign:"middle",fontFace:FONT,fontSize:13,bold:true,color:labelColor});
    const runs=[];
    items.forEach((it)=>{
      runs.push({text:marker+"  ",color:labelColor,bold:true});
      runs.push({text:it,color:C.dim,breakLine:true,paraSpaceAfter:9});
    });
    s.addText(T(runs),{x:x+0.45,y:panelY+1.1,w:pw-0.9,h:2.1,isTextBox:true,margin:0,fontFace:FONT,fontSize:14,lineSpacingMultiple:1.05});
    let cx=x+0.45; const cyl=panelY+panelH-0.55;
    chips.forEach(ch=>{
      const cwid=0.28+ch.length*0.105;
      s.addShape(p.ShapeType.roundRect,{x:cx,y:cyl,w:cwid,h:0.42,rectRadius:0.2,fill:{color:C.ground},line:{color:C.line,width:1.25}});
      s.addText(ch,{x:cx,y:cyl,w:cwid,h:0.42,isTextBox:true,margin:0,align:"center",valign:"middle",fontFace:MONO,fontSize:11,color:C.dim});
      cx+=cwid+0.18;
    });
  };
  drawPanel(0.9,"JÁ FIZEMOS",C.teal,
    ["Código do reconhecimento escrito (detectar, seguir e comparar)",
     "IA leve: YOLO nano (detecção) + ByteTrack (tracking)",
     "Backend definido: OpenCV, FastAPI e SQLite"],
    "✓",["YOLO nano","ByteTrack","OpenCV"]);
  drawPanel(0.9+pw+0.33,"PRÓXIMOS PASSOS",C.amber,
    ["Subir no AIBOX e conectar a câmera",
     "Cadastrar as pessoas autorizadas",
     "Testar o reconhecimento no ambiente real"],
    "→",["reconhecido","desconhecido","evento"]);
  chrome(s,5);
  s.addNotes("Stack: YOLO nano (detecção) + ByteTrack (tracking), OpenCV, FastAPI e SQLite, no AIBOX (ARM64). Status honesto: código e arquitetura prontos; falta subir no AIBOX, cadastrar e testar no ambiente real.");
})();

p.writeFile({ fileName: "Auditix_AI_Pitch.pptx" }).then(f=>console.log("OK:",f));
