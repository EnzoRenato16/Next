/* A imagem do alerta e a lista de pessoas.
 *
 * O que se testa aqui é o que não pode falhar depois de alguém decidir guardar
 * imagem de menor de idade numa escola: que ela só entre em evento grave, que
 * toda leitura deixe rastro, e que ela suma sozinha no prazo. Se qualquer uma
 * das três quebrar, o argumento que sustenta a funcionalidade cai junto.
 *
 *     node testes/foto-pessoas.mjs
 */
import { spawn } from 'node:child_process';

const PORTA = 8791;
const BASE = `http://127.0.0.1:${PORTA}`;
const BANCO = '/tmp/auditix-teste-foto.db';

/* JPEG de 1x1 de verdade: o servidor confere o cabeçalho do data URL, e um
   "data:image/jpeg;base64,xxx" inventado passaria por engano num teste frouxo. */
const JPEG = 'data:image/jpeg;base64,' + Buffer.from(
  'ffd8ffe000104a46494600010100000100010000ffdb004300' + 'ff'.repeat(70) +
  'ffc2000b080001000101011100ffc40014000100000000000000' +
  '00000000000000000009ffda0008010100000000d7ffd9', 'hex').toString('base64');

await import('node:fs').then(fs => { try{ fs.unlinkSync(BANCO); }catch{} });

const srv = spawn('uv', ['run', 'servidor.py'], { env: { ...process.env,
  PORTA: String(PORTA),
  DATABASE_URL: '',
  WEBHOOK_URL: '',
  SQLITE_ARQUIVO: BANCO,
  /* ~3 segundos de validade: o prazo real é de dias, e um teste que espera
     dias não é rodado por ninguém. */
  FOTO_DIAS: String(3 / 86400) }, stdio:'ignore' });

const dormir = ms => new Promise(r => setTimeout(r, ms));
const json = async (u, o) => {
  const r = await fetch(BASE + u, o);
  return { codigo: r.status, corpo: await r.json().catch(() => null) };
};
const evento = (tipo, aluno = 'corpo-1') => json('/api/evento', { method:'POST',
  headers:{ 'Content-Type':'application/json' },
  body: JSON.stringify({ aluno_id:aluno, tipo_evento:tipo, localizacao:'sala-teste' }) });
const mandarFoto = (id, img = JPEG) => json('/api/foto', { method:'POST',
  headers:{ 'Content-Type':'application/json' },
  body: JSON.stringify({ evento_id:id, imagem:img }) });

let pronto = false;
for(let i = 0; i < 60 && !pronto; i++){
  try{ await fetch(BASE + '/'); pronto = true; }catch{ await dormir(500); }
}
const encerrar = c => { srv.kill(); process.exit(c); };
if(!pronto){ console.error('FALHOU: o servidor de teste não subiu'); encerrar(1); }

let bem = true;
const dizer = (ok, msg) => { if(!ok) bem = false;
  console.log((ok ? '  ok    ' : '  FALHA ') + msg); };

/* ---- a imagem só existe onde foi autorizada ---- */
const queda = (await evento('queda')).corpo;
dizer((await mandarFoto(queda.id)).codigo === 200,
      'queda aceita a imagem do instante');

const comum = (await evento('reconhecido', 'Ana Paula')).corpo;
dizer((await mandarFoto(comum.id)).codigo === 403,
      'evento COMUM recusa imagem              (403)');

dizer((await mandarFoto(999999)).codigo === 404,
      'evento inexistente recusa imagem        (404)');

dizer((await mandarFoto(queda.id, 'data:image/png;base64,AAAA')).codigo === 400,
      'só JPEG entra                           (400)');

/* ---- toda leitura deixa rastro ---- */
const a = await json('/api/foto/' + queda.id);
const b = await json('/api/foto/' + queda.id);
dizer(a.corpo.imagem === JPEG, 'a imagem volta inteira');
dizer(b.corpo.consultas === a.corpo.consultas + 1,
      'cada consulta fica registrada           (' + a.corpo.consultas + ' -> ' + b.corpo.consultas + ')');

/* ---- o painel sabe onde há imagem ---- */
const seca = (await evento('queda')).corpo;     // queda sem imagem nenhuma
const lista = (await json('/api/eventos?limite=10')).corpo;
dizer(lista.find(e => e.id === queda.id)?.tem_foto === true,
      'a listagem marca o evento COM imagem');
dizer(lista.find(e => e.id === seca.id)?.tem_foto === false,
      'e marca o evento SEM imagem');
/* O filtro do painel é de leitura: o evento comum continua gravado, só não
   aparece nesta lista. */
dizer(!lista.some(e => e.id === comum.id),
      'o filtro do painel esconde o que não é queda');

/* ---- pessoas ---- */
const p = (await json('/api/pessoas')).corpo;
dizer(p.pessoas.some(x => x.nome === 'Ana Paula'),
      'quem foi reconhecido aparece em pessoas');
dizer(!p.pessoas.some(x => x.nome.startsWith('corpo-')),
      'o corpo anônimo da queda NÃO vira pessoa');

/* ---- e a imagem vence sozinha ---- */
await dormir(3500);
dizer((await json('/api/foto/' + queda.id)).codigo === 404,
      'passado o prazo, a imagem some sozinha  (404)');
const depois = (await json('/api/eventos?limite=10')).corpo;
dizer(depois.find(e => e.id === queda.id) != null,
      'mas o EVENTO continua na cadeia');

console.log(bem ? '\nA IMAGEM DO ALERTA PASSOU' : '\nFALHOU');
encerrar(bem ? 0 : 1);
