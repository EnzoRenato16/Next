/* O banco do laboratório abre com o código novo — roda com:
 *     node testes/banco-antigo.mjs
 *
 * Não precisa do servidor no ar: sobe os seus, em portas e bancos à parte.
 *
 * POR QUE ISTO EXISTE. O PC do laboratório já tem um auditix.db, criado por uma
 * versão ANTIGA do servidor — sem as tabelas de entrega e de esqueleto, e com
 * os cadastros de rosto guardados crus, sem o giro da chave. O código novo
 * cria o que falta e gira o que estava cru na primeira vez que sobe. Se essa
 * migração errar, o erro aparece no laboratório: cadeia acusando quebra,
 * painel vazio, ou — o pior — a pessoa cadastrada deixando de ser reconhecida.
 *
 * Testa as duas versões que o laboratório pode ter rodado: a de antes do
 * cadastro no servidor (5001f2d) e a do cadastro sem o giro (fae8c58).
 */
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let falhas = 0, total = 0;
const ok = (nome, cond, det = '') => {
  total++;
  if(cond) console.log('  ok   ' + nome + (det ? '   ' + det : ''));
  else { falhas++; console.log('  FALHA ' + nome + '   ' + det); }
};
const dormir = ms => new Promise(r => setTimeout(r, ms));
const post = (b, rota, c) => fetch(b + rota, { method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(c) });

async function subir(script, porta, banco){
  const p = spawn('uv', ['run', script], { env:{ ...process.env, PORTA:String(porta),
    SQLITE_ARQUIVO: banco, DATABASE_URL:'', CALIBRACAO:'1', QUEM_ESCREVE:'' },
    stdio:'ignore' });
  for(let i = 0; i < 80; i++){
    try{ await fetch(`http://127.0.0.1:${porta}/api/verificar`); return p; }
    catch{ await dormir(500); }
  }
  p.kill(); throw new Error('servidor não subiu: ' + script);
}
async function descer(p){ p.kill(); await dormir(800); }

const rosto = Array.from({length:128}, (_, i) => Math.sin(i * 1.7) * 0.3);

for(const versao of ['5001f2d', 'fae8c58']){
  console.log('\n  -- banco criado pela versão ' + versao + ' --');
  const dir = mkdtempSync(join(tmpdir(), 'banco-antigo-'));
  const banco = join(dir, 'auditix.db');
  const antigo = join(dir, 'servidor.py');
  writeFileSync(antigo, execFileSync('git', ['show', versao + ':servidor.py']));

  /* 1. a versão antiga cria o banco e grava o que o laboratório teria */
  let s = await subir(antigo, 8795, banco);
  const B = 'http://127.0.0.1:8795';
  for(const t of ['queda', 'reconhecido', 'queda'])
    await post(B, '/api/evento', { aluno_id:'corpo-1', tipo_evento:t, localizacao:'sala-12' });
  const temCadastro = versao === 'fae8c58';
  if(temCadastro)
    await post(B, '/api/cadastro', { nome:'Aluno Antigo', descritores:[rosto] });
  const antes = await (await fetch(B + '/api/verificar')).json();
  await descer(s);

  /* 2. o código novo abre o MESMO arquivo */
  s = await subir('servidor.py', 8796, banco);
  const N = 'http://127.0.0.1:8796';
  const v = await (await fetch(N + '/api/verificar')).json();
  ok('a cadeia antiga continua fechando com o código novo',
     v.integra === true && v.total === antes.total, v.total + ' elos');
  const evs = await fetch(N + '/api/eventos?limite=10');
  ok('o painel lê os eventos antigos (as tabelas novas foram criadas)',
     evs.ok && (await evs.json()).length >= 2, 'HTTP ' + evs.status);

  const r = await (await post(N, '/api/evento', { aluno_id:'corpo-2',
    tipo_evento:'queda', localizacao:'sala-12', chave:'migra' + versao,
    poses:[Array(17).fill([0.5, 0.5, 0.9])] })).json();
  ok('a caixa nova grava no banco antigo, com chave e corpo', r.id > 0 && !r.repetido);
  const c = await post(N, '/api/ciente', { evento_id: r.id });
  ok('e o "Estou ciente" também', c.ok, 'HTTP ' + c.status);
  ok('e a cadeia continua fechando depois disso',
     (await (await fetch(N + '/api/verificar')).json()).integra === true);

  if(temCadastro){
    /* A asserção que mais importa: o cadastro estava CRU no banco antigo. A
       migração o gira com a chave. Se girasse errado, o aluno cadastrado antes
       desta versão simplesmente deixaria de ser reconhecido. */
    const q = await (await post(N, '/api/reconhecer', { descritor: rosto })).json();
    ok('o aluno cadastrado na versão antiga CONTINUA sendo reconhecido',
       q.nome === 'Aluno Antigo', JSON.stringify(q));
    const l = await (await fetch(N + '/api/cadastros?descritores=1')).json();
    const f = l.cadastros.find(x => x.nome === 'Aluno Antigo');
    const iguais = f.descritores[0].filter((x, i) => Math.abs(x - rosto[i]) < 1e-9).length;
    ok('e o que está guardado agora está girado, não cru', iguais < 3,
       iguais + ' de 128 números iguais ao original');
    await descer(s);
    /* Subir de novo não pode girar de novo: girar duas vezes perderia o aluno. */
    s = await subir('servidor.py', 8797, banco);
    const q2 = await (await post('http://127.0.0.1:8797', '/api/reconhecer',
                                 { descritor: rosto })).json();
    ok('subindo de novo, ele NÃO gira duas vezes', q2.nome === 'Aluno Antigo');
    await descer(s);

    /* O banco copiado para outro PC SEM a chave. O servidor cria uma chave nova
       e o cadastro vira ruído — isso não pode acontecer calado. */
    const { unlinkSync } = await import('node:fs');
    unlinkSync(join(dir, 'chave-bio.txt'));
    const saida = await new Promise(resolve => {
      const p = spawn('uv', ['run', 'servidor.py'], { env:{ ...process.env,
        PORTA:'8798', SQLITE_ARQUIVO: banco, DATABASE_URL:'', QUEM_ESCREVE:'' } });
      let txt = '';
      p.stdout.on('data', d => txt += d);
      setTimeout(() => { p.kill(); resolve(txt); }, 9000);
    });
    ok('sem o chave-bio.txt, o servidor AVISA que os cadastros ficaram inúteis',
       /ATENCAO: criei uma chave NOVA/.test(saida) && /1 cadastro/.test(saida),
       (saida.match(/\[bio\].*/) || ['(nenhum aviso)'])[0].slice(0, 90));
    s = null;
  }
  if(s) await descer(s);
}

console.log('\n' + (falhas ? falhas + ' de ' + total + ' FALHARAM'
                           : total + ' de ' + total + ' passaram'));
process.exit(falhas ? 1 : 0);
