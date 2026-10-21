# VERSAO NPU: deixa o SNPE do pacote (npu-lib/) achavel. Lido por arena.sh e
# ir.sh com "source". A biblioteca do braco (libSNPE.so) vem do
# LD_LIBRARY_PATH, que so vale se estiver pronto ANTES do python abrir; a
# parte que roda DENTRO da NPU (dsp/*Skel.so) vem do ADSP_LIBRARY_PATH.
# Sem a pasta npu-lib, nada muda e tudo roda na CPU.
_NPU_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/npu-lib"
if [ -f "$_NPU_LIB/libSNPE.so" ]; then
  export SNPE_LIB="$_NPU_LIB/libSNPE.so"
  export LD_LIBRARY_PATH="$_NPU_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export ADSP_LIBRARY_PATH="$_NPU_LIB/dsp;/usr/lib/rfsa/adsp;/dsp"
  echo "  NPU: pacote $(cat "$_NPU_LIB/VERSAO" 2>/dev/null) em $_NPU_LIB"
else
  echo "  NPU: sem npu-lib/ (pc npu no PC), tudo na CPU"
fi
