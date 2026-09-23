/* Vídeo fluido (--fluido) — roda com:  node testes/fluido.mjs
 *
 * Não precisa do servidor. Quem testa é o Python: testes/fluido_lado.py.
 */
import { spawnSync } from 'node:child_process';
const py = spawnSync('python3', ['testes/fluido_lado.py'], { encoding:'utf-8' });
process.stdout.write(py.stdout || '');
if(py.stderr) process.stderr.write(py.stderr);
console.log(py.status === 0 ? '\ntodos passaram' : '\nFALHOU');
process.exit(py.status === 0 ? 0 : 1);
