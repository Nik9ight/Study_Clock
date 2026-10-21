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
    const audioFiles = { 'freesound_community-timer-with-chime-101253.mp3': 'audio/mpeg', 'start-chime.wav': 'audio/wav' };
    const chime = new URL(request.url, 'http://localhost').pathname.slice(1);
    if (Object.hasOwn(audioFiles, chime)) {
      response.setHeader('Content-Type', audioFiles[chime]);
      response.end(fs.readFileSync(path.join(__dirname, '..', chime)));
      return;
    }
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
    assert.equal(await evaluate('document.title'), '[░░░░░░░░] 0% · Focus');
    // Use an actual browser click to exercise its audio user-activation policy.
    const startButton = await evaluate("(() => { const r = $('playBtn').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()");
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, ...startButton });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, ...startButton });
    const audioStarted = await evaluate(`new Promise(resolve => {
      const until = Date.now() + 5000;
      const poll = () => {
        if (!sessionChime.paused && sessionChime.currentTime > 0) resolve(true);
        else if (Date.now() >= until) resolve(false);
        else setTimeout(poll, 50);
      };
      poll();
    })`);
    assert.equal(audioStarted, true, 'Start must play its audio file after a user click');
    assert.match(await evaluate('sessionChime.src'), /start-chime\.wav$/);
    assert.ok(await evaluate('sessionChime.duration > 0 && sessionChime.duration <= 1'), 'Start chime must last less than a second');
    assert.equal(await evaluate('sessionChime.error'), null, 'Chime must decode successfully');
    await evaluate(`window.chimeCalls = 0; window.actualChimePlay = sessionChime.play.bind(sessionChime);
      sessionChime.play = () => { window.chimeCalls++; window.chimeRemaining = secondsLeft; return window.actualChimePlay(); };
      pause();`);
    assert.equal(await evaluate('sessionChime.paused'), true);
    await evaluate('start()');
    assert.equal(await evaluate('window.chimeCalls'), 0, 'Resume must not replay the start chime');
    await evaluate('deadline = Date.now() + 12000; tick()');
    assert.equal(await evaluate('window.chimeCalls'), 0, 'End cue must wait for the final ten seconds');
    // Let the browser's own timer run through 00:10 and zero without forcing ticks.
    assert.equal(await evaluate(`new Promise(resolve => {
      const until = Date.now() + 5000;
      const poll = () => {
        if (window.chimeCalls) resolve(true);
        else if (Date.now() >= until) resolve(false);
        else setTimeout(poll, 50);
      };
      poll();
    })`), true, 'End cue must start while the countdown runs');
    assert.equal(await evaluate('window.chimeRemaining'), 10, 'End cue must start at exactly 00:10 remaining');
    assert.equal(await evaluate('window.chimeCalls'), 1, 'End cue must start once during the countdown');
    assert.match(await evaluate('sessionChime.src'), /timer-with-chime-101253\.mp3$/);
    assert.equal(await evaluate(`new Promise(resolve => {
      const until = Date.now() + 5000;
      const poll = () => {
        if (!sessionChime.paused && sessionChime.currentTime > 0) resolve(true);
        else if (Date.now() >= until) resolve(false);
        else setTimeout(poll, 50);
      };
      poll();
    })`), true, 'Original end recording must decode and play');
    const endPlaybackPosition = await evaluate('sessionChime.currentTime');
    assert.equal(await evaluate(`new Promise(resolve => {
      const until = Date.now() + 12000;
      const poll = () => {
        if (state === 'completed') resolve(true);
        else if (Date.now() >= until) resolve(false);
        else setTimeout(poll, 50);
      };
      poll();
    })`), true, 'The countdown must finish naturally');
    assert.equal(await evaluate('secondsLeft'), 0);
    assert.ok(await evaluate('sessionChime.currentTime') >= endPlaybackPosition, 'Completion must not rewind the recording');
    assert.equal(await evaluate('window.chimeCalls'), 1, 'Completion must not restart the countdown chime');
    console.log('PASS: real countdown started the MP3 at 00:10, reached zero, and played the end cue once without rewinding.');
    await evaluate('start()');
    assert.equal(await evaluate('window.chimeCalls'), 2, 'Next session must chime');
    await evaluate('reset()');
    assert.equal(await evaluate('sessionChime.paused'), true, 'Reset must stop the chime');
    await evaluate("$('testChimeBtn').click()");
    assert.equal(await evaluate('window.chimeCalls'), 3, 'Settings must allow sound testing');
    assert.match(await evaluate('sessionChime.src'), /\.mp3$/);
    await evaluate("$('testStartChimeBtn').click()");
    assert.equal(await evaluate('window.chimeCalls'), 4);
    assert.match(await evaluate('sessionChime.src'), /start-chime\.wav$/);
    await evaluate(`sessionChime.play = () => Promise.reject(new DOMException('Blocked', 'NotAllowedError')); playChime()`);
    assert.equal(await evaluate("$('soundStatus').hidden"), false);
    assert.match(await evaluate("$('soundStatus').textContent"), /blocked/);
    await evaluate('sessionChime.play = window.actualChimePlay; reset(); sessionsCompleted = 0; playChime()');
    assert.equal(await evaluate("$('soundStatus').hidden"), true);
    await evaluate('stopChime()');
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
    assert.match(await evaluate('document.title'), /100% · Done$/);
    assert.equal(await evaluate("$('progress').getAttribute('aria-valuenow')"), '100');
    assert.equal(await evaluate("$('progressCells').querySelectorAll('.filled').length"), 20);
    assert.equal(await evaluate('sessionsCompleted'), 1);
    assert.equal(await evaluate('dailyRemainingSeconds()'), 6000);
    await evaluate("$('playBtn').click(); $('timerTab').click(); $('playBtn').click()");
    assert.equal(await evaluate('state'), 'paused');
    assert.equal(await evaluate("$('playBtn').textContent"), 'Resume');
    assert.equal(await evaluate("$('progressStatus').textContent"), 'PAUSED');
    assert.match(await evaluate('document.title'), /% · Paused$/);
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

    await evaluate("start(); $('notesInput').focus(); $('notesInput').value = 'Review chapter 3\\nWrite down questions'; $('notesInput').dispatchEvent(new Event('input'))");
    const noteDeadline = await evaluate('deadline');
    await send('Input.dispatchKeyEvent', { type: 'keyDown', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
    assert.equal(await evaluate('state'), 'running', 'Typing spaces must not pause the timer');
    assert.equal(await evaluate('deadline'), noteDeadline);
    await evaluate("$('remindersTab').click(); $('reminderInput').value = '   '; $('reminderForm').requestSubmit()");
    assert.equal(await evaluate('reminders.length'), 0);
    await evaluate("$('reminderInput').value = 'Review <img src=x onerror=alert(1)>'; $('reminderForm').requestSubmit()");
    assert.equal(await evaluate("$('reminderList').querySelector('img')"), null);
    assert.equal(await evaluate("$('reminderList').querySelector('span').textContent"), 'Review <img src=x onerror=alert(1)>');
    await evaluate("$('reminderList').querySelector('input').click(); $('reminderInput').value = 'Take a short break'; $('reminderForm').requestSubmit(); pause()");
    const notesBeforeReload = await evaluate("$('notesInput').value");
    await send('Page.reload');
    await new Promise(resolve => setTimeout(resolve, 500));
    assert.equal(await evaluate("$('notesInput').value"), notesBeforeReload);
    assert.equal(await evaluate('reminders.length'), 2);
    assert.equal(await evaluate('reminders[0].done'), true);
    await evaluate("$('remindersTab').click(); $('reminderList').querySelector('button').click()");
    assert.equal(await evaluate('reminders.length'), 1);
    assert.equal(await evaluate('reminders[0].text'), 'Take a short break');
    await evaluate("$('reminderList').querySelector('input').click(); reset()");
    assert.equal(await evaluate('reminders[0].done'), true, 'Timer reset must retain reminders');
    await evaluate("$('notesTab').focus()");
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    assert.equal(await evaluate("$('remindersTab').getAttribute('aria-selected')"), 'true');
    await evaluate("$('notesTab').click(); $('notesInput').value = 'Review chapter 3\\nWrite down questions'; $('notesInput').dispatchEvent(new Event('input'))");
    // Exercise storage failures without losing the in-memory draft.
    await evaluate("window.originalStorageSet = Storage.prototype.setItem; Storage.prototype.setItem = () => { throw new Error('Storage full'); }; $('notesInput').dispatchEvent(new Event('input'))");
    assert.match(await evaluate("$('scratchStatus').textContent"), /Could not save/);
    await evaluate("Storage.prototype.setItem = window.originalStorageSet; saveScratchpad()");
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
            assert.match(await evaluate('document.title'), new RegExp(`\\] ${percent}% · `));
            assert.doesNotMatch(await evaluate('document.title'), /\d{2}:\d{2}/);
            if (style === 'ASCII') {
              assert.equal(await evaluate("$('asciiBar').textContent.length"), 32);
              assert.equal(await evaluate("$('asciiBar').scrollWidth <= $('progress').clientWidth"), true, `ASCII overflow: ${width}`);
              if (percent === 100) assert.equal(await evaluate("$('asciiBar').textContent"), '[' + '='.repeat(30) + ']');
            } else if (style === 'Installer') {
              const filled = Math.floor(percent / 100 * 28);
              const tabFilled = Math.floor(percent / 100 * 8);
              assert.ok((await evaluate('document.title')).startsWith('[' + '█'.repeat(tabFilled) + '░'.repeat(8 - tabFilled) + ']'));
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
    await evaluate("reset(); start()");
    const originalDeadline = await evaluate('deadline');
    for (const [width, height] of [[280, 600], [320, 480], [390, 600], [700, 400], [900, 500], [1280, 720], [1920, 1080], [440, 300]]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
      for (const view of ['timer', 'clock']) {
        await evaluate(`setMode('${view}')`);
        for (const settingsOpen of [false, true]) {
          await evaluate(`$('settings').hidden = ${!settingsOpen}; $('settingsBtn').setAttribute('aria-expanded', '${settingsOpen}')`);
          const layout = await evaluate(`(() => {
            const card = document.querySelector('.card').getBoundingClientRect();
            const display = $('display').getBoundingClientRect();
            const overflow = [...document.querySelectorAll('button, select, input, textarea')].filter(el => {
              const r = el.getBoundingClientRect();
              return r.width && (r.left < 0 || r.right > innerWidth + 1 || r.width < 24);
            }).map(el => el.id);
            const remaining = document.querySelector('.remaining').getBoundingClientRect();
            const controls = document.querySelector('.controls').getBoundingClientRect();
            return { footerOverlap: remaining.right > controls.left && remaining.bottom > controls.top && remaining.top < controls.bottom,
              horizontal: document.documentElement.scrollWidth > innerWidth,
              top: card.top + scrollY, height: document.documentElement.scrollHeight,
              textFits: $('display').scrollWidth <= display.width + 1, overflow };
          })()`);
          assert.equal(layout.horizontal, false, `Horizontal overflow at ${width}x${height}`);
          assert.equal(layout.footerOverlap, false, `Footer overlap at ${width}x${height}`);
          assert.ok(layout.top >= 0, `Unreachable top at ${width}x${height}`);
          assert.equal(layout.textFits, true, `Clock/timer clipped at ${width}x${height}`);
          assert.deepEqual(layout.overflow, [], `Clipped controls at ${width}x${height}`);
          if (!settingsOpen && width >= 700 && height >= 600) {
            assert.ok(layout.height <= height + 1, `Unnecessary scrolling at ${width}x${height}: ${layout.height}`);
          }
          await evaluate("window.scrollTo(0, document.documentElement.scrollHeight)");
          assert.equal(await evaluate("document.querySelector('.card').getBoundingClientRect().bottom <= innerHeight + 1"), true, 'Bottom controls must remain reachable');
          await evaluate('window.scrollTo(0, 0)');
        }
      }
      assert.equal(await evaluate('state'), 'running');
      assert.equal(await evaluate('deadline'), originalDeadline);
      if (screenshots) {
        await evaluate("$('settings').hidden = true; $('settingsBtn').setAttribute('aria-expanded', 'false'); setMode('timer')");
        const screenshot = await send('Page.captureScreenshot', { format: 'png' });
        fs.writeFileSync(path.join(screenshots, `Responsive-${width}x${height}.png`), Buffer.from(screenshot.data, 'base64'));
      }
    }
    await evaluate('pause()');
    assert.deepEqual(errors, [], 'Browser runtime errors');
    console.log('Passed browser state, clock, themes, notes, reminders, persistence, keyboard, and responsive checks.');
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
