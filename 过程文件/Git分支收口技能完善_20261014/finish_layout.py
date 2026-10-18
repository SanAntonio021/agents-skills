from pathlib import Path
p=Path(r'D:\BaiduSyncdisk\.agents\skills\git-branch-consolidation\scripts\git_layout.py')
p.write_text('''"""Sealed Git layout/configuration for schema-4 recovery (no hooks executed)."""
from __future__ import annotations
import hashlib,json,os,re,subprocess
from pathlib import Path
from recovery_fs import canonical_path, canonical_rel, current_entry, io_path, path_within, sha256_file, inventory_tree

def run(repo,*args,check=True):
 p=subprocess.run(['git','--no-optional-locks','-c','core.longpaths=true','-C',str(repo),*map(str,args)],capture_output=True)
 if check and p.returncode:raise RuntimeError('Git layout command failed: '+p.stderr.decode('utf-8','replace'))
 return p

def text(repo,*args,check=True):return run(repo,*args,check=check).stdout.decode('utf-8','surrogateescape').strip()

def discover_worktrees(repo,raw_records=None):
 if raw_records is None:
  raw_records=run(repo,'worktree','list','--porcelain','-z').stdout
 if isinstance(raw_records,bytes):
  records=[]
  for block in raw_records.rstrip(b'\\0').split(b'\\0\\0'):
   entry={}
   for field in block.split(b'\\0'):
    key,_,value=field.decode('utf-8','surrogateescape').partition(' ')
    if key:entry[key]=value or True
   if 'worktree' in entry:records.append(entry)
 else:records=[dict(x) for x in raw_records]
 result=[]
 for i,entry in enumerate(records):
  # The first porcelain path may be separate-git-dir metadata, not the checkout.
  candidate=Path(repo) if i==0 else Path(entry['worktree'])
  if not candidate.is_dir():raise RuntimeError('Registered worktree is missing: '+str(candidate))
  top=Path(text(candidate,'rev-parse','--show-toplevel')).resolve()
  admin=Path(text(top,'rev-parse','--absolute-git-dir')).resolve()
  common=Path(text(top,'rev-parse','--path-format=absolute','--git-common-dir')).resolve()
  ptr=top/'.git';kind=current_entry(ptr,'.git')
  record=dict(entry,worktree=str(top),listed_worktree=str(entry['worktree']),git_dir=str(admin),common_dir=str(common),admin_dir=str(admin),role='main' if canonical_path(admin)==canonical_path(common) else 'linked',index=i,git_pointer_kind=kind['kind'] if kind else 'missing',git_pointer_sha256=sha256_file(ptr) if ptr.is_file() else None)
  result.append(record)
 return result

def _effective(repo):
 result=[]
 for field in run(repo,'config','--includes','--null','--list').stdout.split(b'\\0'):
  if field:
   key,_,value=field.decode('utf-8','surrogateescape').partition('\\n');result.append([key,value])
 return result

def inspect_layout(repo,worktrees=None):
 records=discover_worktrees(repo,worktrees);files={};items=[]
 def include(path,label):
  path=io_path(path)
  if not path.exists():return
  if not path.is_file():raise RuntimeError('Configuration dependency is not a regular file: '+str(path))
  entry=current_entry(path,label)
  if entry['kind']!='file':raise RuntimeError('Configuration link requires separate recovery: '+str(path))
  files[label]=dict(entry,source=str(path))
 for i,wt in enumerate(records):
  root=Path(wt['worktree']);admin=Path(wt['admin_dir']);common=Path(wt['common_dir'])
  include(common/'config',f'common/config')
  include(admin/'config.worktree',f'worktrees/{i:03d}/config.worktree')
  include(admin/'info/exclude',f'worktrees/{i:03d}/info-exclude')
  include(common/'info/exclude','common/info-exclude')
  if (root/'.git').is_file():include(root/'.git',f'worktrees/{i:03d}/git-pointer')
  for field in run(root,'config','--includes','--show-origin','--null','--list').stdout.split(b'\\0')[::2]:
   if field.startswith(b'file:'):
    name=field[5:].decode('utf-8','surrogateescape');source=Path(name).expanduser()
    if not source.is_absolute():source=root/source
    label='dependencies/'+hashlib.sha256(canonical_path(source).encode()).hexdigest()+'.config';include(source,label)
  exclude=text(root,'config','--path','--get','core.excludesfile',check=False)
  if not exclude:
   exclude=str(Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'git/ignore')
  exclusion=Path(exclude).expanduser()
  if not exclusion.is_absolute():exclusion=root/exclusion
  include(exclusion,f'worktrees/{i:03d}/global-exclude')
  hooks=text(root,'rev-parse','--git-path','hooks')
  h=Path(hooks)
  if not h.is_absolute():h=root/h
  if h.exists():
   for entry in inventory_tree(h,f'worktrees/{i:03d}/hooks'):
    relative=Path(entry['path']).relative_to(f'worktrees/{i:03d}/hooks')
    if entry['kind'] not in ('directory','file'):raise RuntimeError('Hook link requires separate recovery: '+entry['path'])
    if entry['kind']=='file':include(h/relative,entry['path'])
  items.append({'index':i,'layout':wt,'effective':_effective(root)})
 return {'schemaVersion':1,'repo':str(Path(repo).resolve()),'worktrees':items,'files':files}

def capture_layout(repo,worktrees,output):
 output=io_path(output);snapshot=inspect_layout(repo,worktrees)
 output.mkdir(parents=True,exist_ok=False)
 for name,entry in snapshot['files'].items():
  src=io_path(entry['source']);dst=path_within(output,name);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes())
  if sha256_file(dst)!=entry['sha256']:raise RuntimeError('Layout file changed while capturing')
 (output/'layout.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
 return snapshot

def verify_layout(root):
 root=io_path(root);j=json.loads((root/'layout.json').read_text(encoding='utf-8'))
 if j.get('schemaVersion')!=1:raise RuntimeError('Unsupported Git layout schema')
 for name,entry in j['files'].items():
  p=path_within(root,canonical_rel(name))
  if not p.is_file() or p.stat().st_size!=entry['size'] or sha256_file(p)!=entry['sha256']:raise RuntimeError('Sealed layout hash mismatch: '+name)
 return j

# Disable process execution, path-sensitive configs and network destinations in the replay repository.
# Their raw configuration is retained byte-for-byte as evidence instead.
SAFE_CORE={'core.autocrlf','core.eol','core.safecrlf','core.filemode','core.ignorecase','core.symlinks','core.longpaths','core.quotePath'.lower()}
def configure_restore(layout_root,bare,worktree,index):
 root=io_path(layout_root);j=verify_layout(root);item=j['worktrees'][index]
 for key,value in item['effective']:
  if key.lower() in SAFE_CORE:run(bare,'config','--local',key,value)
 run(bare,'config','--local','core.hookspath',str(Path(bare)/'hooks-disabled'))
 Path(bare,'hooks-disabled').mkdir(exist_ok=True)
 # Per-worktree configs/exclusions are flattened from the frozen effective view.
 run(bare,'config','--local','extensions.worktreeConfig','true')
 for key,value in item['effective']:
  if key.lower() in SAFE_CORE:run(worktree,'config','--worktree',key,value)
 run(worktree,'config','--worktree','core.worktree',str(Path(worktree).resolve()))
 run(worktree,'config','--worktree','core.hookspath',str(Path(bare)/'hooks-disabled'))
 exclude=root/f'worktrees/{index:03d}/global-exclude'
 if exclude.is_file():run(worktree,'config','--worktree','core.excludesfile',str(exclude.resolve()))
 local=root/f'worktrees/{index:03d}/info-exclude'
 if not local.is_file():local=root/'common/info-exclude'
 if local.is_file():
  target=Path(text(worktree,'rev-parse','--path-format=absolute','--git-path','info/exclude'));target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(local.read_bytes())
 return {'source':item['layout'],'destination':str(Path(worktree).resolve()),'adminDir':text(worktree,'rev-parse','--absolute-git-dir'),'commonDir':text(worktree,'rev-parse','--path-format=absolute','--git-common-dir'),'configRemapped':True,'hooksExecuted':False,'savedRawFiles':{name:x['sha256'] for name,x in j['files'].items()}}
''',encoding='utf-8')
print('Sealed layout module completed')
