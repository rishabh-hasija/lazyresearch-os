"""Exercise the shipped navigation handler without browser pixels or timers."""

import shutil
import subprocess

import pytest

from lazyresearch.ui.app import NAVIGATION_SCROLL


def test_only_changed_workspace_page_scrolls_and_listener_is_not_duplicated():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable for the optional JavaScript behavior check")
    script = NAVIGATION_SCROLL.removeprefix("\n<script>").removesuffix("</script>\n")
    harness = r"""
const assert = require("node:assert/strict");
const listeners = new Set();
const scrolls = [];
global.window = {};
global.document = {
    addEventListener(name, fn, capture) {
        assert.equal(name, "click"); assert.equal(capture, true); listeners.add(fn);
    },
    removeEventListener(name, fn, capture) { listeners.delete(fn); },
    querySelector(selector) {
        assert.equal(selector, '[data-testid="stMain"]');
        return {scrollTo: options => scrolls.push(options)};
    }
};
"""
    checks = r"""
assert.equal(listeners.size, 1);
const click = kind => [...listeners][0]({target: {
    closest(selector) {
        assert.equal(selector, ".st-key-workspace-navigation button");
        return kind === null ? null : {getAttribute: () => kind};
    }
}});
// Evidence, filters, feedback and refresh controls are outside navigation.
click(null);
click("primary"); // Re-selecting the current page also leaves scroll alone.
assert.equal(scrolls.length, 0);
click("tertiary");
assert.equal(scrolls.length, 1);
assert.deepEqual(scrolls[0], {top: 0, left: 0, behavior: "instant"});
"""
    subprocess.run(
        [node, "-e", harness + script + script + checks], check=True, capture_output=True
    )
