# 云端图像提取运行边界

只处理用户已授权进入当前任务空间的 PDF。先核实 Python 3.10+ 和 PyMuPDF；按需读取脚本帮助。使用实际解析到的技能目录及新建的任务输出目录：

python <resolved-skill-root>/scripts/extract_paper_images.py --pdf <cloud-pdf> --out <new-task-output-dir> --mode auto

不传 --html-url、--html-file 或 --html-base-url。原脚本的可选网络分支会访问远程图片或正文转换服务，不是云端联网入口，不得暗中启动下载或 Jina 回退。需要公开 HTML 或原始图片时，另通过宿主 web-access 的已授权渠道取得并核实；未公开稿件不得进入这些查询或第三方转换。

PDF-only 路径不联网。检查输出 manifest、裁剪内容和置信度；低置信度区域回看原 PDF 页面，表格或旋转内容不能只凭自动框。page-render 仍可能产生图件裁剪，完整页面位于 debug_pages，不能声称它是无裁剪模式。HTML 可选分支需要 beautifulsoup4 与 lxml，此云端版本未验证该分支；Pillow、pandas 是可选功能，部分表格导出还可能需要 tabulate。

依赖缺失时使用宿主 PDF 页面渲染/裁剪能力并说明提取缺口，不自动安装软件或把未测分支说成可用。
