'use strict';
const vm = require('node:vm');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const { promisify } = require('node:util');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.length > 4000000) process.exit(2);
});
process.stdin.on('end', () => main().catch(error => finish({error: String(error.message || error)})));
let finished = false;
function finish(result) {
  if (finished) return;
  finished = true;
  process.stdout.write(JSON.stringify(result), () => process.exit(0));
}
process.on('unhandledRejection', error => finish({error: String(error.message || error)}));
setTimeout(() => finish({error: '音源初始化或解析超时'}), 28000);

async function main() {
  const request = JSON.parse(input);
  const state = {init: null, handler: null, updates: [], requests: 0};
  const context = vm.createContext({
    console: {log(){}, warn(){}, error(){}, info(){}, debug(){}, group(){}, groupEnd(){}, table(){}, time(){}, timeEnd(){}, assert(){}},
    setTimeout, clearTimeout, setInterval, clearInterval,
    URL, URLSearchParams, TextEncoder, TextDecoder,
    atob: s => Buffer.from(s, 'base64').toString('binary'),
    btoa: s => Buffer.from(s, 'binary').toString('base64'),
    lx: {
      env: 'desktop', version: '2.0.0',
      currentScriptInfo: {name: request.name || '', version: '1.0.0', rawScript: request.script},
      EVENT_NAMES: {inited: 'inited', request: 'request', updateAlert: 'updateAlert'},
      on(event, handler) { if (event === 'request') state.handler = handler; },
      send(event, data) {
        if (event === 'inited') state.init = data;
        if (event === 'updateAlert' && state.updates.length < 3) state.updates.push(data);
        return Promise.resolve();
      },
      request(url, options, callback) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), Math.min(Number(options?.timeout) || 10000, 12000));
        (async () => {
          if (++state.requests > 16 || !/^https?:\/\//i.test(url)) throw new Error('音源请求超限或地址无效');
          let body = options?.body;
          const headers = {'User-Agent': 'Mozilla/5.0', ...options?.headers};
          if (options?.form) {
            body = new URLSearchParams(options.form).toString();
            headers['Content-Type'] ||= 'application/x-www-form-urlencoded';
          } else if (body && typeof body === 'object' && !Buffer.isBuffer(body)) body = JSON.stringify(body);
          const response = await fetch(url, {method: options?.method || 'GET', headers, body,
                                             signal: controller.signal});
          const reader = response.body.getReader();
          let length = 0;
          const chunks = [];
          while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            length += value.length;
            if (length > 4000000) { await reader.cancel(); throw new Error('音源响应过大'); }
            chunks.push(Buffer.from(value));
          }
          let data = Buffer.concat(chunks).toString('utf8');
          try { data = JSON.parse(data); } catch {}
          callback(null, {statusCode: response.status, headers: Object.fromEntries(response.headers), body: data}, data);
        })().catch(error => callback(error, null, null)).finally(() => clearTimeout(timer));
        return () => controller.abort();
      },
      utils: {
        buffer: {from: (...args) => Buffer.from(...args), bufToString: (buffer, encoding) => Buffer.from(buffer).toString(encoding)},
        crypto: {
          md5: text => crypto.createHash('md5').update(String(text)).digest('hex'),
          randomBytes: n => crypto.randomBytes(Math.min(Number(n), 4096)),
          aesEncrypt(buffer, mode, key, iv) {
            const cipher = crypto.createCipheriv(mode, Buffer.from(key), iv ? Buffer.from(iv) : null);
            return Buffer.concat([cipher.update(Buffer.from(buffer)), cipher.final()]);
          },
          rsaEncrypt: (buffer, key) => crypto.publicEncrypt({key, padding: crypto.constants.RSA_PKCS1_PADDING}, Buffer.from(buffer)),
        },
        zlib: {inflate: promisify(zlib.inflate), deflate: promisify(zlib.deflate)},
      },
    },
  }, {codeGeneration: {strings: true, wasm: false}});
  vm.runInContext('var window=globalThis;', context, {timeout: 1500});
  vm.runInContext(request.script, context, {timeout: 2000, filename: 'imported-lx-source.js'});
  for (let i = 0; !state.init && i < 200; i++) await new Promise(resolve => setTimeout(resolve, 100));
  if (!state.init) throw new Error('音源未完成初始化');
  if (request.action === 'init') return finish({init: state.init, updates: state.updates});
  const result = request.info || {};
  const platform = result.platform || 'wy';
  const supported = state.init.sources?.[platform];
  if (!supported) throw new Error('这个音源不支持当前平台，请切换平台或换源');
  const qualities = supported.qualitys || [];
  const quality = qualities.includes(request.quality) ? request.quality : qualities[0] || '128k';
  if (!state.handler) throw new Error('音源没有注册请求回调');
  context.__handler = state.handler;
  context.__payload = {source: platform, action: 'musicUrl', info: {type: quality, musicInfo: result.music_info || {}}};
  const promise = vm.runInContext('Promise.resolve(__handler(__payload))', context, {timeout: 2000});
  const resolved = await promise;
  finish({result: resolved, updates: state.updates});
}
