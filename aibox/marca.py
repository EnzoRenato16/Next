"""O letreiro "AUDITIX IA" que abre o servidor, a sala e a arena.

Sem dependencia nenhuma, de proposito: o servidor do PC importa isto e nao
pode puxar numpy nem OpenCV junto. Cor so em terminal de verdade (e nunca com
NO_COLOR); terminal que nao sabe escrever os blocos recebe a versao em ASCII,
em vez de derrubar a partida por causa de um enfeite.
"""
import os
import sys

_BLOCOS = r"""
 █████╗ ██╗   ██╗██████╗ ██╗████████╗██╗██╗  ██╗    ██╗ █████╗
██╔══██╗██║   ██║██╔══██╗██║╚══██╔══╝██║╚██╗██╔╝    ██║██╔══██╗
███████║██║   ██║██║  ██║██║   ██║   ██║ ╚███╔╝     ██║███████║
██╔══██║██║   ██║██║  ██║██║   ██║   ██║ ██╔██╗     ██║██╔══██║
██║  ██║╚██████╔╝██████╔╝██║   ██║   ██║██╔╝ ██╗    ██║██║  ██║
╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝   ╚═╝   ╚═╝╚═╝  ╚═╝    ╚═╝╚═╝  ╚═╝
"""[1:-1].splitlines()

_ASCII = r"""
    _   _   _ ___ ___ _____ _____  __  ___   _
   /_\ | | | |   \_ _|_   _|_ _\ \/ / |_ _| /_\
  / _ \| |_| | |) | |  | |  | | >  <   | | / _ \
 /_/ \_\\___/|___/___| |_| |___/_/\_\ |___/_/ \_\
"""[1:-1].splitlines()

# Do verde-agua ao verde da marca, uma cor por linha.
_CORES = [(63, 158, 139), (72, 170, 146), (82, 180, 152),
          (95, 191, 160), (110, 200, 168), (128, 210, 178)]


def _com_cor():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")          # liga as cores ANSI no console do Windows
    return True


def letreiro(modulo=""):
    """Imprime o letreiro. `modulo` vai embaixo: "central", "sala", "arena"."""
    cor = _com_cor()
    sub = "central de segurança" + (f"  ·  {modulo}" if modulo else "")
    try:
        linhas = _BLOCOS
        "".join(linhas).encode(sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        linhas = _ASCII
    largura = max(len(x) for x in linhas)
    saida = [""]
    for i, x in enumerate(linhas):
        if cor:
            r, g, b = _CORES[min(i, len(_CORES) - 1)]
            x = f"\033[1;38;2;{r};{g};{b}m{x}\033[0m"
        saida.append("  " + x)
    sub = sub.upper().center(largura)
    saida.append("  " + (f"\033[2m{sub}\033[0m" if cor else sub))
    saida.append("")
    try:
        print("\n".join(saida), flush=True)
    except UnicodeEncodeError:
        print("\n".join("  " + x for x in _ASCII) + "\n", flush=True)


if __name__ == "__main__":
    letreiro(sys.argv[1] if len(sys.argv) > 1 else "")
