from pathlib import Path
import tempfile, importlib.util, sys, json, subprocess
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
from scaffold_test_project import scaffold
from validate_test_project import Report, validate_delivery, validate_project

def main():
 with tempfile.TemporaryDirectory(prefix='delivery_') as tmp:
  base=Path(tmp);project=base/'project';scaffold(project,'交付测试','python')
  assert (project/'AGENTS.md').is_file()
  assert not (project/'过程文件').exists()
  manifest=project/'config'/'delivery.json'
  external=P.parent/'SKILL.md'
  def run(entries,dependencies):
   manifest.write_text(json.dumps(dict(entry_points=entries,dependencies=dependencies)),encoding='utf8')
   report=Report();validate_delivery(project,manifest,report);return report.errors
  assert not run(['run_test.py'],[str(external)])
  assert run(['run_test.py'],['missing.mat'])
  assert run(['run_test.py'],['过程文件/task/draft.mat'])
  assert run(['run_test.py'],[str(base/'过程文件'/'draft.mat')])
  assert run([],[])
  source=project/'analysis'/'20260914_000000_replot'/'data'/'sources.txt';source.parent.mkdir(parents=True)
  source.write_text('../../../过程文件/task/input.mat',encoding='utf8')
  assert any('process files' in x for x in run(['run_test.py'],[]))
  source.write_text(str(external),encoding='utf8')
  assert not run(['run_test.py'],[])
  (project/'AGENTS.md').unlink()
  assert any('AGENTS' in x for x in run(['run_test.py'],[]))
  # Legacy default remains structurally compatible; isolate existing analysis fixture.
  source.unlink();source.parent.rmdir();source.parent.parent.rmdir()
  assert not validate_project(project).errors
 print('PASS: default AGENTS, lazy temporary directory, external formal source, missing/process dependencies, empty entry list, analysis source, delivery AGENTS, legacy default')
if __name__=='__main__':main()