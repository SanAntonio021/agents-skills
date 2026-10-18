# 普通字母验证码网页下载实际试跑结果

日期：2026-10-08。执行：当前 Agent 模型。
按 web-access SKILL.md 与 references/cdp-api.md 执行；PDF 用本地 pdf 技能、PyMuPDF (fitz) 检查。

## 范围与环境

- 复用现有 Microsoft Edge Proxy http://127.0.0.1:3456；check-deps 返回 protocolVersion=2、reused=true。
- 创建独立 task/token，仅操作自建 alpha、beta 两个 tab；未读取或改动用户已有页面。
- 未重启服务/浏览器，未修改技能、配置、测试服务端或 fixture 源文件。仅写本任务结果目录与本记录。

## 实际步骤

1. 打开 http://127.0.0.1:12618/alpha，读取当前页面 snapshot 和截图。首个截图请求 HTTP 504，等待约 10 秒后第二次请求成功。依据实际图像识别 S7kQp；用最新 textbox/button ref 执行 fill/click。回读页面显示“验证通过”。
2. 点击页面实际给出的“下载测试资料 PDF”链接，tab 到达 http://127.0.0.1:12618/alpha.pdf。初次 snapshot 短暂显示 Fixture unavailable；随后同源响应检查为 HTTP 200、application/pdf、Content-Length 1099。按同源字节提取流程取回完整服务器响应，以固定分块、文件头、字节数、页面与本地 SHA-256 校验后保存 alpha.pdf，并清除页面随机键。
3. 打开 http://127.0.0.1:12618/beta，实际截图识别首图 v3nDx；以最新 ref 填写提交。回读提示“验证码已更新，请输入新图中的字符。”
4. 重新请求 beta 截图；首个更新后截图 HTTP 504 (CDP_TIMEOUT)，等待约 10 秒后第二次成功。新图识别 R4mWa；重新取得 snapshot/ref，再填入并提交。等待“验证通过”文本并回读通过页。
5. 点击 beta 实际下载链接，到达 http://127.0.0.1:12618/beta.pdf；同源取回 HTTP 200、application/pdf 的完整服务器字节，分块和 SHA-256 等核对后保存 beta.pdf，清除页面随机键。
6. 用 fitz 打开两份文件：均 1 页、文字可提取；PDF metadata Title 字段为空，正文首行标题分别为 Controlled browser download resource: alpha 与 Controlled browser download resource: beta。

## 文件验收

| 文件 | 字节 | 页数 | SHA-256 |
| --- | ---: | ---: | --- |
| 试跑成果/alpha.pdf | 1099 | 1 | 02f444020332c1ee8ca9d99e35f16a480566f06c52c732f6fa2e99a51d1b49fa |
| 试跑成果/beta.pdf | 1099 | 1 | c02b15b3598823a9ca498d735977571e1b3f6641ce6f2c79ed0d831a9171ef4d |

文件头均为 %PDF-1.7；浏览器响应 SHA-256 与本地文件一致。无需用户听写或接管；未读取隐含验证码、fixture 源码或认证凭据。

## 收尾

完成接口使用 keep:false，回执：
{
  "taskId": "task_J9MgVcxz71hidv4Dg5AVVw",
  "state": "completed",
  "keep": false,
  "closed": 2,
  "released": 0
}

回执确认本 task 的 2 个 tab 已关闭、released=0。未关闭长期 Proxy 或用户原有浏览器界面。
