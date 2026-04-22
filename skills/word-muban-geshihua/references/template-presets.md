# Template Presets

- `tongyong-moren`
  - Template: `assets/master-default-template.docx`
  - Source: synthesized from `jishu-zongjie` body rules and `gongzuo-zongjie` cover conventions
  - Intended use: long-term default formatting for general reports, acceptance materials, and reusable Word exports

- `jishu-zongjie`
  - Template: `assets/default-template.docx`
  - Source: `2. 技术总结报告.doc`
  - Intended use: jishu-zongjie / acceptance-report formatting with the `GF报告...` custom style family

- `gongzuo-zongjie`
  - Template: `assets/work-summary-template.docx`
  - Source: `1. 工作总结报告.docx`
  - Intended use: gongzuo-zongjie formatting that stays closer to built-in Word heading/body styles

- `qiye-shenbao`
  - Template: `assets/qiye-shenbao-template.docx`
  - Source: `D:\BaiduSyncdisk\申报书本子\雅江壹新\2.项目申报书-锦弘脑机接口多场景融合高价值应用示范项目.docx`
  - Intended use: proposal-style formatting for the `锦弘脑机接口多场景融合高价值应用示范项目` document family; on this machine it is also the current default when the user does not specify another formatting source

Legacy English aliases remain accepted for compatibility:

- `master-default` -> `tongyong-moren`
- `technical-summary` -> `jishu-zongjie`
- `work-summary` -> `gongzuo-zongjie`
- `default` -> `qiye-shenbao`

Use `qiye-shenbao` as the current default on this machine when the user leaves the format unspecified. Use `tongyong-moren` when the user explicitly wants a general report style, use `jishu-zongjie` when the user wants the original `GF报告...` look, and use `gongzuo-zongjie` when the user explicitly wants the work-summary cover/body feel.
