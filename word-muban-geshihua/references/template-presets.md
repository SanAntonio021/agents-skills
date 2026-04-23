# Template Presets

- `tongyong-moren`
  - Public asset: `assets/master-default-template.style-profile.json`
  - Source policy: synthesized from `jishu-zongjie` body rules and `gongzuo-zongjie` cover conventions
  - Intended use: long-term default formatting for general reports, acceptance materials, and reusable Word exports

- `jishu-zongjie`
  - Public asset: `assets/default-template.style-profile.json`
  - Source policy: technical-summary style family; original sample document omitted from the public repo
  - Intended use: jishu-zongjie / acceptance-report formatting with the `GF报告...` custom style family

- `gongzuo-zongjie`
  - Public asset: `assets/work-summary-template.style-profile.json`
  - Source policy: work-summary style family; original sample document omitted from the public repo
  - Intended use: gongzuo-zongjie formatting that stays closer to built-in Word heading/body styles

- `qiye-shenbao`
  - Public asset: `assets/qiye-shenbao-template.style-profile.json`
  - Source policy: proposal-style formatting family; original sample document omitted from the public repo
  - Intended use: proposal-style formatting; on this machine it is also the current default when the user does not specify another formatting source

Legacy English aliases remain accepted for compatibility:

- `master-default` -> `tongyong-moren`
- `technical-summary` -> `jishu-zongjie`
- `work-summary` -> `gongzuo-zongjie`
- `default` -> `qiye-shenbao`

Use `qiye-shenbao` as the current default on this machine when the user leaves the format unspecified. Use `tongyong-moren` when the user explicitly wants a general report style, use `jishu-zongjie` when the user wants the original `GF报告...` look, and use `gongzuo-zongjie` when the user explicitly wants the work-summary cover/body feel. The public repo ships style profiles only, not the original sample documents.
