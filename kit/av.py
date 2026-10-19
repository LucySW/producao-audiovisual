"""Local audiovisual continuity and review tools. No model calls or network access."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

SKIP = {'.git', '.continuidade', 'node_modules', '__pycache__', '07_CACHE', 'BACKUPS', '.venv'}

def now():
    return datetime.now(timezone.utc).isoformat()

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def hashfile(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

@contextmanager
def lock(folder):
    p = folder / 'scan.lock'
    f = p.open('a+b')
    f.seek(0)
    if p.stat().st_size == 0:
        f.write(b'0'); f.flush()
    f.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError('Scan busy; retry after the active scan')
    try:
        yield
    finally:
        f.close()  # OS releases the lock even if this process crashes.

def event(folder, kind, **fields):
    value = {'at': now(), 'kind': kind, **fields}
    atomic(folder/'events'/f'{time.time_ns()}-{uuid.uuid4().hex}.json', value)
    return value

def inventory(root, config, previous, full=False):
    files, errors = {}, []
    for rel in config['watch']:
        base = (root/rel).resolve()
        if not base.is_relative_to(root):
            raise ValueError('Watch path outside project')
        if not base.exists():
            continue
        paths = [base] if base.is_file() else walk_files(base)
        for p in paths:
            if p.is_symlink() or p.name.startswith('.env') or any(v in SKIP for v in p.relative_to(root).parts):
                continue
            key = p.relative_to(root).as_posix()
            try:
                st = p.stat()
                sig = {'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
                old = previous.get(key, {})
                digest = old.get('sha256') if not full and all(old.get(k)==v for k,v in sig.items()) else hashfile(p)
                end = p.stat()
                if (end.st_size,end.st_mtime_ns)!=(st.st_size,st.st_mtime_ns):
                    raise RuntimeError('file changed during hashing')
                files[key] = {**sig, 'sha256': digest}
            except (OSError, RuntimeError) as exc:
                errors.append({'path':key,'error':str(exc)[:180]})
                if key in previous: files[key] = previous[key]
    return files, errors

def walk_files(base):
    for d, dirs, names in os.walk(base):
        dirs[:] = [v for v in dirs if v not in SKIP and not v.startswith(('DOCUMENTACAO_ANTERIOR','PASSAGEM_IA')) and not (Path(d)/v).is_symlink()]
        for n in names:
            yield Path(d)/n

def delta(before, after):
    return {'added': sorted(after.keys()-before.keys()), 'removed': sorted(before.keys()-after.keys()),
            'changed': sorted(k for k in after.keys() & before.keys() if after[k]['sha256']!=before[k]['sha256'])}

def summarize(root, folder, current, errors):
    checkpoint = read(folder/'checkpoint.json', {})
    baseline = checkpoint.get('files', {})
    changes = delta(baseline, current)
    pending = {}
    for p in sorted((folder/'events').glob('*.json')):
        e = read(p)
        if e['kind']=='begin': pending[e['operation']] = e
        elif e['kind']=='end' and e.get('result')!='unknown': pending.pop(e['operation'],None)
    lines = ['# Retomada automática', '', 'Gerado: '+now(),
             'Checkpoint humano/agente: '+checkpoint.get('at','nenhum'),
             'Etapa: '+checkpoint.get('stage','não definida'),
             'Último resumo: '+checkpoint.get('summary','não registrado'),
             'Próxima ação: '+checkpoint.get('next','consultar estado editorial'), '',
             '## Mudanças desde o checkpoint (não equivalem a aprovação)']
    for k,values in changes.items():
        lines.append(f'- {k}: {len(values)}')
        lines.extend('  - '+v for v in values[:15])
        if len(values)>15:lines.append('  - Demais caminhos em delta.json')
    lines += ['', f'## Operações sem fechamento: {len(pending)}']
    for e in list(pending.values())[-10:]:
        lines.append(f"- {e['operation']}: {e.get('summary',e.get('tool','operação'))}; verificar antes de repetir")
    lines += ['',f'Erros de leitura: {len(errors)}; ver delta.json.',
              'Somente arquivos salvos são observáveis. Ausência de mudança não prova ausência de ação externa.',
              'Arquivos removidos são relatados; esta ferramenta não apaga mídia.']
    atomic(folder/'delta.json', {'at':now(),'changes':changes,'read_errors':errors,'pending':list(pending.values())})
    atomic(folder/'RETOMAR.md','\n'.join(lines)+'\n')
    return changes

def scan(root, full=False):
    folder=root/'.continuidade'
    config=read(folder/'config.json')
    if not config:raise ValueError('Run init first')
    with lock(folder):
        old=read(folder/'observed.json',{})
        current,errors=inventory(root,config,old,full)
        diff=delta(old,current)
        if any(diff.values()) or errors:event(folder,'files',changes=diff,read_errors=errors)
        atomic(folder/'observed.json',current)
        changes=summarize(root,folder,current,errors)
    return current,errors,changes

def init(root, watches):
    folder=root/'.continuidade'
    if (folder/'config.json').exists():raise ValueError('Already initialized; preserve existing configuration')
    root.mkdir(parents=True,exist_ok=True)
    folder.mkdir(exist_ok=True)
    atomic(folder/'config.json',{'version':1,'watch':watches or ['docs','assets','audio','projects','exports','AGENTS.md','CLAUDE.md','BRIEFING_TECNICO.md']})
    shutil.copy2(__file__,folder/'av.py')
    (folder/'events').mkdir(exist_ok=True)
    current,errors,_=scan(root)
    if errors:raise RuntimeError('Initial scan incomplete; inspect delta.json')
    atomic(folder/'checkpoint.json',{'at':now(),'stage':'entrada','summary':'Inventário inicial; nenhum conteúdo aprovado automaticamente','next':'preencher briefing técnico e verificar ferramentas','files':current})
    scan(root)

def hooks(root):
    folder=root/'.continuidade'
    if not (folder/'config.json').exists():raise ValueError('Run init first')
    path=root/'.claude/settings.local.json'
    settings=read(path,{})
    command=f'"{Path(sys.executable).as_posix()}" "{(folder/"av.py").as_posix()}" --project "{root.as_posix()}" hook'
    hookmap=settings.setdefault('hooks',{})
    for name in ('SessionStart','PreToolUse','PostToolUse','PostToolUseFailure','Stop'):
        items=hookmap.setdefault(name,[])
        if not any(command==h.get('command') for x in items for h in x.get('hooks',[])):
            items.append({'hooks':[{'type':'command','command':command,'timeout':30}]})
    if path.exists():shutil.copy2(path,folder/f'settings-backup-{time.time_ns()}.json')
    atomic(path,settings)
    instructions='\n<!-- audiovisual-continuity -->\nAntes de agir, leia `.continuidade/RETOMAR.md` e o estado editorial vigente. Antes de operação externa/paga ou edição relevante, use `.continuidade/av.py begin`; após verificação use `end`. Faça `checkpoint` a cada unidade concluída, sem esperar o fim da sessão. Um evento de ferramenta concluída não é aprovação artística. Consulte o método em docs/producao-audiovisual/CONTINUIDADE.md quando disponível.\n'
    agents=root/'AGENTS.md'
    text=agents.read_text(encoding='utf-8') if agents.exists() else '# Instruções do projeto\n'
    if 'audiovisual-continuity' not in text:
        if agents.exists():shutil.copy2(agents,folder/f'agents-backup-{time.time_ns()}.md')
        atomic(agents,text+instructions)
    claude=root/'CLAUDE.md'
    text=claude.read_text(encoding='utf-8') if claude.exists() else '# Continuidade local\n'
    if '@AGENTS.md' not in text:
        if claude.exists():shutil.copy2(claude,folder/f'claude-backup-{time.time_ns()}.md')
        atomic(claude,text+'\n@AGENTS.md\n')

def hook(root):
    data=json.load(sys.stdin)
    folder=root/'.continuidade'
    name=data.get('hook_event_name','unknown')
    # Deliberately discard prompts, command arguments, tool results, transcript and credentials.
    op='hook:'+str(data.get('session_id',''))+':'+str(data.get('tool_use_id',''))
    if name=='PreToolUse':event(folder,'begin',operation=op,tool=data.get('tool_name'),summary='Ferramenta '+str(data.get('tool_name')))
    elif name in ('PostToolUse','PostToolUseFailure'):
        event(folder,'end',operation=op,result='tool_returned' if name=='PostToolUse' else 'tool_failed')
    if name!='PreToolUse':
        try:scan(root)
        except RuntimeError as exc:
            event(folder,'scan_deferred',reason=str(exc))
        if name=='SessionStart':print((folder/'RETOMAR.md').read_text(encoding='utf-8'))

def grid(source, out, count, ffmpeg, ffprobe):
    from PIL import Image, ImageDraw
    info=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_entries','format=duration','-of','json',str(source)],text=True))
    duration=float(info['format']['duration'])
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration')
    count=count or 12*max(1,math.ceil(duration/60))
    if count<1 or count>240:raise ValueError('Use 1..240 frames or divide video into sections')
    if out.exists():raise ValueError('Output already exists; use a new version')
    out.mkdir(parents=True)
    cells=[]
    for i in range(count):
        t=(i+.5)*duration/count
        name=f'frame_{i+1:03d}.jpg'
        subprocess.run([ffmpeg,'-nostdin','-v','error','-ss',str(t),'-i',str(source),'-frames:v','1','-vf','scale=384:216:force_original_aspect_ratio=decrease,pad=384:216:(ow-iw)/2:(oh-ih)/2','-q:v','3',str(out/name)],check=True)
        cells.append({'index':i+1,'requested_seconds':round(t,6),'path':name,'page':i//12+1})
    for start in range(0,count,12):
        sheet=Image.new('RGB',(1152,976),(23,23,23));draw=ImageDraw.Draw(sheet)
        for j,c in enumerate(cells[start:start+12]):
            x=(j%3)*384;y=(j//3)*244
            with Image.open(out/c['path']) as im:sheet.paste(im,(x,y+28))
            draw.text((x+8,y+7),f"#{c['index']:03d} | {c['requested_seconds']:.3f}s",fill='white')
        sheet.save(out/f'grid_{start//12+1:02d}.jpg',quality=90)
    atomic(out/'index.json',{'source':str(source.resolve()),'source_sha256':hashfile(source),'duration':duration,'sampling':'uniform midpoints; requested timestamps, not exact decoded PTS; cannot prove motion/audio quality','frames':cells})
    return {'frames':count,'pages':math.ceil(count/12),'output':str(out)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--project',type=Path,default=Path.cwd())
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('init');a.add_argument('--watch',action='append',default=[])
    a=sub.add_parser('scan');a.add_argument('--full',action='store_true')
    sub.add_parser('status');sub.add_parser('install-claude-hooks');sub.add_parser('hook')
    a=sub.add_parser('watch');a.add_argument('--interval',type=int,default=30)
    a=sub.add_parser('begin');a.add_argument('--summary',required=True);a.add_argument('--stage',required=True)
    a=sub.add_parser('end');a.add_argument('--operation',required=True);a.add_argument('--result',required=True,choices=['verified','failed','unknown']);a.add_argument('--evidence',required=True)
    a=sub.add_parser('checkpoint');a.add_argument('--stage',required=True);a.add_argument('--summary',required=True);a.add_argument('--next',required=True)
    a=sub.add_parser('grid');a.add_argument('source',type=Path);a.add_argument('--out',type=Path,required=True);a.add_argument('--frames',type=int);a.add_argument('--ffmpeg',default='ffmpeg');a.add_argument('--ffprobe',default='ffprobe')
    args=p.parse_args();root=args.project.resolve();folder=root/'.continuidade'
    if args.cmd=='init':init(root,args.watch)
    elif args.cmd=='install-claude-hooks':hooks(root)
    elif args.cmd=='hook':hook(root)
    elif args.cmd=='grid':print(json.dumps(grid(args.source,args.out,args.frames,args.ffmpeg,args.ffprobe)))
    elif args.cmd=='watch':
        atomic(folder/'watcher.json',{'pid':os.getpid(),'started':now(),'interval':max(5,args.interval)})
        while True:
            try:scan(root)
            except Exception as exc:event(folder,'watch_error',message=str(exc)[:200])
            time.sleep(max(5,args.interval))
    elif args.cmd=='begin':
        op=uuid.uuid4().hex;event(folder,'begin',operation=op,summary=args.summary,stage=args.stage);scan(root);print(op)
    elif args.cmd=='end':event(folder,'end',operation=args.operation,result=args.result,evidence=args.evidence);scan(root)
    elif args.cmd=='checkpoint':
        current,errors,_=scan(root)
        if errors:raise RuntimeError('Do not checkpoint an incomplete scan')
        state={'at':now(),'stage':args.stage,'summary':args.summary,'next':args.next}
        atomic(folder/'checkpoint.json',{**state,'files':current});event(folder,'checkpoint',**state);scan(root)
    else:
        scan(root,getattr(args,'full',False))
        if args.cmd=='status':print((folder/'RETOMAR.md').read_text(encoding='utf-8'))

if __name__=='__main__':main()
