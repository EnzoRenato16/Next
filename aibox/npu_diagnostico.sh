#!/bin/bash
# Diagnostico da NPU (Hexagon V68) para a versao NPU do Auditix.
#
# SO OLHA, NAO MUDA NADA: nao instala, nao grava fora de ~/auditix-npu, nao
# mexe em ~/auditix nem no .env. Responde as perguntas que decidem o caminho:
#   1. o grupo11 consegue abrir o dispositivo da NPU (/dev/adsprpc-smd ou
#      /dev/fastrpc-*)? Sem isso nada roda na NPU, com nenhum programa.
#   2. o grupo11 consegue LER as bibliotecas do SNPE (/root/lib, /usr/lib)?
#   3. existe snpe-net-run, tflite_runtime, PyGObject (gi), qtimltflite?
#
# Uso, na caixa:   bash ~/auditix-npu/aibox/npu_diagnostico.sh
# Ele grava tudo em ~/auditix-npu/diagnostico.txt (para copiar de volta ao PC).

SAIDA="$HOME/auditix-npu/diagnostico.txt"
mkdir -p "$HOME/auditix-npu"
P=/opt/eduvision/venv/bin/python

{
echo "== quando / quem =="
date; id; uname -a
cat /etc/os-release 2>/dev/null | head -3
cat /sys/devices/soc0/machine 2>/dev/null

echo; echo "== dispositivos da NPU / DSP (permissao) =="
ls -l /dev/adsprpc* /dev/fastrpc* /dev/dma_heap/* /dev/ion /dev/kgsl* 2>&1

echo; echo "== bibliotecas do SNPE / QNN que existem e se da para LER =="
for d in /root/lib /usr/lib /usr/lib64 /usr/lib/aarch64-linux-gnu /usr/local/lib /opt /dsp /usr/lib/dsp /vendor/lib64 /vendor/dsp; do
  ls -d "$d" >/dev/null 2>&1 || continue
  find "$d" -maxdepth 4 \( -iname 'libSNPE*' -o -iname 'libSnpe*' -o -iname 'libQnn*' \
       -o -iname 'libcdsprpc*' -o -iname 'libadsprpc*' -o -iname '*V68*' -o -iname 'libhexagon*' \
       -o -iname 'snpe-net-run' -o -iname 'qnn-net-run' -o -iname 'libtensorflowlite*' \) 2>/dev/null |
  while read -r f; do
    if [ -r "$f" ]; then echo "LE   $f"; else echo "NAO  $f"; fi
  done
done
ls -ld /root /root/lib 2>&1
which snpe-net-run qnn-net-run snpe-platform-validator 2>&1
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
echo "ADSP_LIBRARY_PATH=$ADSP_LIBRARY_PATH"

echo; echo "== versao do SNPE (string dentro da lib) =="
for f in /root/lib/libSNPE.so /usr/lib/libSNPE.so; do
  [ -r "$f" ] && strings "$f" 2>/dev/null | grep -m3 -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' && echo "($f)"
done
# o C API do SNPE 2.x (o que o Python vai chamar por ctypes)
for f in /root/lib/libSNPE.so /usr/lib/libSNPE.so; do
  [ -r "$f" ] && echo "simbolos Snpe_ em $f: $(nm -D "$f" 2>/dev/null | grep -c ' T Snpe_')"
done

echo; echo "== funcoes do C API do SNPE (o que o npu.py chama) =="
for f in /root/lib/libSNPE.so /usr/lib/libSNPE.so; do
  [ -r "$f" ] || continue
  nm -D --defined-only "$f" 2>/dev/null | awk '{print $3}' |
    grep -E '^Snpe_(SNPE_|SNPEBuilder_|ITensor_|TensorMap_|Util_|DlContainer_(Open|Delete)|TensorShape_|StringList_|RuntimeList_|ErrorCode_)' | sort | tr '\n' ' '
  echo; echo "($f)"
done

echo; echo "== Python da caixa: o que ele ja tem =="
$P - <<'PY'
import importlib, platform
print("python", platform.python_version())
for m in ["numpy", "cv2", "onnxruntime", "tflite_runtime", "tensorflow", "gi", "ultralytics", "qai_hub"]:
    try:
        mod = importlib.import_module(m)
        print("TEM ", m, getattr(mod, "__version__", ""))
    except Exception as e:
        print("NAO ", m, type(e).__name__)
try:
    import onnxruntime as ort
    print("onnxruntime providers:", ort.get_available_providers())
except Exception:
    pass
PY

echo; echo "== GStreamer: plugins de ML da Qualcomm =="
gst-inspect-1.0 2>/dev/null | grep -iE 'qtiml|snpe|qnn|tflite' || echo "nenhum"
gst-inspect-1.0 qtimltflite 2>/dev/null | grep -iE -A12 'delegate' | head -30
gst-inspect-1.0 qtimlsnpe 2>/dev/null | grep -iE -A8 'runtime|delegate' | head -20

echo; echo "== teste rapido: o SNPE consegue ABRIR a NPU? =="
# snpe-platform-validator diz se o runtime DSP/HTP esta disponivel. Se nao
# existir, tenta abrir a lib pelo Python (sem rodar modelo nenhum).
if which snpe-platform-validator >/dev/null 2>&1; then
  timeout 30 snpe-platform-validator --runtime dsp 2>&1 | tail -8
fi
$P - <<'PY'
import ctypes, os
for d in ["/root/lib", "/usr/lib"]:
    f = os.path.join(d, "libSNPE.so")
    if not os.path.exists(f):
        continue
    try:
        lib = ctypes.CDLL(f)
        print("abriu", f)
        try:
            lib.Snpe_Util_IsRuntimeAvailable.restype = ctypes.c_int
            # 0 CPU, 1 GPU, 2 DSP(HTP)... (enum Snpe_Runtime_t do SNPE 2.x)
            for nome, cod in [("CPU", 0), ("GPU", 1), ("DSP", 2)]:
                print("  runtime", nome, "disponivel =", lib.Snpe_Util_IsRuntimeAvailable(cod))
        except AttributeError as e:
            print("  sem Snpe_Util_IsRuntimeAvailable:", e)
    except OSError as e:
        print("NAO abriu", f, "->", e)
PY

echo; echo "== carga da caixa agora =="
uptime
ps -eo user,pcpu,comm --sort=-pcpu | head -8
} > "$SAIDA" 2>&1

cat "$SAIDA"
echo
echo "Salvo em $SAIDA"
