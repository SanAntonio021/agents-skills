import fs from "node:fs";

import { sha256Text } from "./common.mjs";

function splitLines(text) {
  return text.replace(/\r\n/g, "\n").split("\n");
}

/** A deterministic line-level LCS diff for audit evidence, not patch application. */
export function diffText(beforeText, afterText) {
  const before = splitLines(beforeText);
  const after = splitLines(afterText);
  const rows = before.length + 1;
  const columns = after.length + 1;
  if (rows * columns > 4_000_000) {
    return {
      algorithm: "summary-only",
      beforeLines: before.length,
      afterLines: after.length,
      changed: beforeText !== afterText,
      beforeSha256: sha256Text(beforeText),
      afterSha256: sha256Text(afterText)
    };
  }

  const table = Array.from({ length: rows }, () => new Uint32Array(columns));
  for (let row = before.length - 1; row >= 0; row -= 1) {
    for (let column = after.length - 1; column >= 0; column -= 1) {
      table[row][column] = before[row] === after[column]
        ? table[row + 1][column + 1] + 1
        : Math.max(table[row + 1][column], table[row][column + 1]);
    }
  }

  const changes = [];
  let row = 0;
  let column = 0;
  while (row < before.length || column < after.length) {
    if (row < before.length && column < after.length && before[row] === after[column]) {
      row += 1;
      column += 1;
    } else if (column < after.length && (row === before.length || table[row][column + 1] >= table[row + 1][column])) {
      changes.push({ type: "added", line: column + 1, text: after[column] });
      column += 1;
    } else {
      changes.push({ type: "removed", line: row + 1, text: before[row] });
      row += 1;
    }
  }
  return {
    algorithm: "lcs-lines",
    beforeLines: before.length,
    afterLines: after.length,
    changed: changes.length > 0,
    beforeSha256: sha256Text(beforeText),
    afterSha256: sha256Text(afterText),
    changes
  };
}

export function diffFiles(beforeFile, afterFile) {
  return diffText(fs.readFileSync(beforeFile, "utf8"), fs.readFileSync(afterFile, "utf8"));
}
