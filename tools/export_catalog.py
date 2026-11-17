"""Export source-bound bilingual review data locally; never run/install the game."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from assess_resources import Pak, StringTable, require
from build_locale import ROOT, EXE_SHA, BS_SHA, PDA_SHA, digest
from locale_catalog import load_catalog, bind_sources
from pda_resources import PdaResource


def export(game: Path, locale: str, out: Path) -> None:
    require(out.resolve().is_relative_to((ROOT/'build').resolve()), 'bilingual export must stay in ignored build directory')
    require(not out.exists(), 'choose a new review output')
    require((ROOT/'locales'/locale).resolve().parent==(ROOT/'locales').resolve(), 'invalid locale path')
    require(digest((game/'secondsight.EXE').read_bytes())==EXE_SHA, 'unsupported EXE')
    raw=Pak((game/'pak/arcade/l_103.pak').read_bytes()).member('data/strsspxe.bs')
    require(digest(raw)==BS_SHA, 'unsupported BS')
    table=StringTable(raw)
    pda=None
    for path in sorted((game/'pak').rglob('*.pak')):
        archive=Pak(path.read_bytes())
        if any(e['name']=='data/pdaps_a.raw' for e in archive.entries):
            member=archive.member('data/pdaps_a.raw')
            require(digest(member)==PDA_SHA, 'unsupported PDA')
            pda=PdaResource(member)
            break
    require(pda is not None, 'PDA not found')
    data=bind_sources(load_catalog(ROOT/'locales'/locale),table.strings,{k:s.text for k,s in pda.segments.items() if s.text})
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    require(json.loads(out.read_text(encoding='utf-8'))==data, 'review reopen mismatch')
    print(f"EXPORT PASS: BS={len(data['bs'])}; PDA={len(data['pda'])}; local bilingual review only; game not launched")


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game-root',type=Path,required=True)
    p.add_argument('--locale',default='zh-CN')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();export(a.game_root,a.locale,a.out)
