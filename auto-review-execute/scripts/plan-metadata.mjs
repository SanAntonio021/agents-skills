import fs from "node:fs";
import path from "node:path";

import {
  assertNoSymlinkSegments,
  assertRegularFile,
  ensureWithinCwd,
  isSameOrDescendant,
  normalizeForComparison
} from "./common.mjs";

const FRONT_MATTER_START = "---";
const READ_ONLY_COMMANDS = [
  {
    name: "Test-Path",
    expression: /^Test-Path(?:\s+-LiteralPath)?\s+(?:"[^"\r\n;|&`$(){}<>]+"|'[^'\r\n;|&`$(){}<>]+'|[^\s;|&`$(){}<>]+)$/i
  },
  {
    name: "Get-Content",
    expression: /^Get-Content(?:\s+-LiteralPath)?\s+(?:"[^"\r\n;|&`$(){}<>]+"|'[^'\r\n;|&`$(){}<>]+'|[^\s;|&`$(){}<>]+)$/i
  },
  {
    name: "node --version",
    expression: /^node\s+--version$/i
  }
];

function unquote(value) {
  const trimmed = value.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function scalar(value, lineNumber) {
  if (value === "[]") return [];
  if (value === "{}") return {};
  if (/^(true|false)$/i.test(value)) return /^true$/i.test(value);
  if (/^-?\d+(?:\.\d+)?$/.test(value)) return Number(value);
  if (!value) throw new Error(`Missing scalar value at front-matter line ${lineNumber}`);
  return unquote(value);
}

/**
 * Deliberately small YAML subset. Metadata is a security boundary, so reject
 * aliases, flow objects and unknown nesting instead of accepting loose YAML.
 */
export function parsePlanMetadata(text) {
  const normalized = text.startsWith("\uFEFF") ? text.slice(1) : text;
  const lines = normalized.split(/\r?\n/);
  if (lines[0] !== FRONT_MATTER_START) throw new Error("Plan must start with YAML front matter");
  let close = -1;
  for (let index = 1; index < lines.length; index += 1) {
    if (lines[index] === FRONT_MATTER_START) {
      close = index;
      break;
    }
  }
  if (close === -1) throw new Error("Plan front matter is not terminated");

  const metadata = { targetRoots: [], allowedPaths: [], acceptanceCriteria: [] };
  let inSection = null;
  let currentCriterion = null;
  for (let index = 1; index < close; index += 1) {
    const raw = lines[index];
    const lineNumber = index + 1;
    if (!raw.trim() || raw.trimStart().startsWith("#")) continue;
    if (/\t/.test(raw)) throw new Error(`Tabs are not allowed in metadata at line ${lineNumber}`);

    const topLevel = /^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/.exec(raw);
    if (topLevel) {
      const [, key, rest] = topLevel;
      if (key !== "auto-review-execute" || rest.trim()) {
        throw new Error(`Expected only 'auto-review-execute:' at front-matter line ${lineNumber}`);
      }
      inSection = "root";
      continue;
    }
    if (inSection !== "root" && inSection !== "targetRoots" && inSection !== "allowedPaths" && inSection !== "acceptanceCriteria") {
      throw new Error(`Unexpected metadata content at line ${lineNumber}`);
    }

    const section = /^  (targetRoots|allowedPaths|acceptanceCriteria):\s*(.*)$/.exec(raw);
    if (section) {
      const [, key, rest] = section;
      if (rest.trim() && rest.trim() !== "[]") throw new Error(`Section ${key} cannot have an inline value at line ${lineNumber}`);
      metadata[key] = rest.trim() === "[]" ? [] : [];
      inSection = key;
      currentCriterion = null;
      continue;
    }

    const listItem = /^    -\s+(.+)$/.exec(raw);
    if (listItem && (inSection === "targetRoots" || inSection === "allowedPaths")) {
      metadata[inSection].push(unquote(listItem[1]));
      continue;
    }

    const criterionStart = /^    -\s+(id):\s*(.+)$/.exec(raw);
    if (criterionStart && inSection === "acceptanceCriteria") {
      currentCriterion = { id: unquote(criterionStart[2]) };
      metadata.acceptanceCriteria.push(currentCriterion);
      continue;
    }

    const criterionField = /^      (description|verifyCommand|expectedOutput):\s*(.+)$/.exec(raw);
    if (criterionField && inSection === "acceptanceCriteria" && currentCriterion) {
      currentCriterion[criterionField[1]] = scalar(criterionField[2], lineNumber);
      continue;
    }
    throw new Error(`Unsupported metadata syntax at front-matter line ${lineNumber}`);
  }
  return metadata;
}

export function readPlanMetadata(planFile) {
  assertRegularFile(planFile, "plan file");
  return parsePlanMetadata(fs.readFileSync(planFile, "utf8"));
}

export function classifyReadOnlyVerifyCommand(command) {
  if (typeof command !== "string" || !command.trim()) return null;
  const trimmed = command.trim();
  return READ_ONLY_COMMANDS.find((entry) => entry.expression.test(trimmed))?.name || null;
}

export function assertReadOnlyVerifyCommand(command) {
  const type = classifyReadOnlyVerifyCommand(command);
  if (!type) {
    throw new Error(
      `verifyCommand is not in the read-only allowlist (Test-Path, Get-Content, node --version): ${command}`
    );
  }
  return type;
}

export function validatePlanMetadata(metadata, { cwd = process.cwd(), requireExistingRoots = true } = {}) {
  if (!metadata || typeof metadata !== "object") throw new Error("Plan metadata must be an object");
  const targetRoots = metadata.targetRoots;
  const allowedPaths = metadata.allowedPaths;
  const criteria = metadata.acceptanceCriteria;
  if (!Array.isArray(targetRoots) || targetRoots.length === 0) throw new Error("targetRoots must be a non-empty list");
  if (!Array.isArray(allowedPaths) || allowedPaths.length === 0) throw new Error("allowedPaths must be a non-empty list");
  if (!Array.isArray(criteria) || criteria.length === 0) throw new Error("acceptanceCriteria must be a non-empty list");

  const resolvedRoots = targetRoots.map((entry) => path.resolve(entry));
  const resolvedAllowed = allowedPaths.map((entry) => path.resolve(entry));
  ensureWithinCwd(resolvedRoots, cwd);
  if (requireExistingRoots) {
    for (const root of resolvedRoots) {
      if (!fs.existsSync(root)) throw new Error(`targetRoot does not exist: ${root}`);
      assertNoSymlinkSegments(root, root);
    }
  }
  for (const allowed of resolvedAllowed) {
    if (!resolvedRoots.some((root) => isSameOrDescendant(allowed, root))) {
      throw new Error(`allowedPath is not inside targetRoots: ${allowed}`);
    }
    const containingRoot = resolvedRoots.find((root) => isSameOrDescendant(allowed, root));
    if (fs.existsSync(allowed)) assertNoSymlinkSegments(allowed, containingRoot);
  }

  const ids = new Set();
  for (const criterion of criteria) {
    if (!criterion || typeof criterion !== "object") throw new Error("Every acceptance criterion must be an object");
    for (const key of ["id", "description", "verifyCommand", "expectedOutput"]) {
      if (typeof criterion[key] !== "string" || !criterion[key].trim()) {
        throw new Error(`acceptance criterion is missing a non-empty ${key}`);
      }
    }
    if (ids.has(criterion.id)) throw new Error(`Acceptance criterion id is duplicated: ${criterion.id}`);
    ids.add(criterion.id);
    assertReadOnlyVerifyCommand(criterion.verifyCommand);
  }

  return {
    targetRoots: resolvedRoots.map(normalizeForComparison),
    allowedPaths: resolvedAllowed.map(normalizeForComparison),
    acceptanceCriteria: criteria.map((criterion) => ({ ...criterion }))
  };
}
