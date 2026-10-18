from pathlib import Path
import os
import subprocess
import sys

task = Path(__file__).resolve().parent
tests = task.parents[1] / 'git-branch-consolidation/tests'
test_root = Path(r'D:\AgentSkillTests\git-branch-consolidation-20261014\followup')
test_root.mkdir(parents=True, exist_ok=True)
names = [
    'test_recovery_flow.FilesystemSafetyTests',
    'test_capture_v3.CaptureV3Tests.test_hidden_index_flags_and_nested_repository_block',
    'test_git_layout.GitLayoutTests.test_separate_main_without_core_worktree_captures_and_restores_external_linked',
    'test_nested_v4.NestedRecoveryTests.test_clean_and_dirty_child_replay_from_parent_packages_only',
    'test_retained_local.RetainedLocalTests.test_shared_destination_accepts_only_verified_material_union',
    'test_retained_local.RetainedLocalTests.test_directory_registration_does_not_allow_extra_children',
    'test_retained_local.RetainedLocalTests.test_source_commits_and_root_materials_stay_usable',
]
log = task / 'followup-tests.log'
with log.open('wb') as handle:
    result = subprocess.run([sys.executable, '-m', 'unittest', *names, '-v'], cwd=tests,
                            env=dict(os.environ, GBC_TEST_ROOT=str(test_root)),
                            stdout=handle, stderr=subprocess.STDOUT)
print(log.read_text(encoding='utf-8', errors='replace'))
sys.exit(result.returncode)
