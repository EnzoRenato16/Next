/* Os modelos locais precisam chegar ao navegador com o TIPO certo.
 *
 * Existe porque isto já quebrou em produção: o servidor deixava o sistema
 * operacional decidir o tipo de cada arquivo. O Linux conhece ".mjs", o
 * Windows não — lá o módulo do MediaPipe ia marcado como binário qualquer, o
 * Chrome se recusava a executá-lo, e a tela ficava presa em "Carregando o
 * detector de corpo..." sem erro nenhum. Passou nos testes porque os testes
 * rodavam em Linux.
 *
 * Precisa do servidor no ar:  uv run servidor.py
 */
const BASE = process.env.BASE || 'http://127.0.0.1:8000';

const ESPERADO = [
  ['vendor/mediapipe/vision_bundle.mjs',              'text/javascript'],
  ['vendor/mediapipe/wasm/vision_wasm_internal.js',   'text/javascript'],
  // instantiateStreaming recusa qualquer coisa que não seja exatamente isto
  ['vendor/mediapipe/wasm/vision_wasm_internal.wasm', 'application/wasm'],
  ['vendor/mediapipe/pose_landmarker_lite.task',      'application/octet-stream'],
  ['vendor/face-api/face-api.js',                     'text/javascript'],
  ['vendor/face-api/model/face_recognition_model.bin','application/octet-stream'],
  ['vendor/face-api/model/tiny_face_detector_model-weights_manifest.json', 'application/json'],
  ['vendor/fontes/fontes.css',                        'text/css'],
];

/* Um caminho que saia da pasta nunca pode ser servido: quem pede isso não é
   navegador, é quem quer ler o disco da máquina. */
const PROIBIDO = ['vendor/../servidor.py', 'vendor/..%2fservidor.py',
                  'vendor/nao-existe.js', 'vendor/../auditix.db'];

let falhas = 0;
const dizer = (ok, msg) => { if(!ok) falhas++;
  console.log((ok ? '  ok   ' : '  FALHA ') + msg); };

try{
  await fetch(BASE + '/');
}catch{
  console.error('o servidor não está no ar em ' + BASE + ' (uv run servidor.py)');
  process.exit(1);
}

console.log('tipo de cada arquivo:');
for(const [caminho, tipo] of ESPERADO){
  const r = await fetch(BASE + '/' + caminho);
  const visto = (r.headers.get('content-type') || '').split(';')[0].trim();
  dizer(r.ok && visto === tipo,
        `${caminho.split('/').pop().padEnd(42)} ${r.status} ${visto || '(sem tipo)'}`
        + (visto === tipo ? '' : `  — esperado ${tipo}`));
}

console.log('\nfora da pasta vendor:');
for(const caminho of PROIBIDO){
  const r = await fetch(BASE + '/' + caminho, { redirect:'manual' });
  dizer(r.status === 404, `${caminho.padEnd(42)} ${r.status}`);
}

console.log(falhas ? `\n${falhas} FALHA(S)` : '\nOS ESTÁTICOS ESTÃO CERTOS');
process.exit(falhas ? 1 : 0);
