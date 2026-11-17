"""Read recorded Windows x86 minidumps; never attach to or launch a process.

Subset: module, exception, MemoryList and Memory64List streams. Unknown streams
remain unparsed. Thread contexts must be x86/WOW64; no implicit x64 decoding.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct


class Minidump:
    def __init__(self,path: Path):
        self.path=path.resolve()
        self.data=path.read_bytes()
        self.sha256=hashlib.sha256(self.data).hexdigest()
        if self.data[:4]!=b"MDMP": raise ValueError("not a Windows minidump")
        self.streams={}
        count,directory=self.unpack("<II",8)
        self.slice(directory,count*12)
        for index in range(count):
            kind,size,offset=self.unpack("<III",directory+index*12)
            self.slice(offset,size)
            if kind==0: continue # UnusedStream entries may repeat in Windows dumps.
            if kind in self.streams: raise ValueError("duplicate minidump stream")
            self.streams[kind]=(offset,size)
        self.modules=[]
        if 4 in self.streams:
            start,size=self.streams[4]
            count=self.unpack("<I",start)[0]
            if 4+108*count>size: raise ValueError("truncated module list")
            for index in range(count):
                row=start+4+108*index
                base,length,checksum,timestamp,name_rva=self.unpack("<QIIII",row)
                name_length=self.unpack("<I",name_rva)[0]
                name=self.slice(name_rva+4,name_length).decode("utf-16le")
                self.modules.append(dict(name=name,base=base,size=length,timestamp=timestamp))
        self.memory=[]
        if 9 in self.streams:
            start,size=self.streams[9]
            count,file_offset=self.unpack("<QQ",start)
            if 16+16*count>size: raise ValueError("truncated Memory64 list")
            for index in range(count):
                address,length=self.unpack("<QQ",start+16+index*16)
                self.slice(file_offset,length)
                self.memory.append((address,length,file_offset));file_offset+=length
        elif 5 in self.streams:
            start,size=self.streams[5]
            count=self.unpack("<I",start)[0]
            if 4+16*count>size: raise ValueError("truncated MemoryList")
            for index in range(count):
                address,length,file_offset=self.unpack("<QII",start+4+index*16)
                self.slice(file_offset,length)
                self.memory.append((address,length,file_offset))
        self.memory.sort()

    def slice(self,offset: int,size: int) -> bytes:
        if offset<0 or size<0 or offset+size>len(self.data): raise ValueError("minidump file range outside input")
        return self.data[offset:offset+size]

    def unpack(self,fmt: str,offset: int) -> tuple:
        return struct.unpack(fmt,self.slice(offset,struct.calcsize(fmt)))

    def read(self,address: int,size: int) -> bytes:
        result=bytearray()
        while size:
            match=next((row for row in self.memory if row[0]<=address<row[0]+row[1]),None)
            if not match: raise ValueError(f"memory not recorded: {address:#x}")
            start,length,offset=match
            take=min(size,start+length-address)
            result.extend(self.slice(offset+address-start,take))
            size-=take;address+=take
        return bytes(result)

    def containing_module(self,address: int) -> dict | None:
        return next((m for m in self.modules if m["base"]<=address<m["base"]+m["size"]),None)

    def exception(self) -> dict:
        start,size=self.streams[6]
        if size<168: raise ValueError("truncated exception stream")
        thread=self.unpack("<I",start)[0]
        code=self.unpack("<I",start+8)[0]
        address=self.unpack("<Q",start+24)[0]
        count=self.unpack("<I",start+32)[0]
        if count>15: raise ValueError("invalid exception parameter count")
        parameters=list(self.unpack("<"+"Q"*count,start+40))
        context_size,context_offset=self.unpack("<II",start+160)
        context=self.slice(context_offset,context_size)
        flags=struct.unpack_from("<I",context)[0] if context_size>=4 else 0
        if not flags&0x10000 or context_size<204: raise ValueError("only recorded x86/WOW64 contexts supported")
        positions=dict(edi=156,esi=160,ebx=164,edx=168,ecx=172,eax=176,ebp=180,eip=184,eflags=192,esp=196)
        registers={name:struct.unpack_from("<I",context,offset)[0] for name,offset in positions.items()}
        module=self.containing_module(address)
        return dict(thread=thread,code=code,address=address,parameters=parameters,
                    registers=registers,module=module,rva=address-module["base"] if module else None)


if __name__=="__main__":
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    dump=Minidump(args.dump)
    report=dict(path=str(dump.path),sha256=dump.sha256,exception=dump.exception(),
                modules=dump.modules,memory_ranges=len(dump.memory),
                limitations=["recorded crash only; no live process access","missing recorded memory remains unknown"])
    text=json.dumps(report,indent=2)
    if args.out: args.out.write_text(text+"\n",encoding="utf-8",newline="\n")
    error=report['exception'];module=Path(error['module']['name']).name if error['module'] else 'unknown'
    print(f"RECORDED CRASH: code={error['code']:#x}; module={module}; RVA={error['rva']}; read={error['parameters']}; no target execution")
