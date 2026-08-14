# CC Switch 同步工作流

本文档记录 auto-review-execute 技能推送后如何触发 cc-switch 同步。

## 标准流程

1. 修改技能文件
2. `git add` + `git commit` + `git push`
3. **立即**调用 `Invoke-CcSwitchSkillSync.ps1`，传入：
   - `-Skills @('auto-review-execute')`
   - `-ExpectedRemoteCommit '<刚刚推送的提交 SHA>'`

## 要求

- `ExpectedRemoteCommit` 必须是当前 HEAD
- 该提交修改的 skills 必须恰好等于 `-Skills` 参数指定的列表

## 示例

```powershell
& "D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1" `
  -Skills @('auto-review-execute') `
  -ExpectedRemoteCommit '8f28d0fa548882aaef761f140a7a6f4c5d542db9'
```

## 常见问题

**Q: HEAD 推进后如何同步旧提交？**

A: 无法直接同步。需要创建新提交把目标 skill 带到 HEAD。
