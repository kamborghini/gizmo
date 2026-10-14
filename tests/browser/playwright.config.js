// The browser suite: every screen of Reactor in Chromium, at three sizes, in
// an invented world. Spec: docs/superpowers/specs/2026-10-14-browser-suite-design.md
const fs = require('fs');
const path = require('path');
const { defineConfig } = require('@playwright/test');

const ROOT = path.join(__dirname, '..', '..');
const PORT = Number(process.env.BROWSER_PORT || 8930);
const PY = process.env.PY || (fs.existsSync(path.join(ROOT, '.venv/bin/python')) ? '.venv/bin/python' : 'python');
const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /\.spec\.js$/,
  outputDir: path.join(RUN, 'results'),
  globalTeardown: path.join(__dirname, 'teardown.js'),
  timeout: 90000,
  expect: { timeout: 20000 },
  fullyParallel: true,
  workers: 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { outputFolder: path.join(RUN, 'report'), open: 'never' }]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: 'on-first-retry', reducedMotion: 'reduce', deviceScaleFactor: 1 },
  projects: [
    { name: 'phone', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'laptop', use: { viewport: { width: 1280, height: 800 } } },
    { name: 'wide', use: { viewport: { width: 1920, height: 1080 } } },
  ],
  webServer: {
    command: `${PY} tests/browser/serve.py`,
    cwd: ROOT,
    url: `http://127.0.0.1:${PORT}/`,
    timeout: 180000,
    reuseExistingServer: !process.env.CI,
    env: { PORT: String(PORT), BROWSER_RUN: RUN },
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
