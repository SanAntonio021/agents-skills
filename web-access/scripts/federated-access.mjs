// SAML / Shibboleth / CARSI attribute-release consent.
//
// The user authorised (2026-11-22) releasing non-personal institutional
// attributes to listed academic service providers as a routine login step.
// Only affiliation, organization and pseudonymous identifiers are released
// automatically; any personal attribute, an unlisted service provider or an
// unparsable attribute list stops with a redacted status.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PROVIDERS_FILE = fileURLToPath(new URL('../references/federated-providers.json', import.meta.url));
// These are the only categories that can ever be released without asking.
const SAFE_CATEGORIES = new Set(['affiliation', 'organization', 'pseudonymous_id']);

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

function normalizeEntries(list) {
  return (Array.isArray(list) ? list : []).map((entry) => ({
    id: String(entry?.id || '').slice(0, 64),
    names: (Array.isArray(entry?.names) ? entry.names : []).map(String).filter(Boolean).slice(0, 20),
    hosts: (Array.isArray(entry?.hosts) ? entry.hosts : []).map((host) => String(host).toLowerCase()).filter(Boolean).slice(0, 20),
    loginHosts: (Array.isArray(entry?.loginHosts) ? entry.loginHosts : []).map((host) => String(host).toLowerCase()).filter(Boolean).slice(0, 20),
  })).filter((entry) => entry.id && entry.hosts.length);
}

export function loadFederatedProviders({ localFile } = {}) {
  const base = readJson(PROVIDERS_FILE) || {};
  let local = null;
  const candidate = localFile !== undefined ? localFile
    : (process.env.WEB_ACCESS_TEST_MODE === '1' || !process.env.LOCALAPPDATA) ? null
      : path.join(process.env.LOCALAPPDATA, 'web-access', 'federated-providers.local.json');
  if (candidate) local = readJson(candidate);
  const merge = (key) => normalizeEntries([...(base[key] || []), ...((local && local[key]) || [])]);
  const configured = Array.isArray(local?.autoConsentCategories) ? local.autoConsentCategories : base.autoConsentCategories;
  return {
    serviceProviders: merge('serviceProviders'),
    discoveryServices: merge('discoveryServices'),
    identityProviders: merge('identityProviders'),
    autoConsentCategories: (Array.isArray(configured) ? configured : []).filter((value) => SAFE_CATEGORIES.has(value)),
  };
}

export function hostMatches(host, patterns) {
  const value = String(host || '').toLowerCase();
  return (patterns || []).some((pattern) => value === pattern || value.endsWith(`.${pattern}`));
}

const PERSONAL_RULES = [
  ['name', /^(?:cn|commonname|displayname|givenname|sn|surname|name|fullname|urn:oid:2\.5\.4\.(?:3|4|42)|urn:oid:2\.16\.840\.1\.113730\.3\.1\.241)$/i,
    /姓名|名字|全名|姓氏|^(?:name|full ?name|display ?name|given ?name|first ?name|last ?name|surname|common ?name)$/i],
  ['email', /^(?:mail|email|e-?mail|mailaddress|urn:oid:0\.9\.2342\.19200300\.100\.1\.3)$/i, /邮箱|电子邮件|邮件|e-?mail/i],
  ['person_id', /^(?:uid|edupersonprincipalname|eppn|employeenumber|studentnumber|studentid|staffid|edupersonuniqueid|subject-?id|samaccountname|userid|username|schacpersonaluniquecode|urn:oasis:names:tc:saml:attribute:subject-id|urn:oid:0\.9\.2342\.19200300\.100\.1\.1|urn:oid:1\.3\.6\.1\.4\.1\.5923\.1\.1\.1\.(?:6|13))$/i,
    /学号|工号|学工号|证件号|身份证|账号|帐号|用户名|user ?id|principal|student (?:id|number)|employee (?:id|number)/i],
  ['phone', /^(?:mobile|telephonenumber|phone|phonenumber|urn:oid:2\.5\.4\.20|urn:oid:0\.9\.2342\.19200300\.100\.1\.41)$/i, /手机|电话|联系方式|mobile|phone|telephone/i],
];
const SAFE_RULES = [
  ['pseudonymous_id', /^(?:edupersontargetedid|targetedid|pairwise-?id|urn:oasis:names:tc:saml:attribute:pairwise-id|persistent-?id|transient-?id|urn:oid:1\.3\.6\.1\.4\.1\.5923\.1\.1\.1\.10)$/i,
    /匿名标识|定向标识|假名标识|targeted ?id|pairwise|pseudonym/i],
  ['affiliation', /^(?:edupersonscopedaffiliation|edupersonaffiliation|edupersonprimaryaffiliation|scopedaffiliation|affiliation|urn:oid:1\.3\.6\.1\.4\.1\.5923\.1\.1\.1\.(?:1|5|9))$/i,
    /身份类别|用户类别|人员类别|身份类型|用户身份|从属关系|隶属关系|affiliation/i],
  ['organization', /^(?:o|organization|organizationname|schachomeorganization|schachomeorganizationtype|edupersonorgdn|homeorganization|urn:oid:2\.5\.4\.10|urn:oid:1\.3\.6\.1\.4\.1\.25178\.1\.2\.(?:9|10))$/i,
    /所属机构|所属单位|所在机构|机构名称|所属学校|organi[sz]ation|institution/i],
];

const PERSONAL = new Set(PERSONAL_RULES.map(([category]) => category));
const ENTITLEMENT = /entitlement|权限|授权资格/i;

function ruleMatch(rules, value, index) {
  if (!value) return null;
  for (const rule of rules) if (rule[index].test(value)) return rule[0];
  return null;
}

// The attribute ID decides when it is recognised; a label can only make the
// result stricter. Unrecognised IDs are never released automatically.
export function categorizeAttribute(attribute) {
  const id = String(attribute?.id || '').trim();
  const label = String(attribute?.label || '').trim().slice(0, 80);
  const idCategory = ruleMatch(PERSONAL_RULES, id, 1) || (id && ENTITLEMENT.test(id) ? 'entitlement' : null) ||
    ruleMatch(SAFE_RULES, id, 1);
  const labelPersonal = ruleMatch(PERSONAL_RULES, label, 2);
  const labelSafe = ruleMatch(SAFE_RULES, label, 2);
  if (idCategory) {
    if (PERSONAL.has(idCategory) || idCategory === 'entitlement') return idCategory;
    return labelPersonal && labelSafe !== idCategory ? labelPersonal : idCategory;
  }
  if (id) return labelPersonal || 'unknown';
  if (labelPersonal) return labelPersonal;
  if (label && ENTITLEMENT.test(label)) return 'entitlement';
  return labelSafe || 'unknown';
}
export function classifyReleaseAttributes(attributes, allowedCategories) {
  const allowed = new Set((allowedCategories || []).filter((value) => SAFE_CATEGORIES.has(value)));
  const categories = [...new Set((attributes || []).map(categorizeAttribute))].sort();
  const blocked = categories.filter((category) => !allowed.has(category));
  return { categories, blocked, autoConsent: categories.length > 0 && blocked.length === 0 };
}

// Runs in the page. Returns structure only: attribute IDs and row labels go to
// the Broker, never attribute values. With submit:true it selects the
// per-service "remember" option (never a global one) and accepts.
export function consentPageProgram(options) {
  const opts = options || {};
  const textOf = node => String((node && (node.innerText || node.textContent)) || '').replace(/\s+/g, ' ').trim();
  const visible = node => !!node && typeof node.getClientRects === 'function' && node.getClientRects().length > 0;
  const attr = (node, key) => { try { return String(node.getAttribute(key) || ''); } catch (_) { return ''; } };
  if (location.protocol !== 'https:') return {consent: false};
  const forms = [...document.querySelectorAll('form')];
  const kindOf = form => {
    if (form.querySelectorAll('input[name="_shib_idp_consentIds"],input[name="_shib_idp_consentOptions"],[name="_eventId_AttributeReleaseRejected"]').length)
      return 'shibboleth';
    if (/uapprove/i.test(attr(form, 'action')) || form.querySelectorAll('[name*="uApprove"],[id*="uApprove"]').length) return 'uapprove';
    return null;
  };
  let candidates = forms.map(form => ({form, kind: kindOf(form)})).filter(item => item.kind);
  const pageText = (document.title || '') + '\n' + ((document.body && document.body.innerText) || '').slice(0, 20000);
  if (!candidates.length && /attribute release|information to be provided to (?:the )?service|属性发布|属性释放|信息发布|将(?:要)?(?:向|提供给).{0,12}(?:服务|提供者)|共享.{0,8}(?:属性|信息)/i.test(pageText)) {
    candidates = forms.filter(form => form.querySelectorAll('table,input[type="submit"],button').length).map(form => ({form, kind: 'generic'}));
  }
  if (!candidates.length) return {consent: false};
  if (candidates.length !== 1) return {consent: true, status: 'ambiguous_form', kind: candidates[0].kind};
  const {form, kind} = candidates[0];

  const rawAction = attr(form, 'action').trim();
  let action;
  try { action = new URL(rawAction || location.href, location.href); } catch (_) { return {consent: true, kind, status: 'insecure_form'}; }
  if (action.protocol !== 'https:' || action.origin !== location.origin ||
      String(form.method || 'get').toLowerCase() !== 'post' || !['', '_self'].includes(String(form.target || '').toLowerCase()))
    return {consent: true, kind, status: 'insecure_form'};

  const attributes = [];
  const rowTexts = [];
  for (const input of [...form.querySelectorAll('input[name="_shib_idp_consentIds"]')]) {
    const row = typeof input.closest === 'function' ? input.closest('tr') : null;
    const cell = row && row.querySelector('td,th');
    const id = String(input.consentId || attr(input, 'value') || input.id || '').trim().slice(0, 120);
    attributes.push({id, label: textOf(cell).slice(0, 80)});
    if (row) rowTexts.push(textOf(row));
  }
  if (!attributes.length) {
    for (const row of [...form.querySelectorAll('tr')]) {
      const cells = [...row.querySelectorAll('td')];
      if (cells.length < 2) continue;
      const label = textOf(cells[0]);
      if (!label || label.length > 80) { attributes.push({id: '', label: ''}); continue; }
      attributes.push({id: '', label});
      rowTexts.push(textOf(row));
    }
  }
  if (!attributes.length || attributes.some(item => !item.id && !item.label))
    return {consent: true, kind, status: 'attributes_unparsed'};

  const buttons = [...form.querySelectorAll('button,input[type="submit"]')].filter(node => visible(node) && !node.disabled);
  const label = node => textOf(node) || String(node.defaultValue || '') || attr(node, 'aria-label');
  const accepts = buttons.filter(node => attr(node, 'name') === '_eventId_proceed' ||
    /^(?:accept|agree|allow|yes|continue|同意|接受|确认|确定|同意并继续|允许)$/i.test(label(node)));
  if (accepts.length !== 1) return {consent: true, kind, status: 'ambiguous_accept'};

  // Remember for this service only; a global "never ask again" would extend
  // consent to services outside the allow-list.
  const choices = [...form.querySelectorAll('input[type="radio"],input[type="checkbox"]')]
    .filter(node => attr(node, 'name') !== '_shib_idp_consentIds');
  const choiceLabel = node => textOf((node.labels && node.labels[0]) || node.parentElement) || attr(node, 'aria-label');
  const globalPattern = /globalconsent|所有服务|全部服务|任何服务|all services|any service|global/i;
  let remember = choices.find(node => attr(node, 'value') === '_shib_idp_rememberConsent');
  if (!remember) {
    remember = choices.find(node => !globalPattern.test(attr(node, 'value') + ' ' + attr(node, 'name') + ' ' + choiceLabel(node)) &&
      /(?:记住|保存).{0,8}(?:选择|同意)|以后不再询问|下次不再询问|信息(?:变化|改变)时.{0,6}询问|remember|ask me again if/i.test(choiceLabel(node)));
  }
  const rememberMode = remember ? 'service' : choices.some(node => globalPattern.test(attr(node, 'value') + ' ' + choiceLabel(node))) ? 'global_only_skipped' : 'not_offered';

  // Match the service-provider names outside the attribute table, so a value
  // that happens to contain a publisher name cannot vouch for the SP.
  let spText = pageText;
  for (const value of rowTexts) if (value) spText = spText.split(value).join(' ');
  const spMatches = [];
  for (const [id, names] of Object.entries(opts.spNames || {})) {
    const hit = (names || []).some(name => {
      const escaped = String(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return /^[\x20-\x7e]+$/.test(name)
        ? new RegExp(`(^|[^A-Za-z0-9])${escaped}([^A-Za-z0-9]|$)`, 'i').test(spText)
        : spText.includes(name);
    });
    if (hit) spMatches.push(id);
  }

  const result = {consent: true, kind, status: 'ready', origin: location.origin, host: location.hostname, path: location.pathname,
    attributes, spMatches, rememberMode};
  if (opts.submit !== true) return result;
  if (remember && !remember.checked) {
    remember.checked = true;
    try { if (typeof Event === 'function' && remember.dispatchEvent) remember.dispatchEvent(new Event('change', {bubbles: true})); } catch (_) {}
  }
  try { form.requestSubmit(accepts[0]); } catch (_) { return {consent: true, kind, status: 'submit_failed'}; }
  return {consent: true, kind, status: 'submitted', host: location.hostname, path: location.pathname, rememberMode};
}
