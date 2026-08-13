import { nowIso } from "./common.mjs";

const BLOCK_START = "<!-- CODEX-REVIEW";
const BLOCK_END = "-->";

export function parseLeadingCodexReviewBlock(text) {
  const normalized = text.startsWith("\uFEFF") ? text.slice(1) : text;
  if (!normalized.startsWith(BLOCK_START)) return null;
  const end = normalized.indexOf(BLOCK_END);
  if (end === -1) throw new Error("Unterminated leading CODEX-REVIEW block");
  const endOffset = end + BLOCK_END.length;
  const block = normalized.slice(0, endOffset);
  const fields = {};
  for (const line of block.split(/\r?\n/).slice(1, -1)) {
    const match = /^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/.exec(line.trim());
    if (match) fields[match[1]] = match[2];
  }
  return { block, fields, endOffset, hasBom: text.startsWith("\uFEFF") };
}

export function removeLeadingCodexReviewBlock(text) {
  const parsed = parseLeadingCodexReviewBlock(text);
  if (!parsed) return text;
  const remainder = (parsed.hasBom ? "\uFEFF" : "") + text.slice((parsed.hasBom ? 1 : 0) + parsed.endOffset);
  return remainder.replace(/^(\r?\n){1,2}/, "");
}

export function generateCodexReviewBlock({ round, status = "reviewed", timestamp = nowIso(), changes = [], reasons = [] }) {
  if (!Number.isInteger(round) || round < 1) throw new Error("CODEX-REVIEW round must be a positive integer");
  const safeLines = (items, fallback) => (items.length ? items : [fallback])
    .map((item) => String(item).replace(/[\r\n]+/g, " ").trim());
  return [
    BLOCK_START,
    `round: ${round}`,
    `status: ${status}`,
    `timestamp: ${timestamp}`,
    "changes:",
    ...safeLines(changes, "none").map((item) => `- ${item}`),
    "reasons:",
    ...safeLines(reasons, "none").map((item) => `- ${item}`),
    BLOCK_END
  ].join("\n");
}

export function replaceLeadingCodexReviewBlock(text, block) {
  if (!block.startsWith(BLOCK_START) || !block.endsWith(BLOCK_END)) {
    throw new Error("Replacement must be a complete CODEX-REVIEW block");
  }
  return `${block}\n\n${removeLeadingCodexReviewBlock(text)}`;
}
