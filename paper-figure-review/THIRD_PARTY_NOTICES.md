# Third-party notices

## Liberation Serif 2.1.5

- Project: Liberation Fonts
- Source: https://github.com/liberationfonts/liberation-fonts
- Pinned source commit: `49e1358e4017577429c9f8c39a3e6e879093264e`
- Binary release archive: `liberation-fonts-ttf-2.1.5.tar.gz`
- License: SIL Open Font License 1.1
- Local license copy: `assets/fonts/LICENSE`

The four bundled Liberation Serif TTF files are process-local fallback assets.
The skill does not install them into the operating system.

## Paul Tol colour schemes

- Project: Paul Tol colour schemes
- Source: https://sronpersonalpages.nl/~pault/
- Local use: static high-contrast, bright, muted, and nightfall values
- Upstream code license: BSD 3-Clause

The color values are stored locally so an upstream edit cannot change a paper's
confirmed figure color map.

## K-Dense scientific-visualization

- Project: K-Dense scientific-visualization skill
- Source: https://github.com/K-Dense-AI/claude-scientific-skills
- Pinned commit: `13385c7c4db02fdcc84a020752c07cce91ef780e`
- License: MIT

Only the palette-routing, export-manifest, and audit concepts were absorbed.
The upstream Matplotlib style itself is not copied because its font, open-axis,
outward-tick, and margin choices conflict with this skill's IEEE profile.
