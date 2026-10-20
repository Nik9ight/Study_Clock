// Run with Node 22+ and Chrome/Edge: node tests/browser_smoke.cjs
// Set BROWSER_PATH to override the browser executable.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { spawn } = require('node:child_process');
const { once } = require('node:events');

async function main() {
  const browserPath = [
    process.env.BROWSER_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/chromium', '/usr/bin/google-chrome',
  ].find(candidate => candidate && fs.existsSync(candidate));
  assert.ok(browserPath, 'Install Chrome/Edge or set BROWSER_PATH');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'focus-browser-'));
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end(fs.readFileSync(path.join(__dirname, '..', 'focus.html')));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const browser = spawn(browserPath, [
    '--headless=new', '--disable-gpu', '--no-first-run',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
  ], { windowsHide: true, stdio: 'ignore' });
  const errors = [];
  browser.on('error', error => errors.push(error.message));
  let socket;
  try {
    const portFile = path.join(profile, 'DevToolsActivePort');
    let port;
    for (let retry = 0; !port && retry < 100; retry++) {
      try {
        port = fs.readFileSync(portFile, 'utf8').split('\n')[0].trim();
      } catch (error) {
        if (!['ENOENT', 'EBUSY', 'EACCES'].includes(error.code)) throw error;
      }
      if (port) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(port, `Browser did not start: ${errors.join(', ')}`);
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
    await once(socket, 'open');
    let nextId = 0;
    const pending = new Map();
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(message.params));
      if (pending.has(message.id)) {
        const { resolve, reject, timeout } = pending.get(message.id);
        pending.delete(message.id);
        clearTimeout(timeout);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      }
    });
    function send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = ++nextId;
        const timeout = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`Timed out: ${method}`));
        }, 10000);
        pending.set(id, { resolve, reject, timeout });
        socket.send(JSON.stringify({ id, method, params }));
      });
    }
    async function evaluate(expression) {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
      return result.result.value;
    }
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
    for (let retry = 0; retry < 50; retry++) {
      if (await evaluate("document.readyState === 'complete' && !!document.getElementById('playBtn')")) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.equal(await evaluate("$('display').textContent"), '25:00');
    await evaluate("$('playBtn').click(); $('clockTab').click()");
    assert.equal(await evaluate('state'), 'running');
    for (const style of ['Installer', 'ASCII', 'Segments']) {
      await evaluate(`$('progressStyle').value = '${style}'; $('progressStyle').dispatchEvent(new Event('change'))`);
      assert.equal(await evaluate('state'), 'running');
      assert.equal(await evaluate("$('progress').dataset.style"), style);
    }
    assert.match(await evaluate("$('display').textContent"), /^\d{2}:\d{2}:\d{2}$/);
    await evaluate("$('formatBtn').click(); $('theme').value = 'Forest'; $('theme').dispatchEvent(new Event('change'))");
    assert.equal(await evaluate('use24Hour'), false);
    assert.equal(await evaluate('document.documentElement.dataset.theme'), 'Forest');
    assert.equal(await evaluate('state'), 'running');
    assert.equal(await evaluate("$('sessionMin').disabled"), true);
    await evaluate('deadline = Date.now() - 1000; tick()');
    assert.equal(await evaluate('state'), 'completed');
    assert.equal(await evaluate("$('progress').getAttribute('aria-valuenow')"), '100');
    assert.equal(await evaluate("$('progressCells').querySelectorAll('.filled').length"), 20);
    assert.equal(await evaluate('sessionsCompleted'), 1);
    assert.equal(await evaluate('dailyRemainingSeconds()'), 6000);
    await evaluate("$('playBtn').click(); $('timerTab').click(); $('playBtn').click()");
    assert.equal(await evaluate('state'), 'paused');
    assert.equal(await evaluate("$('playBtn').textContent"), 'Resume');
    assert.equal(await evaluate("$('progressStatus').textContent"), 'PAUSED');
    await evaluate("$('resetBtn').click(); $('settingsBtn').click(); $('sessionMin').value = '999'; $('sessionMin').dispatchEvent(new Event('change'))");
    assert.equal(await evaluate('sessionMinutes'), 60);
    assert.equal(await evaluate('sessionsCompleted'), 0);
    await evaluate("$('dailySessions').value = '1'; $('dailySessions').dispatchEvent(new Event('change')); start(); deadline = Date.now() - 1000; tick()");
    assert.equal(await evaluate("$('playBtn').textContent"), 'New goal');
    assert.equal(await evaluate('dailyRemainingSeconds()'), 0);
    await evaluate('start(); pause()');
    assert.equal(await evaluate('sessionsCompleted'), 0);
    await evaluate("$('hideBtn').click()");
    assert.equal(await evaluate("$('app').hidden && !$('reviveBtn').hidden"), true);
    await evaluate("$('reviveBtn').click(); reset(); $('settingsBtn').click(); document.activeElement.blur()");
    await send('Input.dispatchKeyEvent', { type: 'keyDown', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
    assert.equal(await evaluate('state'), 'running');
    await evaluate('reset()');
    await send('Page.reload');
    await new Promise(resolve => setTimeout(resolve, 500));
    assert.equal(await evaluate('document.documentElement.dataset.theme'), 'Forest');
    assert.equal(await evaluate('use24Hour'), false);
    assert.equal(await evaluate('progressStyle'), 'Segments');
    assert.equal(await evaluate("$('progressStyle').value"), 'Segments');

    const screenshots = process.argv.includes('--screenshots')
      ? fs.mkdtempSync(path.join(os.tmpdir(), 'focus-previews-')) : null;
    for (const width of [320, 390, 1280]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height: 860, deviceScaleFactor: 1, mobile: width < 500 });
      for (const theme of ['Midnight', 'Paper', 'Forest']) {
        await evaluate(`$('theme').value = '${theme}'; $('theme').dispatchEvent(new Event('change')); setMode('clock')`);
        for (const style of ['Installer', 'ASCII', 'Segments']) {
          await evaluate(`$('progressStyle').value = '${style}'; $('progressStyle').dispatchEvent(new Event('change'))`);
          for (const percent of [0, 42, 100]) {
            await evaluate(`secondsLeft = Math.round(totalSeconds * (1 - ${percent} / 100)); renderProgress()`);
            assert.equal(await evaluate("$('progress').getAttribute('aria-valuenow')"), String(percent));
            if (style === 'ASCII') {
              assert.equal(await evaluate("$('asciiBar').textContent.length"), 32);
              assert.equal(await evaluate("$('asciiBar').scrollWidth <= $('progress').clientWidth"), true, `ASCII overflow: ${width}`);
              if (percent === 100) assert.equal(await evaluate("$('asciiBar').textContent"), '[' + '='.repeat(30) + ']');
            } else if (style === 'Installer') {
              const filled = Math.floor(percent / 100 * 28);
              assert.equal(await evaluate("$('installerBar').textContent"), '[' + '█'.repeat(filled) + '░'.repeat(28 - filled) + ']');
              assert.equal(await evaluate("$('installerBar').scrollWidth <= $('progress').clientWidth"), true, `Installer overflow: ${width}`);
              assert.equal(await evaluate("$('progressCells').hidden"), true);
            } else {
              const count = 20;
              assert.equal(await evaluate("$('progressCells').querySelectorAll('.filled').length"), Math.floor(percent / 100 * count));
            }
          }
          assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true, `Overflow: ${width}/${theme}/${style}`);
          if (screenshots && theme === 'Midnight' && width === 390) {
            await evaluate("secondsLeft = Math.round(totalSeconds * 0.58); state = 'paused'; setMode('timer'); render()");
            const screenshot = await send('Page.captureScreenshot', { format: 'png' });
            fs.writeFileSync(path.join(screenshots, `${style}-${width}.png`), Buffer.from(screenshot.data, 'base64'));
          }
        }
        assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true, `Overflow: ${width}/${theme}`);
        assert.equal(await evaluate(`(() => {
          const display = $('display').getBoundingClientRect();
          const card = document.querySelector('.card').getBoundingClientRect();
          return display.left >= card.left && display.right <= card.right;
        })()`), true);
        if (screenshots && (width === 390 || width === 1280)) {
          const screenshot = await send('Page.captureScreenshot', { format: 'png' });
          fs.writeFileSync(path.join(screenshots, `${theme}-${width}.png`), Buffer.from(screenshot.data, 'base64'));
        }
      }
    }
    assert.deepEqual(errors, [], 'Browser runtime errors');
    console.log('Passed browser state, clock, themes, progress styles, persistence, keyboard, and responsive checks.');
    if (screenshots) console.log(`Screenshots: ${screenshots}`);
    await send('Browser.close');
  } finally {
    if (socket) socket.close();
    if (browser.exitCode === null) {
      await new Promise(resolve => {
        const timeout = setTimeout(() => { browser.kill(); resolve(); }, 3000);
        browser.once('exit', () => { clearTimeout(timeout); resolve(); });
      });
    }
    server.close();
    // Only remove the temporary profile created by this run.
    if (path.dirname(profile) === path.resolve(os.tmpdir()) && path.basename(profile).startsWith('focus-browser-')) {
      await fs.promises.rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    }
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
