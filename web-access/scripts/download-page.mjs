// Runs only inside the task-owned browser page. Never exports cookies or tokens.
export function startPageDownload(options) {
  const { key, startUrl, pageOrigin, allowedHosts, maxBytes, timeoutMs, maxDepth } = options;
  const controller = new AbortController();
  const job = { state: 'pending', controller };
  window[key] = job;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const allowed = (raw) => {
    const url = new URL(raw);
    return !url.username && !url.password && ['http:', 'https:'].includes(url.protocol) &&
      (url.origin === pageOrigin || (url.protocol === 'https:' && !url.port && allowedHosts.includes(url.hostname)));
  };
  (async () => {
    try {
      const visit = async (url, depth) => {
        if (depth > maxDepth) throw new Error('too_many_wrappers');
        if (!allowed(url)) throw new Error('unexpected_origin');
        // The broker intercepts every request (including redirects) before it is sent.
        const response = await fetch(url, { credentials: 'include', redirect: 'follow', signal: controller.signal });
        if (!response.ok) throw new Error('http_' + response.status);
        if (!allowed(response.url)) throw new Error('unexpected_final_origin');
        const mime = (response.headers.get('content-type') || '').toLowerCase();
        const lengthHeader = response.headers.get('content-length');
        const declared = lengthHeader === null ? null : Number(lengthHeader);
        if (declared !== null && (!Number.isSafeInteger(declared) || declared < 0)) throw new Error('incomplete');
        if (declared > maxBytes) throw new Error('too_large');
        if (!response.body) throw new Error('incomplete');
        const reader = response.body.getReader();
        const chunks = [];
        let total = 0;
        try {
          while (true) {
            const part = await reader.read();
            if (part.done) break;
            total += part.value.byteLength;
            if (total > maxBytes) throw new Error('too_large');
            chunks.push(part.value);
          }
        } finally { await reader.cancel().catch(() => {}); }
        const encoding = (response.headers.get('content-encoding') || '').toLowerCase();
        if (declared !== null && (!encoding || encoding === 'identity') && total !== declared) throw new Error('incomplete');
        const bytes = new Uint8Array(total);
        let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        if (mime.includes('text/html')) {
          const doc = new DOMParser().parseFromString(new TextDecoder().decode(bytes), 'text/html');
          for (const node of doc.querySelectorAll('iframe[src],embed[src],object[data]')) {
            let next;
            try { next = new URL(node.getAttribute('src') || node.getAttribute('data'), response.url).href; }
            catch { continue; }
            if (allowed(next)) return visit(next, depth + 1);
          }
          throw new Error('not_pdf');
        }
        if (String.fromCharCode(...bytes.slice(0, 5)) !== '%PDF-') throw new Error('not_pdf');
        if (!new TextDecoder().decode(bytes.slice(-2048)).includes('%%EOF')) throw new Error('incomplete');
        const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
          .map(value => value.toString(16).padStart(2, '0')).join('');
        const dataUrl = await new Promise((resolve, reject) => {
          const reader2 = new FileReader();
          reader2.onload = () => resolve(reader2.result);
          reader2.onerror = () => reject(new Error('incomplete'));
          reader2.readAsDataURL(new Blob([bytes], { type: 'application/pdf' }));
        });
        if (controller.signal.aborted) throw new Error('download_timeout');
        const data = String(dataUrl).split(',', 2)[1];
        Object.assign(job, { state: 'done', data, chars: data.length, bytes: total, sha256,
          mime: 'application/pdf', isPdf: true, finalUrl: response.url });
      };
      await visit(startUrl, 0);
    } catch (error) {
      Object.assign(job, { state: 'error', code: controller.signal.aborted ? 'download_timeout' :
        (['TypeError', 'NetworkError'].includes(error?.name) ? 'incomplete' : (error?.message || 'download_failed')) });
    } finally { clearTimeout(timer); }
  })();
  return true;
}

export function downloadUrlAllowed(raw, policy) {
  try {
    const url = new URL(raw);
    return !url.username && !url.password && ['http:', 'https:'].includes(url.protocol) &&
      (url.origin === policy.pageOrigin ||
        (url.protocol === 'https:' && !url.port && policy.allowedHosts.includes(url.hostname)));
  } catch { return false; }
}
