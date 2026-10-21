"""Exercise public status rendering without requiring a browser or admin session."""

import shutil
import subprocess

import pytest

from ingest.validate import PROJECT_ROOT

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is needed for the frontend behavior check")
def test_public_health_renders_active_mode_before_admin_login() -> None:
    script = (PROJECT_ROOT / "src/serving/static/app.js").read_text(encoding="utf-8")
    # Run the actual status functions in a small DOM boundary. No app initialization
    # or authenticated endpoint is available, matching a fresh public demo visit.
    health = script[script.index("  function loadHealth()") : script.index("  function loadStats(")]
    rendering = script[
        script.index("  function modeLabel(") : script.index("  function loadRuntime(")
    ]
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const nodes = new Map();
const byId = id => {
  if (!nodes.has(id)) nodes.set(id, {
    textContent: id === 'activeModeLabel' ? '讀取模式…' : '',
    setAttribute(key, value) { this[key] = value; }
  });
  return nodes.get(id);
};
let status;
const context = vm.createContext({
  byId,
  api: async path => {
    assert.equal(path, '/api/health');
    return status;
  },
  document: { querySelector: () => null, activeElement: null },
  valueText: value => value == null ? '—' : String(value),
  announce: message => { throw new Error(message); },
  runtimeRequestActive: false
});
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
(async () => {
  for (const [mode, label] of [['offline', '離線規則'], ['online', '線上 API']]) {
    status = { demo: mode === 'offline', mode: {
      active_mode: mode, default_mode: 'auto', online_configured: mode === 'online'
    }};
    await context.loadHealth();
    assert.equal(byId('activeModeLabel').textContent, label);
    assert.equal(byId('modeShortcut')['data-mode'], mode);
    assert.equal(byId('demoBanner').hidden, mode !== 'offline');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [NODE, "-e", harness],
        input=health + rendering,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
