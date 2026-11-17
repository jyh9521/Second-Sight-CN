"""Generate only synthetic data for the offline ASI host test (no game assets)."""
from pathlib import Path
import argparse
import struct
from PIL import Image
from build_locale import blob,dxt3,pack_runtime
from ui_textures import dxt3_solid


def fixture(format: str = 'SLP2') -> bytes:
    if format not in ('SLP2','SLP3'):
        raise ValueError('unsupported synthetic pack format')
    text=struct.pack("<I",850)+blob(b"Synthetic menu")+blob(b"\x1f0000\x1f0001")
    pda=struct.pack("<I",0x188c)+blob(b"Synthetic objective")+blob(b"\x1f0001")
    resources=[(f"textures/localization/page{i}.dds",dxt3(Image.new("L",(512,512)))) for i in range(6)]
    resources.append(('textures/misc/nse_tv/loading.dds',dxt3_solid(Image.new('L',(256,64)),65535)))
    executable=[struct.pack('<I',i)+blob(s)+blob(b'\x1f0000') for i,s in [(1,b'Quick scroll'),(2,b'Button inoperative')]]
    if format=='SLP3':
        return pack_runtime([text],[pda],executable,resources,
                            {850:[b'Synthetic menu variant A',b'Synthetic menu variant B']})
    return (b"SLP2"+struct.pack("<IIII",1,1,7,2)+text+pda+b''.join(executable)+
            b''.join(blob(name.encode('ascii'))+blob(payload) for name,payload in resources))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path)
    parser.add_argument('--format',choices=('SLP2','SLP3'),default='SLP2')
    args=parser.parse_args()
    args.path.parent.mkdir(parents=True,exist_ok=True)
    args.path.write_bytes(fixture(args.format))
    print(f"FIXTURE PASS: format={args.format}; synthetic BS/PDA/atlas data; aliases={2 if args.format=='SLP3' else 0}; no game assets")
