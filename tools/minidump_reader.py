"""Read recorded Windows minidumps; never attach to or launch a process.

Subset: module, exception, thread, system, MemoryList and Memory64List streams.
Unknown streams remain unparsed. WOW64 TLS recovery is explicitly requested;
the version-sensitive layout is not silently applied to native AMD64 threads.
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

    @staticmethod
    def x86_context(context: bytes) -> dict:
        if len(context)<204: raise ValueError("truncated x86 context")
        flags=struct.unpack_from("<I",context)[0]
        if flags&0xff0000!=0x10000 or flags&3!=3:
            raise ValueError("x86 control/integer context not recorded")
        positions=dict(edi=156,esi=160,ebx=164,edx=168,ecx=172,eax=176,ebp=180,eip=184,eflags=192,esp=196)
        return dict(architecture="x86",flags=flags,
                    registers={name:struct.unpack_from("<I",context,offset)[0] for name,offset in positions.items()})

    def threads(self,*,wow64: bool=False) -> list[dict]:
        """Decode recorded contexts, not a symbolized stack unwind.

        Optional AMD64-TEB TLS[1]+4 recovery follows the documented WOW64
        layout also used by LLDB. Missing or changed layouts remain unknown.
        https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-wow64_context
        https://lldb.llvm.org/cpp_reference/MinidumpParser_8cpp_source.html
        """
        if 3 not in self.streams: return []
        start,size=self.streams[3]
        if size<4: raise ValueError("truncated thread list")
        count=self.unpack("<I",start)[0]
        if 4+48*count>size: raise ValueError("truncated thread list")
        architecture=None
        if 7 in self.streams:
            system,system_size=self.streams[7]
            if system_size<2: raise ValueError("truncated system info")
            architecture=self.unpack("<H",system)[0]
        rows=[];seen=set()
        for index in range(count):
            tid,suspend,priority_class,priority,teb,stack,stack_size,stack_rva,context_size,context_rva=self.unpack(
                "<IIIIQQIIII",start+4+index*48)
            if tid in seen: raise ValueError("duplicate thread id")
            seen.add(tid)
            raw=self.slice(context_rva,context_size)
            self.slice(stack_rva,stack_size)
            row=dict(id=tid,teb=teb,suspend_count=suspend,priority_class=priority_class,priority=priority,
                     stack=dict(address=stack,size=stack_size,file_offset=stack_rva),
                     context_file_offset=context_rva,context_size=context_size,
                     context=None,context_error=None,wow64_context=None,wow64_error=None)
            try:
                if architecture==0:
                    row['context']=self.x86_context(raw)
                elif architecture==9:
                    if len(raw)<256: raise ValueError("truncated amd64 context")
                    flags=struct.unpack_from('<I',raw,48)[0]
                    if flags&0xff0000!=0x100000 or flags&3!=3:
                        raise ValueError("amd64 control/integer context not recorded")
                    names=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+[f'r{i}' for i in range(8,16)]+['rip']
                    row['context']=dict(architecture='amd64',flags=flags,
                        registers={name:struct.unpack_from('<Q',raw,120+i*8)[0] for i,name in enumerate(names)})
                    if wow64:
                        try:
                            slot=struct.unpack('<Q',self.read(teb+0x1488,8))[0]
                            if slot==0: raise ValueError('WOW64 TLS slot is null')
                            context=self.x86_context(self.read(slot+4,716))
                            context.update(recorded_address=slot+4,tls_slot_address=teb+0x1488,
                                           method='explicit AMD64 TEB TLS[1]+4; version-sensitive')
                            row['wow64_context']=context
                        except ValueError as error:
                            row['wow64_error']=str(error)
                else:
                    raise ValueError(f'unsupported or missing system architecture: {architecture}')
            except ValueError as error:
                row['context_error']=str(error)
            rows.append(row)
        return rows

    def exception(self) -> dict | None:
        if 6 not in self.streams: return None
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
        registers=None;context_error=None;context_architecture=None
        try:
            if len(context)>=4 and struct.unpack_from('<I',context)[0]&0xff0000==0x10000:
                registers=self.x86_context(context)['registers'];context_architecture='x86'
            elif len(context)>=256 and struct.unpack_from('<I',context,48)[0]&0xff0000==0x100000:
                flags=struct.unpack_from('<I',context,48)[0]
                if flags&3!=3: raise ValueError('amd64 control/integer context not recorded')
                names=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+[f'r{i}' for i in range(8,16)]+['rip']
                registers={name:struct.unpack_from('<Q',context,120+i*8)[0] for i,name in enumerate(names)}
                context_architecture='amd64'
            else: raise ValueError('unsupported or truncated exception context')
        except ValueError as error:
            context_error=str(error)
        module=self.containing_module(address)
        return dict(thread=thread,code=code,address=address,parameters=parameters,
                    registers=registers,module=module,rva=address-module["base"] if module else None,
                    context_architecture=context_architecture,context_error=context_error)


if __name__=="__main__":
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--wow64",action="store_true",help="explicitly recover x86 contexts from recorded AMD64 TEB TLS slots")
    args=parser.parse_args()
    dump=Minidump(args.dump)
    report=dict(path=str(dump.path),sha256=dump.sha256,exception=dump.exception(),threads=dump.threads(wow64=args.wow64),
                modules=dump.modules,memory_ranges=len(dump.memory),
                limitations=["recorded snapshot only; no live process access", "not a symbolized stack unwind",
                             "missing recorded memory remains unknown", "one snapshot does not prove a deadlock or its cause"])
    text=json.dumps(report,indent=2)
    if args.out: args.out.write_text(text+"\n",encoding="utf-8",newline="\n")
    error=report['exception']
    if error:
        module=Path(error['module']['name']).name if error['module'] else 'unknown'
        print(f"RECORDED CRASH: code={error['code']:#x}; module={module}; RVA={error['rva']}; read={error['parameters']}; no target execution")
    else:
        x86=sum(bool(row['wow64_context'] or (row['context'] and row['context']['architecture']=='x86')) for row in report['threads'])
        print(f"RECORDED DUMP: exception=absent; threads={len(report['threads'])}; x86_contexts={x86}; memory_ranges={len(dump.memory)}; no target execution")
