// Browser authentication policy lives here, not in publisher-specific clients.
//
// loginFormProgram runs inside the page. It never reads field values. In
// `autofill` mode it only submits a form the browser has already autofilled; in
// `credential` mode the Broker passes a secret from the OS credential store as a
// Runtime.callFunctionOn argument, and the program writes it into the single
// verified password field. Both modes return status strings only.
export function loginFormProgram(options) {
  const opts = options || {};
  const mode = opts.mode === 'credential' ? 'credential' : 'autofill';
  const submitRequested = opts.submit === true;
  const visible = e => {
    if (!e || typeof e.getClientRects !== 'function' || e.getClientRects().length === 0) return false;
    try {
      if (typeof getComputedStyle === 'function') {
        const style = getComputedStyle(e);
        if (style && (style.visibility === 'hidden' || style.display === 'none')) return false;
      }
    } catch (_) {}
    return true;
  };
  const matches = (element, selector) => {
    try { return element.matches(selector); } catch (_) { return false; }
  };
  const autofilled = element =>
    matches(element, ':-webkit-autofill') || matches(element, ':autofill');
  const label = element => String(element.innerText || element.textContent ||
    (element.tagName === 'INPUT' ? element.defaultValue : '') ||
    element.getAttribute('aria-label') || element.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  const isTab = element => (element.getAttribute('role') || '').toLowerCase() === 'tab' ||
    /(?:^|[\s_-])tabs?(?:$|[\s_-])/i.test(element.getAttribute('class') || '');
  const sameSecureOrigin = url => url.protocol === 'https:' && url.origin === location.origin;

  if (location.protocol !== 'https:') return {status: 'not_https'};
  if (mode === 'credential' && location.origin !== opts.expectedOrigin) return {status: 'origin_mismatch'};
  const pageText = (document.title || '') + '\n' +
    ((document.body && document.body.innerText) || '').slice(0, 12000);
  if (!/(?:sign in|log in|login|single sign-on|\bsso\b|登录|统一身份认证)/i.test(pageText))
    return {status: 'not_login_page'};

  const passwords = [...document.querySelectorAll('input[type="password"]')].filter(visible);
  if (!passwords.length) return {status: 'no_password_form'};
  const forms = [...new Set(passwords.map(input => input.form).filter(Boolean))];
  if (forms.length !== 1 || passwords.filter(input => input.form === forms[0]).length !== 1)
    return {status: 'ambiguous_form'};

  const form = forms[0];
  const rawAction = String(form.getAttribute('action') || '').trim();
  // A missing, "#" or javascript: action means page script owns the submission.
  const scriptAction = !rawAction || rawAction === '#' || /^javascript:/i.test(rawAction);
  let action;
  try { action = new URL(scriptAction ? location.href : rawAction, location.href); }
  catch (_) { return {status: 'insecure_form'}; }
  const formMethod = String(form.method || 'get').toLowerCase();
  const formTarget = String(form.target || '').toLowerCase();
  if (!sameSecureOrigin(action) || !['', '_self'].includes(formTarget))
    return {status: 'insecure_form'};

  const identityFields = [...form.querySelectorAll('input')].filter(input => {
    if (!visible(input)) return false;
    const type = (input.type || 'text').toLowerCase();
    if (!['text', 'email', 'tel'].includes(type)) return false;
    const hint = [input.type, input.name, input.id, input.getAttribute('autocomplete')]
      .filter(Boolean).join(' ');
    return type === 'email' || /user(?:name)?|e-?mail|login|account|uid|学号|工号/i.test(hint);
  });
  if (identityFields.length !== 1) return {status: 'ambiguous_identity'};
  if (mode === 'autofill') {
    if (!autofilled(identityFields[0])) return {status: 'identity_not_filled'};
    if (!autofilled(passwords[0])) return {status: 'password_not_filled'};
  }

  // Only controls the site marks as required are checked. Optional boxes such
  // as "remember me" or "stay signed in for 7 days" are never touched.
  const requiredCheckboxes = [...form.querySelectorAll('input[type="checkbox"][required]')].filter(visible);
  if (requiredCheckboxes.some(input => !input.checked)) return {status: 'consent_required'};
  const requiredRadios = [...form.querySelectorAll('input[type="radio"][required]')].filter(visible);
  const radioGroups = [...new Set(requiredRadios.map(input => input.name || '__unnamed__'))];
  for (const name of radioGroups) {
    const group = [...form.querySelectorAll('input[type="radio"]')]
      .filter(input => (input.name || '__unnamed__') === name && visible(input));
    if (!group.some(input => input.checked)) return {status: 'consent_required'};
  }

  const nativeSubmits = [...form.querySelectorAll('button,input[type="submit"],input[type="image"]')]
    .filter(control => visible(control) && !control.disabled &&
      ((control.tagName || '').toLowerCase() !== 'button' ||
       ['', 'submit'].includes((control.getAttribute('type') || '').toLowerCase())));
  let submitMode;
  let submitControl;
  if (nativeSubmits.length === 1) {
    submitControl = nativeSubmits[0];
    let submitAction = action;
    try {
      const overrideAction = submitControl.getAttribute('formaction');
      if (overrideAction) submitAction = new URL(overrideAction, location.href);
    } catch (_) { return {status: 'insecure_form'}; }
    const submitMethod = String(submitControl.getAttribute('formmethod') || formMethod).toLowerCase();
    const submitTarget = String(submitControl.getAttribute('formtarget') || formTarget).toLowerCase();
    if (!sameSecureOrigin(submitAction) || submitMethod !== 'post' || !['', '_self'].includes(submitTarget))
      return {status: 'insecure_form'};
    submitMode = 'form';
  } else if (nativeSubmits.length === 0 && opts.allowScriptSubmit === true) {
    // Script-submitted login (e.g. an <a> or type=button that encrypts and posts).
    // The Broker runs this only behind its network guard, which blocks
    // cross-origin non-GET requests and any request URL carrying the secret.
    if (formMethod !== 'post' && !(mode === 'credential' && scriptAction))
      return {status: 'insecure_form'};
    const loginLabel = /^(?:登\s*录|登\s*陆|立即登录|安全登录|确\s*定|提\s*交|log\s*in|login|sign\s*in|submit)$/i;
    const scriptButtons = [...form.querySelectorAll('a,button,input[type="button"],[role="button"]')]
      .filter(control => visible(control) && !control.disabled && !isTab(control) &&
        loginLabel.test(label(control)));
    const unique = [...new Set(scriptButtons)];
    if (unique.length !== 1) return {status: 'ambiguous_submit'};
    submitControl = unique[0];
    if ((submitControl.tagName || '').toLowerCase() === 'a') {
      const href = String(submitControl.getAttribute('href') || '').trim();
      if (href && href !== '#' && !/^javascript:/i.test(href)) {
        try { if (!sameSecureOrigin(new URL(href, location.href))) return {status: 'insecure_form'}; }
        catch (_) { return {status: 'insecure_form'}; }
      }
    }
    submitMode = 'script';
  } else {
    return {status: 'ambiguous_submit'};
  }

  if (!submitRequested) return {status: 'ready', origin: location.origin, host: location.hostname, path: location.pathname, submitMode};
  if (mode === 'credential') {
    if (typeof opts.secret !== 'string' || !opts.secret) return {status: 'credential_missing'};
    const setValue = (element, value) => {
      let setter;
      try {
        const proto = Object.getPrototypeOf(element);
        const descriptor = proto && Object.getOwnPropertyDescriptor(proto, 'value');
        setter = descriptor && descriptor.set;
      } catch (_) {}
      if (setter) setter.call(element, value); else element.value = value;
      for (const type of ['input', 'change']) {
        try {
          if (typeof Event === 'function' && typeof element.dispatchEvent === 'function')
            element.dispatchEvent(new Event(type, {bubbles: true}));
        } catch (_) {}
      }
    };
    if (typeof opts.account === 'string' && opts.account) setValue(identityFields[0], opts.account);
    setValue(passwords[0], opts.secret);
  }
  try {
    if (submitMode === 'form') form.requestSubmit(submitControl);
    else submitControl.click();
  } catch (_) { return {status: 'submit_failed'}; }
  return {status: 'submitted', origin: location.origin, host: location.hostname, path: location.pathname, submitMode};
}

export function loginAutofillExpression(submit, options = {}) {
  const args = {mode: 'autofill', submit: submit === true, allowScriptSubmit: options.allowScriptSubmit === true};
  return `(${loginFormProgram.toString()})(${JSON.stringify(args)})`;
}

export function accessProbe() {
  const visible = node => {
    if (!node || typeof node.getClientRects !== 'function' || node.getClientRects().length === 0) return false;
    try {
      if (typeof getComputedStyle === 'function') {
        const style = getComputedStyle(node);
        if (style && (style.visibility === 'hidden' || style.display === 'none')) return false;
      }
    } catch (_) {}
    return true;
  };
  const rawText = ((document.title || '') + '\n' + (document.body?.innerText || '').slice(0, 16000));
  // Login-method switch entries ("验证码登录", "短信登录", "Sign in with SMS") are
  // labels for another tab, not a requirement of the active form. Strip them
  // before looking for verification or strong-authentication wording.
  const method = '(?:短信|手机(?:号码?)?|动态(?:码|口令|密码)?|验证码|校验码|扫码|二维码|微信|企业微信|钉钉|邮箱|人脸|刷脸|指纹|' +
    '安全密钥|sms|text message|otp|one[- ]time (?:code|password)|verification code|code|qr ?code|passkey|security key|authenticator|e-?mail)';
  const verb = '(?:登录|登陆|认证|login|log in|sign[- ]?in)';
  const switchLabel = new RegExp(`^(?:使用|用|通过|改用|切换(?:到|至)?)?\\s*(?:${method}\\s*){1,3}${verb}(?:方式)?$|` +
    `^${verb}\\s*(?:with|via|using|by)\\s+(?:an?\\s+|your\\s+)?(?:${method}\\s*){1,3}(?:instead)?$`, 'i');
  const isSwitch = value => value.length > 0 && value.length <= 24 && switchLabel.test(value);
  const labels = new Set();
  for (const line of rawText.split(/\n|\t|\s{2,}|[|｜·•]/)) {
    const value = line.replace(/\s+/g, ' ').trim();
    if (isSwitch(value)) labels.add(value);
  }
  const candidates = [...document.querySelectorAll('a,button,li,span,label,div,p,[role="tab"],[role="button"],[role="link"]')]
    .slice(0, 3000);
  for (const node of candidates) {
    const value = String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
    if (isSwitch(value) && visible(node)) labels.add(value);
  }
  let text = rawText.replace(/\s+/g, ' ');
  for (const value of [...labels].sort((a, b) => b.length - a.length)) text = text.split(value).join(' ');

  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const inputHints = inputs.map(node => [node.type, node.name, node.id, node.autocomplete,
    node.getAttribute('placeholder'), node.getAttribute('aria-label')].filter(Boolean).join(' '));
  const hints = inputHints.join(' ');
  const activePassword = inputs.some(node => String(node.type || '').toLowerCase() === 'password');
  const visualWidget = [...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.geetest_panel')]
    .some(node => visible(node) && !/size=invisible/i.test(node.getAttribute('src') || ''));

  if (/403\s+access denied|access denied|forbidden|automated access/i.test(rawText))
    return { state: 'access_denied', failureCode: 'access_denied', interactionRequired: false, handoffRequired: false, reason: 'site_denied' };
  // While a password form is active, a code requirement must show up as a
  // visible input or as an explicit instruction ("请输入短信验证码"); a bare
  // mention such as help text does not count. Prompts without an input (face,
  // system security, security key) are judged from the remaining text.
  const instruction = '(?:请输入|请填写|输入|填写|enter|type|已发送|发送至|sent to|we sent)[^。.!！?？]{0,16}?';
  const strongPrompt = /face (?:recognition|verification)|刷脸|人脸识别|windows security|系统安全|安全密钥|security key/i;
  const strongCodeWords = '(?:authenticator|动态口令|totp|短信验证码|sms.?(?:code|verification))';
  const strongCode = new RegExp(strongCodeWords, 'i');
  const strongCodeText = activePassword ? new RegExp(instruction + strongCodeWords, 'i') : strongCode;
  if (strongPrompt.test(text) || strongCode.test(hints) || strongCodeText.test(text))
    return { state: 'user_handoff_required', failureCode: 'user_handoff_required', handoffRequired: true, interactionRequired: false, reason: 'strong_authentication' };
  if (/captcha|滑块|图形验证码|图片验证码|拖动.*验证|拼图|recaptcha|hcaptcha/i.test(text + ' ' + hints) || visualWidget)
    return { state: 'verification_required', failureCode: 'verification_required', interactionRequired: true, handoffRequired: false, reason: 'visual_verification' };
  const codeWords = '(?:验证码|校验码|动态码|verification code|one.time.(?:code|password)|\\botp\\b)';
  const codePattern = new RegExp(codeWords, 'i');
  const codeText = activePassword ? new RegExp(instruction + codeWords, 'i') : codePattern;
  if (codePattern.test(hints) || codeText.test(text)) {
    // Judge the channel from the code field and page text, not from an email-type account field.
    const codeHints = inputHints.filter(value => codePattern.test(value)).join(' ');
    return { state: 'verification_required', failureCode: 'verification_required', interactionRequired: true, handoffRequired: false,
      reason: /email|e-mail|邮箱|电子邮件/i.test(text + ' ' + codeHints) ? 'email_code' : 'verification_method_unresolved' };
  }
  if (/unusual traffic|too many requests|rate limit|verify you are human|checking your browser|cloudflare|access check/i.test(rawText))
    return { state: 'challenge', failureCode: 'challenge', interactionRequired: true, handoffRequired: false, reason: 'site_challenge' };
  if (activePassword || /sign in|log in|single sign.on|institutional login|登录|统一身份认证/i.test(rawText))
    return { state: 'auth_required', failureCode: 'auth_required', interactionRequired: true, handoffRequired: false, reason: 'login' };
  return { state: 'ready', failureCode: null, interactionRequired: false, handoffRequired: false };
}
