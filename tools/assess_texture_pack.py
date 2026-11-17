"""Read-only inventory of a loose DDS texture pack and native proxy metadata.

Does not load DLLs, install files, call graphics APIs, or launch a game.
DDS checks cover ordinary 2D DXT1/3/5 mip chains, not all DDS variants.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import struct


def require(condition: bool,message: str) -> None:
    if not condition: raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dds_metadata(data: bytes) -> dict:
    require(len(data)>=128 and data[:4]==b"DDS ","invalid DDS magic/header")
    u=lambda offset:struct.unpack_from("<I",data,offset)[0]
    require(u(4)==124 and u(76)==32,"invalid DDS header sizes")
    height,width,depth,mips=u(12),u(16),u(24),u(28)
    require(0<width<=32768 and 0<height<=32768,"DDS dimensions outside inspection bounds")
    fmt=data[84:88].decode("ascii",errors="replace")
    require(fmt in ("DXT1","DXT3","DXT5") and u(80)&4,"unsupported DDS pixel format")
    require(depth in (0,1) and not u(112)&0xFE0200,"only ordinary 2D DDS supported")
    levels=max(mips,1)
    require(levels<=max(width,height).bit_length(),"invalid mip count")
    w,h=width,height
    payload=0
    for _ in range(levels):
        payload+=max(1,(w+3)//4)*max(1,(h+3)//4)*(8 if fmt=="DXT1" else 16)
        w,h=max(1,w//2),max(1,h//2)
    require(len(data)>=128+payload,"truncated mip chain")
    return dict(width=width,height=height,format=fmt,mip_count=levels,
                mip_payload_bytes=payload,trailing_bytes=len(data)-128-payload,
                decoded_top_level_rgba_bytes=width*height*4)


def inspect(root: Path,out: Path,decode: bool=False) -> dict:
    import pefile
    root,out=root.resolve(),out.resolve()
    require(root.is_dir(),"texture pack directory missing")
    require(not out.is_relative_to(root),"report output must be outside supplied pack")
    files=sorted(p for p in root.rglob("*") if p.is_file())
    require(bool(files),"empty pack")
    inventory=[];errors=[];textures=[];native=[]
    for path in files:
        before=path.stat()
        raw=path.read_bytes()
        after=path.stat()
        require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),f"source changed during read: {path}")
        row=dict(path=path.relative_to(root).as_posix(),size=len(raw),sha256=sha(raw))
        inventory.append(row)
        if path.suffix.lower()==".dds":
            try:
                info=dds_metadata(raw)
                if decode:
                    from PIL import Image
                    with Image.open(io.BytesIO(raw)) as image:
                        image.load()
                        require(image.size==(info["width"],info["height"]),"decoded dimensions differ")
                textures.append(dict(row,**info))
            except Exception as error:
                errors.append(dict(path=row["path"],error=str(error)))
        elif path.suffix.lower() in (".dll",".asi",".exe"):
            pe=pefile.PE(data=raw)
            native.append(dict(row,machine=hex(pe.FILE_HEADER.Machine),image_base=hex(pe.OPTIONAL_HEADER.ImageBase),
                               entry_rva=hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint),
                               exports=[(s.name or b"").decode("ascii",errors="replace") for s in getattr(getattr(pe,"DIRECTORY_ENTRY_EXPORT",None),"symbols",[])],
                               imports=[entry.dll.decode("ascii",errors="replace") for entry in getattr(pe,"DIRECTORY_ENTRY_IMPORT",[])],
                               version_resource_present=bool(getattr(pe,"VS_VERSIONINFO",None))))
    report=dict(schema=1,mode="read-only; no DLL execution; no game launch",root=str(root),
                total_files=len(files),total_bytes=sum(r["size"] for r in inventory),dds_files=len(textures),
                formats=dict(Counter(r["format"] for r in textures)),
                dimensions=dict(Counter(f"{r['width']}x{r['height']}" for r in textures)),
                mip_counts=dict(Counter(r["mip_count"] for r in textures)),
                trailing_bytes=dict(Counter(r["trailing_bytes"] for r in textures)),
                matching_name_count=sum(bool(re.fullmatch(r"Remaster_Textures/tex_[0-9A-F]{8}\.dds",r["path"])) for r in textures),
                unique_texture_sha256=len({r["sha256"] for r in textures}),
                total_mip_payload_bytes=sum(r["mip_payload_bytes"] for r in textures),
                total_decoded_top_level_rgba_bytes=sum(r["decoded_top_level_rgba_bytes"] for r in textures),
                pixel_decode=decode,errors=errors,native=native,
                inventory_sha256=sha(json.dumps(inventory,sort_keys=True,separators=(",",":")).encode()),
                limitations=["DDS serialization/key compatibility is not inferred from file names or raw DDS hashes",
                             "Sum of texture bytes is not observed VRAM usage or frame time",
                             "No runtime hook compatibility or artistic acceptance is implied"])
    out.mkdir(parents=True,exist_ok=True)
    (out/"inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    (out/"dds.json").write_text(json.dumps(textures,indent=2)+"\n",encoding="utf-8")
    (out/"summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    require(not errors,f"DDS errors={len(errors)}; inspect summary.json")
    print(f"TEXTURE PACK PASS: files={len(files)}; DDS={len(textures)}; bytes={report['total_bytes']}; decoded={decode}; errors=0; no game launched")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--decode",action="store_true")
    args=parser.parse_args();inspect(args.pack_root,args.out,args.decode)
