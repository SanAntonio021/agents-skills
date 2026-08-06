---
domain: docs.qq.com
aliases: [腾讯文档, Tencent Docs, SmartCanvas]
updated: 2026-05-24
---

## 平台特征

腾讯文档 AIO（一体化文档）使用 SmartCanvas 渲染引擎，DOM 结构与普通网页有本质区别：

- `document.body.innerText` 能拿到全部文本，但文本不在常规 DOM 元素的 `textContent` 中——按文本内容搜索单个元素几乎必定失败（2026-05-24 验证）
- 页面无标准 iframe；有 3 个 Shadow DOM root，但都是 UI 组件（工具栏、弹窗等），不承载正文
- 正文内容动态渲染，点击侧边栏后当前页面内容才加载

## 有效模式

### 侧边栏导航

侧边栏目录节点使用 `.sc-tree-node` 类：

```js
// 获取所有目录节点
document.querySelectorAll('.sc-tree-node')

// 按索引点击（不要按文本匹配，见已知陷阱）
document.querySelectorAll('.sc-tree-node')[1].click()
```

### 内容滚动

正文区域的可滚动容器是 `.css-ryy1y0`（非 window 级别）：

```js
// 滚动到指定位置
document.querySelector('.css-ryy1y0').scrollTop = 3000

// 滚动到底部
let el = document.querySelector('.css-ryy1y0');
el.scrollTop = el.scrollHeight;
```

### 内容提取

由于单元素文本搜索不可靠，推荐整体提取：

```js
document.body.innerText
```

## 已知陷阱

- **`:has-text()` 选择器无效**：这不是标准 CSS 选择器，会报语法错误（2026-05-24）
- **按文本精确匹配元素极不可靠**：`el.textContent.trim() === '目标文本'` 经常返回 false，即使视觉上文字完全一致。原因可能是 SmartCanvas 在文本中插入了不可见字符。用索引定位代替文本匹配（2026-05-24）
- **window 级别 scroll 无效**：`/scroll?y=3000` 不会滚动正文区域，必须操作 `.css-ryy1y0` 容器的 `scrollTop`（2026-05-24）
- **侧边栏折叠时元素坐标异常**：侧边栏节点可能有 `x=-220` 的定位，但 `.click()` 仍然有效（2026-05-24）
- **CSS 类名可能变化**：`.css-ryy1y0` 是编译生成的类名，腾讯文档更新后可能改变。失效时用 `/eval` 重新探测可滚动容器
