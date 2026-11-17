"""Generate only synthetic data for the offline ASI host test (no game assets)."""
from pathlib import Path
import sys
import struct
from PIL import Image
from build_locale import blob,dxt3
from ui_textures import dxt3_solid


def fixture() -> bytes:
    text=struct.pack("<I",850)+blob(b"Synthetic menu")+blob(b"\x1f0000\x1f0001")
    pda=struct.pack("<I",0x188c)+blob(b"Synthetic objective")+blob(b"\x1f0001")
    resources=b"".join(blob(f"textures/localization/page{i}.dds".encode())+blob(dxt3(Image.new("L",(512,512)))) for i in range(6))
    resources+=blob(b'textures/misc/nse_tv/loading.dds')+blob(dxt3_solid(Image.new('L',(256,64)),65535))
    executable=b''.join(struct.pack('<I',i)+blob(s)+blob(b'\x1f0000') for i,s in [(1,b'Quick scroll'),(2,b'Button inoperative')])
    return b"SLP2"+struct.pack("<IIII",1,1,7,2)+text+pda+executable+resources


if __name__=="__main__":
    path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(fixture())
    print("FIXTURE PASS: synthetic BS/PDA/atlas data; no game assets")
