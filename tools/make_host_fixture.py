"""Generate only synthetic data for the offline ASI host test (no game assets)."""
from pathlib import Path
import sys
import struct
from PIL import Image
from build_locale import blob,dxt3


def fixture() -> bytes:
    text=struct.pack("<I",850)+blob(b"Synthetic menu")+blob(b"\x1f0000\x1f0001")
    pda=struct.pack("<I",0x188c)+blob(b"Synthetic objective")+blob(b"\x1f0001")
    resources=b"".join(blob(f"textures/localization/page{i}.dds".encode())+blob(dxt3(Image.new("L",(256,256)))) for i in range(6))
    return b"SLP1"+struct.pack("<III",1,1,6)+text+pda+resources


if __name__=="__main__":
    path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(fixture())
    print("FIXTURE PASS: synthetic BS/PDA/atlas data; no game assets")
