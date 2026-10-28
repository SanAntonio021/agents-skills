// Browser authentication policy lives here, not in publisher-specific clients.
export function loginAutofillExpression(submit) {
  return String.raw`(() => {
      const submitRequested = __SUBMIT__;
      const visible = e => !!e && e.getClientRects().length > 0;
      const matches = (element, selector) => {
        try { return element.matches(selector); } catch (_) { return false; }
      };
      const autofilled = element =>
        matches(element, ':-webkit-autofill') || matches(element, ':autofill');
      if (location.protocol !== 'https:') return {status: 'not_https'};
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
      let action;
      try { action = new URL(form.getAttribute('action') || location.href, location.href); }
      catch (_) { return {status: 'insecure_form'}; }
      if (action.protocol !== 'https:' || action.origin !== location.origin ||
          (form.method || 'get').toLowerCase() !== 'post' ||
          !['', '_self'].includes((form.target || '').toLowerCase()))
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
      if (!autofilled(identityFields[0])) return {status: 'identity_not_filled'};
      if (!autofilled(passwords[0])) return {status: 'password_not_filled'};

      const requiredCheckboxes = [...form.querySelectorAll('input[type="checkbox"][required]')].filter(visible);
      if (requiredCheckboxes.some(input => !input.checked)) return {status: 'consent_required'};
      const requiredRadios = [...form.querySelectorAll('input[type="radio"][required]')].filter(visible);
      const radioGroups = [...new Set(requiredRadios.map(input => input.name || '__unnamed__'))];
      for (const name of radioGroups) {
        const group = [...form.querySelectorAll('input[type="radio"]')]
          .filter(input => (input.name || '__unnamed__') === name && visible(input));
        if (!group.some(input => input.checked)) return {status: 'consent_required'};
      }

      const submitControls = [...form.querySelectorAll('button,input[type="submit"],input[type="image"]')]
        .filter(control => visible(control) && !control.disabled &&
          ((control.tagName || '').toLowerCase() !== 'button' ||
           ['', 'submit'].includes((control.getAttribute('type') || '').toLowerCase())));
      if (submitControls.length !== 1) return {status: 'ambiguous_submit'};
      const submitControl = submitControls[0];
      let submitAction = action;
      try {
        const overrideAction = submitControl.getAttribute('formaction');
        if (overrideAction) submitAction = new URL(overrideAction, location.href);
      } catch (_) { return {status: 'insecure_form'}; }
      const submitMethod = (submitControl.getAttribute('formmethod') || form.method || 'get').toLowerCase();
      const submitTarget = (submitControl.getAttribute('formtarget') || form.target || '').toLowerCase();
      if (submitAction.protocol !== 'https:' || submitAction.origin !== location.origin ||
          submitMethod !== 'post' || !['', '_self'].includes(submitTarget))
        return {status: 'insecure_form'};

      if (submitRequested) {
        try { form.requestSubmit(submitControl); }
        catch (_) { return {status: 'submit_failed'}; }
        return {status: 'submitted', host: location.hostname, path: location.pathname};
      }
      return {status: 'ready', host: location.hostname, path: location.pathname};
    })()` .replace('__SUBMIT__', submit ? 'true' : 'false');
}

export function accessProbe() {
  const text = ((document.title || '') + '\n' + (document.body?.innerText || '').slice(0, 16000));
  const visible = node => node.getClientRects().length > 0;
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const hints = inputs.map(node => [node.type, node.name, node.id, node.autocomplete,
    node.getAttribute('placeholder'), node.getAttribute('aria-label')].filter(Boolean).join(' ')).join(' ');
  if (/403\s+access denied|access denied|forbidden|automated access/i.test(text))
    return { state: 'access_denied', failureCode: 'access_denied', interactionRequired: false, handoffRequired: false, reason: 'site_denied' };
  if (/face (?:recognition|verification)|刷脸|人脸识别|windows security|系统安全|安全密钥|security key|authenticator|动态口令|totp|短信验证码|sms (?:code|verification)/i.test(text))
    return { state: 'user_handoff_required', failureCode: 'user_handoff_required', handoffRequired: true, interactionRequired: false, reason: 'strong_authentication' };
  if (/captcha|滑块|图形验证码|拖动.*验证|拼图|recaptcha|hcaptcha/i.test(text + ' ' + hints) ||
      document.querySelector('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.geetest_panel'))
    return { state: 'verification_required', failureCode: 'verification_required', interactionRequired: true, handoffRequired: false, reason: 'visual_verification' };
  if (/验证码|verification code|one.time (?:code|password)|otp/i.test(text + ' ' + hints))
    return { state: 'verification_required', failureCode: 'verification_required', interactionRequired: true, handoffRequired: false,
      reason: /email|e-mail|邮箱|电子邮件/i.test(text + ' ' + hints) ? 'email_code' : 'verification_method_unresolved' };
  if (/unusual traffic|too many requests|rate limit|verify you are human|checking your browser|cloudflare|access check/i.test(text))
    return { state: 'challenge', failureCode: 'challenge', interactionRequired: true, handoffRequired: false, reason: 'site_challenge' };
  if (inputs.some(node => node.type === 'password') || /sign in|log in|single sign.on|institutional login|登录|统一身份认证/i.test(text))
    return { state: 'auth_required', failureCode: 'auth_required', interactionRequired: true, handoffRequired: false, reason: 'login' };
  return { state: 'ready', failureCode: null, interactionRequired: false, handoffRequired: false };
}
