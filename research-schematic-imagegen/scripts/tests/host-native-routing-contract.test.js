import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const skillPath = new URL("../../SKILL.md", import.meta.url);
const evalsPath = new URL("../../evals/evals.json", import.meta.url);

test("documents host-native account as the highest-priority default route", async () => {
  const skill = await readFile(skillPath, "utf8");

  assert.match(skill, /本地登录账号 -> UESTC -> 贾维斯 -> 夯炸了/);
  assert.match(skill, /不是 CC Switch provider，不写入私有注册表/);
  assert.match(skill, /generate-local-account\.js/);
  assert.match(skill, /--ignore-user-config/);
  assert.match(skill, /不要在 CC Switch 或其他自定义 provider 任务里把当前会话的内嵌 `image_gen` 当作本地账号路径/);
  assert.match(skill, /route_mode=local-account-official/);
  assert.match(skill, /不能满足精确模型要求/);
  assert.match(skill, /native_requests_sent/);
  assert.match(skill, /用户明确选择 direct 时直接执行该接口，不先调用本地登录账号/);
});

test("keeps a regression eval for host-native-first failover", async () => {
  const evals = JSON.parse(await readFile(evalsPath, "utf8"));
  const routingEval = evals.evals.find((entry) => entry.id === 18);

  assert.ok(routingEval);
  assert.match(routingEval.expected_output, /本地登录账号 -> UESTC -> 贾维斯 -> 夯炸了/);
  assert.match(routingEval.expected_output, /隔离的官方 Codex 临时会话/);
  assert.match(routingEval.expected_output, /需要重新登录.*立即停止/);
});

test("keeps a regression eval for custom-provider image generation", async () => {
  const evals = JSON.parse(await readFile(evalsPath, "utf8"));
  const customProviderEval = evals.evals.find((entry) => entry.id === 20);

  assert.ok(customProviderEval);
  assert.match(customProviderEval.expected_output, /不调用当前任务的内嵌 image_gen/);
  assert.match(customProviderEval.expected_output, /--ignore-user-config/);
  assert.match(customProviderEval.expected_output, /真实 PNG/);
});
