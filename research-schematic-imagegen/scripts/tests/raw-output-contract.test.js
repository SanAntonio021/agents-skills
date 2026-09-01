import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const skillPath = new URL("../../SKILL.md", import.meta.url);
const ownershipPath = new URL("../../references/output-ownership.md", import.meta.url);
const evalsPath = new URL("../../evals/evals.json", import.meta.url);

test("treats requested dimensions as generation constraints rather than post-processing permission", async () => {
  const skill = await readFile(skillPath, "utf8");
  const ownership = await readFile(ownershipPath, "utf8");

  assert.match(skill, /目标尺寸，只约束生成请求，不等于授权后期裁切、缩放、拉伸、补边、扩图或合成/);
  assert.match(skill, /实际返回尺寸与请求不一致时，停止自动尺寸适配/);
  assert.match(skill, /manifest 都要区分 `original` 与 `processed`/);
  assert.match(ownership, /只有用户明确同意后，才能另存裁切、缩放、拉伸、补边、扩图或合成后的处理版/);
});

test("keeps a regression eval for mixed-size original and processed delivery", async () => {
  const evals = JSON.parse(await readFile(evalsPath, "utf8"));
  const sizeMismatchEval = evals.evals.find((entry) => entry.id === 19);

  assert.ok(sizeMismatchEval);
  assert.match(sizeMismatchEval.expected_output, /目标尺寸视为生成约束而不是后处理授权/);
  assert.match(sizeMismatchEval.expected_output, /不自动裁切、缩放、拉伸、补边、扩图或合成/);
  assert.match(sizeMismatchEval.expected_output, /original\/processed 角色和逐文件尺寸/);
});
