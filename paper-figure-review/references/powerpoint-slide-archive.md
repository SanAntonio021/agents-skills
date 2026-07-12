# PowerPoint 留档当前页

这套加载项保护手工编辑的 PowerPoint 论文图。它不替代普通保存，也不把大型 PPTX 放进 Git。

## 固定行为

- 加载项全局安装，按钮位于 PowerPoint“开始”选项卡的“图件版本”组。
- 用户准备尝试另一种画法时，手动点击“留档当前页”。
- 当前页在同一演示文稿内复制一次；副本移到末尾并设为隐藏。
- 原页位置不变，操作完成后仍选中原页，可继续编辑。
- 历史副本通过 PowerPoint Tags 记录：留档时间、源 Slide ID、源页原始位置和版本序号。
- 成功后自动保存当前演示文稿，不弹成功说明框。
- `Ctrl+S` 保持 PowerPoint 原生保存行为，不生成历史副本。
- 历史页不自动删除、不自动导出、不上传，也不新建演示文稿。

以下情况不改文件，只显示明确提示：

- 演示文稿尚未首次保存；
- 演示文稿只读；
- 没有打开的演示文稿或没有活动页；
- 当前页本身已经是历史副本。

## 图件文件边界

- 数据图用 Git 跟踪 Python/MATLAB 脚本、必要数据和 plot profile。
- 普通中间 PDF/PNG 不逐轮保存；只长期保留用户选中的 Image 2 参考图和最终投稿导出件。
- `.pptx`、`.pptm`、`.ppam` 不进入论文项目的普通 Git baseline。大型 PPTX 继续由百度云单向备份。
- 最终 PDF/PNG 仍按本 skill 的投稿导出流程生成。

## 源码和构建

- VBA：`assets/powerpoint-slide-archive/SlideArchive.bas`
- RibbonX：`assets/powerpoint-slide-archive/customUI14.xml`
- 构建脚本：`scripts/build_powerpoint_slide_archive.ps1`
- 成品：`assets/powerpoint-slide-archive/PaperFigureSlideArchive.ppam`（本机构建，不提交 Git）

构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_powerpoint_slide_archive.ps1 -Force
```

构建只通过 PowerPoint COM 写入 VBA 工程，再用 Open XML 包关系注入 RibbonX。需要 PowerPoint 16 和已启用的 VBOM 访问。

如果当前机器的 `Presentation.VBProject` / `Application.VBE` 返回空，不修改宏安全设置。改用一次性手工模板：

1. 先生成适合当前 VBE 代码页的临时 `.bas`。不要直接导入仓库中的 UTF-8 源码：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export_powerpoint_slide_archive_vba_for_vbe.ps1
   ```

2. 新建空白 PowerPoint，按 `Alt+F11` 打开 VBA 编辑器。
3. 在 VBA 编辑器按 `Ctrl+M`，导入上一步输出的临时 `.bas`。
4. 执行“调试 > 编译 VBAProject”，确认没有编译错误。
5. 另存为临时的 `PowerPoint 加载项 (*.ppam)`，然后关闭 PowerPoint。
6. 用该文件完成后台构建：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_powerpoint_slide_archive.ps1 -VbaTemplatePath <临时.ppam> -Force
   ```

脚本会确认临时 PPAM 含 `ppt/vbaProject.bin`，再注入 RibbonX 并生成正式成品。

## 安装和卸载

安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_powerpoint_slide_archive.ps1
```

卸载：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall_powerpoint_slide_archive.ps1
```

脚本只使用已确认受信任的 `%APPDATA%\Microsoft\AddIns`，不会新增受信任位置，也不会修改宏安全策略。安装、重装和卸载前必须关闭 PowerPoint，避免覆盖正在加载的 PPAM。

安装、同路径重装、卸载和最终重装的生命周期测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_powerpoint_slide_archive_lifecycle.ps1
```

重装先在目标目录暂存新文件，并保留原 PPAM 作为事务备份。PowerPoint 注册或加载失败时恢复原文件；脚本不结束用户进程。

## 验证

集成测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_powerpoint_slide_archive.ps1
```

测试必须确认：

- 普通保存不增加页数；
- 点击一次只增加一个副本；连续点击两次时版本号依次为 `1`、`2`；
- 两个副本均位于末尾且隐藏；
- 原页位置和当前选择不变；
- 原页与两个副本导出后的像素完全一致；
- 时间、源 Slide ID 和版本序号已记录；
- 文件已保存并可重新打开；
- 测试目录没有额外 PPTX。
