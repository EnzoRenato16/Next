/* O caminho do alerta: evento -> filtro -> webhook, com segredo e espera.
 *
 * Sobe um servidor de mentira no lugar da Lambda e confere o que chega nele.
 * O que se testa aqui é o que custa caro quando erra: e-mail sem segredo (que
 * deixa qualquer um gastar a conta da escola), e e-mail em rajada (que faz
 * todo mundo parar de ler os alertas).
 *
 *     node testes/alerta.mjs
 */
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';

const PORTA_FALSA = 8799, PORTA = 8788;
const recebidos = [];
/* Quanto a Lambda de mentira demora para responder. Sem internet (a rede da
   AIBOX não tem), a de verdade não responde nunca — e é aí que se descobre se
   o registro espera por ela. */
let lentidao = 0;

const falso = createServer((req, res) => {
  let corpo = '';
  req.on('data', p => corpo += p);
  req.on('end', () => {
    recebidos.push({ segredo: req.headers['x-auditix-segredo'] || null,
                     corpo: JSON.parse(corpo || '{}') });
    setTimeout(() => {
      res.writeHead(200, { 'Content-Type':'application/json' });
      res.end('{"msg":"enviado"}');
    }, lentidao);
  });
});
await new Promise(r => falso.listen(PORTA_FALSA, r));

const srv = spawn('uv', ['run', 'servidor.py'], { env: { ...process.env,
  PORTA: String(PORTA),
  WEBHOOK_URL: `http://127.0.0.1:${PORTA_FALSA}/`,
  WEBHOOK_SEGREDO: 'senha-de-teste',
  ALERTA_TIPOS: 'graves',
  ALERTA_ESPERA: '2' }, stdio:'ignore' });

const dormir = ms => new Promise(r => setTimeout(r, ms));
const evento = async (tipo, quem = 'corpo-1') => {
  const t0 = Date.now();
  await fetch(`http://127.0.0.1:${PORTA}/api/evento`, { method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ aluno_id: quem, tipo_evento: tipo, localizacao:"sala-teste" }) });
  const gasto = Date.now() - t0;
  await dormir(300);
  return gasto;
};

let pronto = false;
for(let i = 0; i < 60 && !pronto; i++){
  try{ await fetch(`http://127.0.0.1:${PORTA}/`); pronto = true; }
  catch{ await dormir(500); }
}
const encerrar = c => { srv.kill(); falso.close(); process.exit(c); };
if(!pronto){ console.error('FALHOU: o servidor de teste não subiu'); encerrar(1); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };

await evento('queda');
dizer(recebidos.length === 1, 'queda vira alerta                        (' + recebidos.length + ')');
dizer(recebidos[0]?.segredo === 'senha-de-teste',
      'vai com o segredo combinado             (' + recebidos[0]?.segredo + ')');

await evento('reconhecido');
dizer(recebidos.length === 1, 'evento comum NÃO vira alerta            (' + recebidos.length + ')');

await evento('queda');
dizer(recebidos.length === 1, 'segunda queda em 2s não repete o e-mail (' + recebidos.length + ')');

await dormir(2200);
await evento('queda');
dizer(recebidos.length === 2, 'passada a espera, alerta de novo        (' + recebidos.length + ')');

/* A espera é por PESSOA. Era só por tipo: duas quedas de alunos diferentes em
   menos de um minuto davam UM e-mail — justamente no tumulto. */
await evento('queda', 'corpo-2');
dizer(recebidos.length === 3, 'OUTRA pessoa caindo na espera: alerta   (' + recebidos.length + ')');

/* O registro não espera o e-mail. Antes o webhook rodava dentro do /api/evento
   com 5 s de prazo, a AIBOX desiste em 4, e sem internet o evento era gravado
   e contado como "não chegou". */
lentidao = 3000;
const gasto = await evento('queda', 'corpo-3');
dizer(gasto < 1000, 'com a Lambda lenta, o registro responde em ' + gasto + ' ms');
await dormir(3200);
dizer(recebidos.length === 4, 'e o e-mail sai mesmo assim, depois      (' + recebidos.length + ')');

console.log(bem ? '\nO CAMINHO DO ALERTA PASSOU' : '\nFALHOU');
encerrar(bem ? 0 : 1);
