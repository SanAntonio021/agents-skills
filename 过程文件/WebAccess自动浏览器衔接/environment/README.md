# 本地只读研究报告环境

可用页面地址见 [manifest.json](manifest.json)。全部页面为虚构资料。

工具：

```powershell
$node = 'D:\Program Files\nodejs\node.exe'
$client = 'D:\BaiduSyncdisk\.agents\skills\过程文件\WebAccess自动浏览器衔接\environment\client.mjs'
& $node $client SESSION read URL
& $node $client SESSION check
& $node $client SESSION request METHOD PATH 'JSON_BODY'
```

每个独立测试使用不同 SESSION；浏览器不可用环境的会话名是 `browser-unavailable`。请求体也可以用 `@绝对文件路径` 传入，避免终端转义。POST/DELETE 自动添加幂等键；需要原请求重放时使用 `--key=原键`。`request` 转发现有 Proxy API，请根据技能中接口说明指定方法、路径和请求体。返回的任务 token 自动存于会话私有文件，不回显。测试者不读取私有凭据、环境管理文件或答案文件。

允许范围仅为清单中的本机报告页面与隔离 Proxy。禁止连接生产 3456/3457、日常用户浏览器标签或外部网站；页面没有真实登录或外部写入。浏览器为后台无界面临时实例。
