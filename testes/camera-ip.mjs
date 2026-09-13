/* O caminho da câmera IP, ponta a ponta, dentro do navegador.
 *
 * Diferente dos outros testes daqui, este NÃO roda sozinho: precisa do
 * servidor no ar e do Playwright instalado. Rode assim:
 *
 *     uv run servidor.py            (noutra janela)
 *     npm i playwright && node testes/camera-ip.mjs
 *
 * O que ele prova: a Sala monta a oferta WebRTC, espera o ICE fechar, manda
 * para a ponte, recebe a resposta, e o vídeo chega e é MEDIDO. O que ele não
 * prova: compatibilidade com o go2rtc de verdade — o par aqui é uma página
 * falsa que responde como ele. Para valer, teste com a câmera na mão.
 *
 * O par falso emite a 15fps de propósito: é o que a Tapo C200 entrega.
 */
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';

const CAMINHOS = ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'];
const executablePath = CAMINHOS.find(existsSync);   // undefined = o do Playwright

const nav = await chromium.launch({ executablePath, args:['--no-sandbox','--no-proxy-server'] });
const ctx = await nav.newContext();

const cam = await ctx.newPage();
await cam.goto('about:blank');
await cam.evaluate(() => {
  window.responder = async (sdp) => {
    const cv = Object.assign(document.createElement('canvas'), { width:640, height:480 });
    const cx = cv.getContext('2d');
    setInterval(() => { cx.fillStyle = '#123'; cx.fillRect(0,0,640,480);
      cx.fillStyle = '#fff'; cx.fillRect((Date.now()/10)%600, 200, 40, 80); }, 33);
    const fl = cv.captureStream(15);
    const pc = new RTCPeerConnection({ iceServers:[] });
    fl.getTracks().forEach(t => pc.addTrack(t, fl));
    await pc.setRemoteDescription({ type:'offer', sdp });
    await pc.setLocalDescription(await pc.createAnswer());
    await new Promise(ok => { if(pc.iceGatheringState==='complete') return ok();
      const t = setTimeout(ok, 2000);
      pc.addEventListener('icegatheringstatechange', () => {
        if(pc.iceGatheringState==='complete'){ clearTimeout(t); ok(); } }); });
    return pc.localDescription.sdp;
  };
});

const sala = await ctx.newPage();
const erros = [];
sala.on('pageerror', e => erros.push('pageerror: ' + e.message));

/* O par falso fala WHEP, como o go2rtc: recebe SDP cru e devolve SDP cru.
   A versão anterior deste teste falava JSON dos dois lados — era a MINHA
   suposição, e por isso ele passava enquanto o go2rtc respondia
   "sdp: syntax error at pos 1". Um teste que inventa o outro lado não testa
   nada; daí a checagem do corpo abaixo. */
let corpoEnviado = null;
await sala.route('**/api/webrtc*', async route => {
  corpoEnviado = route.request().postData();
  const sdp = await cam.evaluate(o => window.responder(o), corpoEnviado);
  await route.fulfill({ status:200, contentType:'application/sdp', body: sdp });
});

const falhar = async (m) => { console.error('FALHOU: ' + m); await nav.close(); process.exit(1); };

try{ await sala.goto('http://127.0.0.1:8000/', { timeout:20000 }); }
catch{ await falhar('o servidor não está no ar (uv run servidor.py)'); }

await sala.evaluate(() => localStorage.setItem('auditix.fonte','127.0.0.1:1984/sala'));
await sala.reload();
const rotulo = await sala.textContent('#btn-fonte');
if(!/câmera IP/.test(rotulo)) await falhar('a tela não mostra a fonte escolhida: ' + rotulo);

/* Os modelos vêm de CDN. Trocados por bonecos: o que se testa aqui é o
   caminho da câmera, não o reconhecimento. */
await sala.evaluate(() => {
  window.faceapi = { detectAllFaces: () => Promise.resolve([]), nets:{},
                     TinyFaceDetectorOptions: function(){} };
  prontos = true;
  redePose = { detectForVideo: () => ({ landmarks: [] }) };
});

await sala.click('#ligar');
try{
  await sala.waitForFunction(() => document.getElementById('cam').videoWidth > 0,
                             { timeout:25000 });
}catch{
  await falhar('nenhum quadro chegou. tela: ' +
    (await sala.textContent('#desltxt')).replace(/\s+/g,' ').trim());
}

if(!corpoEnviado || !corpoEnviado.startsWith('v='))
  await falhar('a oferta não foi enviada como SDP cru (WHEP), e sim: ' +
               String(corpoEnviado).slice(0, 40));
console.log('a oferta sai como SDP cru');

const d = await sala.evaluate(() => { const v = document.getElementById('cam');
  return { w:v.videoWidth, h:v.videoHeight, over:document.getElementById('over').width }; });
if(d.over !== d.w) await falhar('o canvas não acompanhou o vídeo: ' + d.over + ' vs ' + d.w);
console.log(`vídeo ${d.w}x${d.h}, canvas alinhado`);

await sala.waitForTimeout(3000);
if(!await sala.evaluate(() => document.getElementById('cam').currentTime > 1))
  await falhar('o vídeo não avançou: o fluxo travou depois do primeiro quadro');
console.log('o laço roda sobre o fluxo da ponte');

await sala.click('#desligar');
await sala.waitForTimeout(500);
if(await sala.evaluate(() => !!document.getElementById('cam').srcObject))
  await falhar('sobrou fluxo aberto depois de fechar');
console.log('fecha sem deixar fluxo aberto');

await nav.close();
if(erros.length){ console.error('\nERROS NA PÁGINA:\n' + erros.join('\n')); process.exit(1); }
console.log('\nO CAMINHO DA CÂMERA IP PASSOU');
