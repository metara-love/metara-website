#!/usr/bin/env python3
"""
merge-tree-into-site.py
========================

WHAT THIS DOES
--------------
Takes the standalone, self-contained tree page (metara-tree-interactive.html
-- the SOURCE OF TRUTH for all tree content, styling and behaviour) and
produces TWO files that are safe to deploy alongside the real METARA
website (index.html): the merged index.html itself, and a companion
metara-tree.js that MUST be deployed in the same directory as it. The
tree is wired up as a full-screen overlay triggered by the "Explore the
vision" button. Splitting the JS into its own file (rather than inlining
it, which would be simpler) is not a style choice -- it is required for
the tree to actually run at all on the deployed site. See bug (e) below.

It does this by:
  1. Pulling the <style> and <body> content out of the standalone file.
  2. Prefixing every CSS class the tree defines with "mt-", and every
     structural id, so nothing in the tree can ever collide with a class
     or id the real website already uses (see NAMESPACING below -- this
     is not optional, real collisions WILL happen without it).
  3. Rewriting a short list of JS string literals that reference class
     names directly (see JS_STRING_LITERAL_FIXES below) -- the automatic
     class-attribute renaming above cannot see inside JS strings, so this
     list has to be kept in sync by hand.
  4. Re-scoping every CSS rule that targets a bare HTML element (section,
     footer, h1/h2/h3, body, html, *, ::selection) so it only applies
     inside the tree overlay, never site-wide.
  5. Adapting the scroll-tracking script from window-scroll to
     container-scroll, because on the real site the tree scrolls inside
     its own fixed-position overlay, not the page itself.
  6. Wrapping everything in the overlay markup + open/close JS, and
     splicing it into a copy of the site's real index.html, right before
     </head> and </body>, plus wiring the "Explore the vision" button.

WHY THIS EXISTS (read this before touching the tree's website integration)
----------------------------------------------------------------------
Earlier attempts to do this merge by hand, live, in a chat, produced two
real bugs that were invisible from reading the code and only showed up
when actually clicking around in a browser:

  (a) A structural nesting bug: the body was split at the wrong <script>
      tag (there are THREE scripts in the tree -- one for the Platonic
      solids ring sits early, right after the hero mark, not at the end),
      which silently pushed half the tree outside its scroll container.

  (b) A CSS specificity bug: overriding "The METARA Collective" title's
      font-size with a single-class selector (.trunk-title) silently lost
      to the branch cards' existing ".pillar-head-text h3" rule, because
      class+element beats a single class in CSS specificity regardless of
      which rule appears later in the file. The change looked correct in
      the source and did nothing in the browser.

  (c) A timing bug in the overlay-open code itself, found while building
      THIS pipeline script: the original fix for "the chapter-rail dots
      need real layout to position themselves, but the overlay is
      display:none until opened" was to wait two nested
      requestAnimationFrame callbacks before recalculating. It shipped,
      and looked fine when clicked through by hand. An automated check
      later showed it doesn't reliably work -- the function runs, throws
      no error, and still computes every dot's position as 0, because the
      double-rAF isn't a real guarantee that layout has been flushed. The
      fix was to read `overlay.offsetHeight` once (which forces a
      synchronous layout) immediately before recalculating, rather than
      hoping enough time has passed. See mfOpenTreeOverlay's comment
      below for the fixed version -- if you ever see chapter-rail dots
      all stuck at the top when the overlay first opens, this is why.

  (d) An unexplained opacity bug, also found while building this pipeline:
      the chapter-rail tip labels (".tip", shown next to a dot on hover)
      were staying permanently visible instead of hidden-until-hovered,
      even though their CSS rule (opacity:0 by default) was confirmed --
      via direct browser inspection using Chrome DevTools Protocol's own
      getMatchedStylesForNode AND getComputedStyleForNode, not just
      reading the source -- to be present, correctly parsed, and the
      only matching rule for that property. Bisecting the site's CSS
      rule-by-rule traced it to a single, completely unrelated rule: the
      site's decorative starfield background (".stars::before,
      .stars::after", a dozen-plus chained radial-gradient()
      backgrounds). That rule shares no selector, property, or element
      with the tip label. Why it affects the tip's computed opacity was
      not fully root-caused -- it behaves like a browser rendering-engine
      edge case rather than a genuine CSS cascade bug in this project's
      own code. `!important` on both the tip's hidden (opacity:0) and
      revealed (opacity:1, on hover/active) rules was necessary but not
      sufficient on its own: testing (including under a real, non-headless
      Chromium via xvfb, to rule out a headless-only artifact) showed the
      tip stays stuck fully visible until the very first genuine mouse
      movement anywhere on the page -- not necessarily over the tip or
      even the chapter-rail -- after which it behaves correctly for the
      rest of the session. This points to Chromium deferring some part of
      initial style recalculation (plausibly related to the cost of the
      site's starfield background layer) until the first real input
      event forces it to catch up, rather than a cascade problem as such.
      In practice this means real visitors will essentially never notice
      it: the overlay only appears after they've just clicked a button,
      so genuine mouse movement follows within a fraction of a second.
      It only shows up as "stuck" in automated checks that open the
      overlay and inspect styles without ever moving the mouse -- which
      is exactly how this was found. If you're writing an automated test
      against this tree, do a trivial `page.mouse.move(x, y)` after
      opening the overlay before asserting on any opacity/visibility
      state, or you'll chase a ghost.

  (e) The most consequential one, found only by actually reading the real
      site's deployment config (_headers), not by testing at all: the
      site enforces a Content-Security-Policy with a script-src that has
      NO 'unsafe-inline' -- only 'self', a couple of external domains for
      Cloudflare's own scripts, and a fixed allowlist of sha256 hashes for
      a handful of pre-existing inline scripts. This CSP is a response
      HEADER, only sent when the site is actually served over HTTP by
      Cloudflare Pages -- it does nothing when a file is opened locally
      via file://. That means an earlier version of this merge, which
      pasted the tree's JS in as inline <script> tags AND used inline
      onclick="" attributes on the open/close buttons, passed every local
      browser check in this file (including the automated ones) while
      being completely non-functional the moment it was actually
      deployed -- both the inline <script> blocks and the onclick
      attributes would be silently dropped by the browser, with no
      visible error to a casual visitor (just a button that does nothing).
      The fix, reflected in this script: the tree's entire JS is written
      to a separate metara-tree.js file and loaded via
      <script src="metara-tree.js" defer>, which 'self' already permits
      with no CSP changes needed; and both buttons are wired up with
      addEventListener from inside that file (targeting
      #mt-explore-btn / .mt-close-btn) instead of onclick="" attributes,
      since 'unsafe-hashes' would need those exact attribute contents
      hashed and allowlisted too. If you ever add a NEW inline
      onclick=""/onload="" anywhere in the tree, or move JS back inline,
      it will look completely fine in every local test and then silently
      do nothing in production -- always check whatever the real
      deployment's CSP actually says, not just whether it works when you
      open the file yourself.

  (f) A self-inflicted one, worth recording because it's a direct
      demonstration of a warning this file already gave: scope_global_
      selectors() used to convert the standalone source's global
      "html{scroll-behavior:smooth;}" rule by matching that exact,
      complete string. When a later fix added overflow-x:hidden to that
      same rule (see the standalone file's own header notes on the
      mobile horizontal-scroll bug), the rule's text no longer matched
      the hardcoded string byte-for-byte, so it slipped through
      completely unscoped and would have leaked onto the real site's
      <html> element. find_risky_selectors()'s warning output is what
      caught it, not a passing test -- it printed a warning rather than
      failing outright, so it's easy to miss if you don't read this
      script's stderr output after running it. The fix was to match the
      SELECTOR via regex (any "html{...}", regardless of contents)
      instead of the whole rule's exact text. The general lesson, since
      it applies to every exact-string match in this file, not just this
      one: matching a full rule's text is fragile to any future edit of
      that rule's contents; matching by selector and capturing the
      declarations is not. If you add a new global-selector scoping step
      here, prefer the regex-capture pattern over a literal string match.

Neither of these would be caught by reading the CSS/HTML -- they only
show up as a rendered page. Whoever (whatever) is maintaining this next:
treat "I edited the CSS/JS" and "I confirmed it renders correctly in an
actual browser" as two separate, both-required steps. This script's
build_and_verify() companion checklist at the bottom is there for exactly
that reason -- use it, or something equivalent, every time.

NAMESPACING CONVENTION
-----------------------
Every CSS class the tree defines gets an "mt-" prefix when merged into the
site (e.g. .chip -> .mt-chip). This is because the real site already has
its own .chip, .hero, .active, .desc, .name, .sub, .type classes with
completely different meanings -- confirmed by direct inspection, not
hypothetical. Structural ids (journey, sideRail, railFill, sunlight,
canopy, branches, trunk, roots, soil) get the same "mt-" treatment even
though no current collision was found, defensively, since the site will
keep growing.

The *standalone* file (metara-tree-interactive.html) intentionally does
NOT use the mt- prefix -- it's meant to be readable and self-contained on
its own. The prefixing only happens in this script, on the way into the
merged site file. This means: always edit the standalone file, never the
merged file, then re-run this script.

JS_STRING_LITERAL_FIXES
------------------------
Renaming `class="foo"` to `class="mt-foo"` is a simple attribute rewrite.
But `element.classList.toggle('foo')` in a <script> block is just a JS
string -- nothing about it looks like a CSS class to a regex, so it does
NOT get renamed automatically, and silently stops matching the (now
renamed) CSS. Every time you add new interactive JS to the standalone
source that touches classList (add/remove/toggle/contains) or
querySelector(All) with a class selector, you must add the corresponding
find/replace pair below, or the merged version will look identical to
the eye and simply not work (this exact bug happened twice already in
this project's history -- 'open'/'active'/'.chapter-dot' all needed it).

HOW TO USE
----------
    python3 merge-tree-into-site.py \\
        --tree metara-tree-interactive.html \\
        --site index.html \\
        --out index-with-tree-overlay.html

Then open --out in a real browser and run through the verification
checklist in verify_checklist() at the bottom of this file before
calling it done.
"""

import re
import os
import argparse
import sys


# ---------------------------------------------------------------------------
# Known JS string literals that reference (un-prefixed) tree class names.
# Keep this list in sync with the standalone source's <script> blocks.
# Format: (exact substring to find, exact substring to replace it with)
# ---------------------------------------------------------------------------
JS_STRING_LITERAL_FIXES = [
    ("card.classList.toggle('open')", "card.classList.toggle('mt-open')"),
    ("dot.classList.add('active')", "dot.classList.add('mt-active')"),
    ("dot.classList.remove('active')", "dot.classList.remove('mt-active')"),
    ("document.querySelectorAll('.chapter-dot')", "document.querySelectorAll('.mt-chapter-dot')"),
]

# Structural ids that get the mt- prefix even though (at time of writing)
# nothing on the live site collides with them. Add to this list if you
# introduce new top-level ids in the standalone source.
STRUCTURAL_ID_MAP = {
    'journey': 'mt-journey',
    'sideRail': 'mt-sideRail',
    'railFill': 'mt-railFill',
    'sunlight': 'mt-sunlight',
    'canopy': 'mt-canopy',
    'branches': 'mt-branches',
    'trunk': 'mt-trunk',
    'roots': 'mt-roots',
    'soil': 'mt-soil',
}

# The site's own font <link> (as of this build) -- we patch its weight
# list rather than loading Google Fonts twice. If the site's font link
# changes, update OLD_FONT_LINK to match or this step is silently skipped.
OLD_FONT_LINK = (
    'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400'
    '&family=Inter:wght@300;400;500&family=Philosopher:ital,wght@0,400;0,700;1,400&display=swap'
)
NEW_FONT_LINK = (
    'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400;1,600'
    '&family=Inter:wght@300;400;500;600&family=Philosopher:ital,wght@0,400;0,700;1,400&display=swap'
)

OLD_BUTTON = '<a class="btn btn-ghost" href="#about">Explore the vision</a>'
NEW_BUTTON = '<a class="btn btn-ghost" href="#about" id="mt-explore-btn">Explore the vision</a>'

OVERLAY_STRUCTURAL_CSS = '''
  #mt-overlay{ position:fixed; inset:0; z-index:9999; }
  #mt-scroll{ position:absolute; inset:0; overflow-y:auto; -webkit-overflow-scrolling:touch; }
  .mt-close-btn{
    position:fixed; top:22px; right:26px; z-index:10001;
    width:40px; height:40px; border-radius:50%;
    background:rgba(22,31,56,0.75); border:1px solid rgba(245,243,236,0.25);
    color:#f5f3ec; font-size:1.1rem; line-height:1; cursor:pointer;
    display:flex; align-items:center; justify-content:center;
    transition:background .25s ease, border-color .25s ease, transform .25s ease;
    backdrop-filter:blur(6px);
  }
  .mt-close-btn:hover{background:rgba(35,47,84,0.9); border-color:#d4b87e; transform:rotate(90deg);}
  @media (max-width:900px){
    .mt-close-btn{top:14px; right:14px;}
    #mt-scroll{ scrollbar-width:none; -ms-overflow-style:none; }
    #mt-scroll::-webkit-scrollbar{ display:none; width:0; height:0; }
  }
'''

OVERLAY_OPEN_CLOSE_JS_BODY = '''

// Wired to the site's "Explore the vision" button (see NEW_BUTTON above).
var mtScrollLockY = 0;

function mfOpenTreeOverlay(evt){
  if (evt) evt.preventDefault();
  var overlay = document.getElementById('mt-overlay');
  if (!overlay) return;
  mtScrollLockY = window.scrollY;
  overlay.hidden = false;
  // Lock background scroll without losing scroll position (iOS-safe).
  document.body.style.position = 'fixed';
  document.body.style.top = (-mtScrollLockY) + 'px';
  document.body.style.left = '0';
  document.body.style.right = '0';
  // The overlay was display:none a moment ago, so anything inside it
  // (offsetHeight, getBoundingClientRect) would read as zero if we
  // measured it right now -- browsers don't compute layout for hidden
  // content. Reading offsetHeight here forces the browser to flush
  // layout synchronously before mtRecalcTree measures anything.
  //
  // A double-requestAnimationFrame version of this was tried first and
  // actually shipped -- it looked reasonable and worked when tested by
  // hand, but a later automated check showed it can fire before the
  // browser has actually laid the overlay out, silently leaving every
  // chapter-rail dot stuck at position 0 with no error thrown anywhere.
  // Forcing the reflow synchronously removes that timing gamble
  // entirely, and is the reason this project's testing checklist (see
  // verify_checklist() below) insists on checking actual rendered
  // positions/values in a browser, not just "the function ran with no
  // error" -- that alone was not enough to catch this.
  overlay.offsetHeight;
  if (window.mtRecalcTree) window.mtRecalcTree();
}

function mfCloseTreeOverlay(){
  var overlay = document.getElementById('mt-overlay');
  if (!overlay) return;
  overlay.hidden = true;
  document.body.style.position = '';
  document.body.style.top = '';
  document.body.style.left = '';
  document.body.style.right = '';
  window.scrollTo(0, mtScrollLockY);
}

document.addEventListener('keydown', function(e){
  var overlay = document.getElementById('mt-overlay');
  if (overlay && !overlay.hidden && e.key === 'Escape') mfCloseTreeOverlay();
});

// Wired here via addEventListener rather than inline onclick="" attributes
// on the button markup -- the site's CSP (script-src) permits this
// same-origin script file, but does NOT include our handlers in its
// 'unsafe-hashes' allowlist, so inline onclick="" attributes would be
// silently blocked in production even though they work fine when this
// file is opened locally (CSP headers only apply when actually served
// by Cloudflare Pages). See CSP_NOTE in merge-tree-into-site.py's
// build() function for the full explanation.
(function(){
  var openBtn = document.getElementById('mt-explore-btn');
  if (openBtn) openBtn.addEventListener('click', mfOpenTreeOverlay);

  var closeBtn = document.querySelector('.mt-close-btn');
  if (closeBtn) closeBtn.addEventListener('click', mfCloseTreeOverlay);
})();
'''


def extract_balanced(text, start_idx, open_ch='{', close_ch='}'):
    """Return the index just past the brace that balances the one at start_idx."""
    depth = 0
    i = start_idx
    while i < len(text):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("Unbalanced braces starting at %d" % start_idx)


def rename_css_and_classes(style, body, css_classes):
    """Prefix every known CSS class with mt- in both the stylesheet and
    the HTML class="" attributes. Longest-name-first avoids partial
    matches (e.g. renaming "chip" inside "chip-row" by accident)."""
    ordered = sorted(css_classes, key=len, reverse=True)

    for cls in ordered:
        style = re.sub(r'\.' + re.escape(cls) + r'\b', '.mt-' + cls, style)

    def repl(m):
        tokens = m.group(1).split()
        new_tokens = ['mt-' + t if t in css_classes else t for t in tokens]
        return 'class="' + ' '.join(new_tokens) + '"'
    body = re.sub(r'class="([^"]*)"', repl, body)

    return style, body


def namespace_structural_ids(body):
    for old, new in STRUCTURAL_ID_MAP.items():
        body = re.sub(r'id="' + old + r'"', 'id="' + new + '"', body)
        body = re.sub(r'data-target="' + old + r'"', 'data-target="' + new + '"', body)
        body = re.sub(r"getElementById\('" + old + r"'\)", "getElementById('" + new + "')", body)
    return body


def apply_js_string_literal_fixes(body):
    for old, new in JS_STRING_LITERAL_FIXES:
        if old not in body:
            print("  WARNING: expected JS pattern not found (source may have "
                  "changed, or this fix is now obsolete):\n    %r" % old,
                  file=sys.stderr)
            continue
        body = body.replace(old, new)
    return body


def scope_global_selectors(css):
    """Rescope every bare-element / global CSS rule so it can never leak
    outside #mt-overlay onto the rest of the site. If you add a new
    top-level (non-class, non-id) selector to the standalone source's
    <style> block, add it here too -- otherwise it WILL apply to the
    entire website, not just the tree."""

    # :root -> #mt-overlay (so the tree's CSS variables don't touch the
    # site's own, even if some happen to share a name).
    css = css.replace(':root{', '#mt-overlay{', 1)

    # body{...} rules get folded into #mt-overlay{...} (the tree's own
    # "body-equivalent" root), rather than touching the real <body>.
    body_m = re.search(r'\bbody\{([^}]*)\}', css)
    if body_m:
        body_rules = body_m.group(1)
        css = css[:body_m.start()] + css[body_m.end():]
        css = re.sub(r'(#mt-overlay\{[^}]*)\}', r'\1' + body_rules + '}', css, count=1)

    css = css.replace('*{box-sizing:border-box;}',
                       '#mt-overlay, #mt-overlay *{box-sizing:border-box;}')
    # Redirect any html{...} rule to #mt-scroll{...} rather than matching
    # exact hardcoded rule text. The previous version only replaced the
    # literal strings 'html{scroll-behavior:smooth;}' and
    # 'html{scroll-behavior:auto;}' -- when a later edit to the standalone
    # source changed that rule's content (adding overflow-x:hidden, to fix
    # a real mobile horizontal-scroll bug), the exact string no longer
    # matched and the rule slipped through completely unscoped, leaking
    # onto the real site's <html> element. find_risky_selectors() below
    # is what caught it -- but a regex that matches the SELECTOR rather
    # than the whole rule's exact text is what actually prevents it from
    # recurring. #mt-scroll is the right target regardless of what
    # html{...} contains: it's the tree's own scrolling container inside
    # the overlay, playing the same role there that <html> plays in the
    # standalone page.
    css = re.sub(r'(?<![\w.#-])html\{([^}]*)\}', r'#mt-scroll{\1}', css)
    css = css.replace(
        "h1,h2,h3,.mt-display{font-family:'Philosopher', serif; font-weight:400; margin:0;}",
        "#mt-overlay h1, #mt-overlay h2, #mt-overlay h3, #mt-overlay .mt-display"
        "{font-family:'Philosopher', serif; font-weight:400; margin:0;}"
    )
    css = css.replace('::selection{background:var(--gold); color:var(--deep);}',
                       '#mt-overlay ::selection{background:var(--gold); color:var(--deep);}')
    css = re.sub(r'(?<![\w.#-])section\{', '#mt-overlay section{', css)
    css = re.sub(r'(?<![\w.#-])footer\{', '#mt-overlay footer{', css)

    return css


def find_risky_selectors(css):
    """Sanity check: return any top-level selector that isn't scoped under
    #mt-overlay / .mt-. Used to catch new global leaks before they ship."""
    selectors = re.findall(r'([^{}]+)\{', css)
    risky = []
    for s in selectors:
        s = s.strip()
        if not s or s.startswith('@') or s.startswith('/*') or '/*' in s:
            continue
        for p in [p.strip() for p in s.split(',')]:
            if p.startswith('.mt-') or p.startswith('#mt-') or 'mt-' in p:
                continue
            if p in ('0%', '50%', '100%'):  # keyframe steps, harmless
                continue
            risky.append(p)
    return sorted(set(risky))


def adapt_scroll_to_container(body):
    """The standalone page tracks scroll via `window`. Inside the overlay,
    the tree scrolls inside its own #mt-scroll container instead (because
    the background page's scroll is locked while the overlay is open).
    This anchors on the rail-script's function names (docProgressRange /
    placeDots / onScroll), not exact whitespace, so minor edits to the
    source script (comments, formatting) don't break this step -- but a
    genuine rename of these functions will, loudly (see the assertion
    below), which is intentional: better a clear failure here than a
    silently broken merge.
    """
    marker = "var railFill = document.getElementById('mt-railFill');"
    if marker not in body:
        raise AssertionError(
            "Could not find the rail script's anchor line (%r). The "
            "standalone source's chapter-rail script has probably been "
            "restructured -- update adapt_scroll_to_container() in this "
            "pipeline to match the new code before re-running." % marker
        )

    body = body.replace(
        marker,
        "var scroller = document.getElementById('mt-scroll');\n  " + marker
    )
    body = body.replace(
        "journey.offsetHeight - window.innerHeight",
        "journey.offsetHeight - scroller.clientHeight"
    )
    body = body.replace(
        "function placeDots(){\n    var total = docProgressRange();\n    dots.forEach",
        "function placeDots(){\n    var total = docProgressRange();\n    "
        "var scrollerTop = scroller.getBoundingClientRect().top;\n    dots.forEach"
    )
    body = body.replace(
        "var top = target.getBoundingClientRect().top + window.scrollY;",
        "var top = target.getBoundingClientRect().top - scrollerTop + scroller.scrollTop;"
    )
    body = body.replace(
        "var progress = Math.min(1, Math.max(0, window.scrollY / total));",
        "var progress = Math.min(1, Math.max(0, scroller.scrollTop / total));"
    )
    body = body.replace(
        "window.addEventListener('resize', function(){ placeDots(); onScroll(); });\n"
        "  placeDots();\n  onScroll();\n  window.addEventListener('scroll', onScroll, {passive:true});\n})();",
        "window.addEventListener('resize', function(){ placeDots(); onScroll(); });\n"
        "  scroller.addEventListener('scroll', onScroll, {passive:true});\n"
        "  placeDots();\n  onScroll();\n\n"
        "  // Exposed so the overlay opener can force a re-measure once the\n"
        "  // overlay actually has a layout (see mfOpenTreeOverlay below --\n"
        "  // this element is display:none until opened, so offsetHeight /\n"
        "  // getBoundingClientRect are meaningless before that).\n"
        "  window.mtRecalcTree = function(){ placeDots(); onScroll(); };\n})();"
    )
    return body


STYLE_BLOCK_COMMENT = '''
<!--
  ============================================================================
  METARA TREE OVERLAY -- this block and the matching one at the end of
  <body> (search for "METARA TREE OVERLAY MARKUP") are GENERATED by
  merge-tree-into-site.py from metara-tree-interactive.html. Do not
  hand-edit either block or the companion metara-tree.js file -- edit the
  standalone source and re-run that script instead. See its own header
  comment for the full explanation, including several real bugs (CSS
  specificity, layout timing, a CSP-driven total production failure) that
  were each invisible from reading the code and only showed up in an
  actual rendered/deployed browser.
  ============================================================================
-->
'''

OVERLAY_MARKUP_COMMENT = '''
<!--
  ============================================================================
  METARA TREE OVERLAY MARKUP -- GENERATED, see the matching comment near
  "<style id="mt-tree-styles">" in <head>. Source of truth:
  metara-tree-interactive.html. Regenerate with merge-tree-into-site.py.

  Quick orientation:
    - #mt-overlay is the full-screen fixed container, hidden by default
      via the plain HTML `hidden` attribute (not a class).
    - #mt-scroll is the actual scrolling element inside it -- the
      chapter-rail math in metara-tree.js reads #mt-scroll.scrollTop /
      .clientHeight, not window.scrollY.
    - The open/close buttons (#mt-explore-btn elsewhere on this page, and
      .mt-close-btn just below) are wired up via addEventListener from
      inside metara-tree.js, NOT inline onclick="" attributes -- this
      site's CSP (see _headers) blocks inline script execution including
      onclick handlers unless pre-hashed, and metara-tree.js is a
      same-origin file the CSP already allows via 'self'. If you ever see
      the button do nothing in production despite working locally, check
      the browser console for a CSP violation before anything else.
  ============================================================================
-->
'''


def build(tree_html, site_html):
    """Returns (site_html, tree_js) -- tree_js must be written to a
    same-origin metara-tree.js file, NOT inlined. See CSP_NOTE below."""
    style_m = re.search(r'<style>(.*?)</style>', tree_html, re.S)
    body_m = re.search(r'<body>(.*?)</body>', tree_html, re.S)
    if not style_m or not body_m:
        raise AssertionError("Could not find <style> or <body> in the standalone tree file.")
    style, body = style_m.group(1), body_m.group(1)

    css_classes = set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', style))

    style, body = rename_css_and_classes(style, body, css_classes)
    body = namespace_structural_ids(body)
    body = apply_js_string_literal_fixes(body)
    style = scope_global_selectors(style)

    risky = find_risky_selectors(style)
    if risky:
        print("WARNING: possibly unscoped global CSS selectors found: %s"
              % risky, file=sys.stderr)
        print("  These will leak onto the whole site unless they're "
              "intentional (e.g. deliberately targeting #mt-overlay "
              "descendants already).", file=sys.stderr)

    style = OVERLAY_STRUCTURAL_CSS + style
    body = adapt_scroll_to_container(body)

    # ------------------------------------------------------------------
    # CSP_NOTE: the real site's _headers file enforces a script-src CSP
    # with NO 'unsafe-inline' -- only 'self' plus a short allowlist of
    # pre-approved sha256 hashes for a couple of pre-existing inline
    # scripts. Any NEW inline <script> we paste in would be silently
    # blocked by the browser at runtime on the real deployed site, even
    # though it works perfectly when opened locally as a file (CSP
    # response headers only apply when actually served over HTTP by
    # Cloudflare Pages, not for file:// testing -- which is exactly why
    # this could ship, "work" in every local check, and then silently do
    # nothing in production). Rather than hash-listing our scripts (which
    # would need recomputing on every future edit -- fragile and easy to
    # forget), every <script> tag's content is pulled OUT of the HTML
    # entirely here and returned separately, to be written to a same-
    # origin metara-tree.js file and loaded via <script src="metara-tree.js"
    # defer></script> instead. 'self' already covers that with zero CSP
    # changes required, and it stays correct no matter how much the tree's
    # JS grows or changes.
    # ------------------------------------------------------------------
    script_bodies = re.findall(r'<script>(.*?)</script>', body, re.S)
    body_no_scripts = re.sub(r'<script>.*?</script>\s*', '', body, flags=re.S)
    tree_js = '\n\n'.join(s.strip() for s in script_bodies) + '\n'
    tree_js = ("/* metara-tree.js -- GENERATED by merge-tree-into-site.py.\n"
               " * Do not hand-edit; see that script's header comment.\n"
               " * Loaded as an external, same-origin script specifically so\n"
               " * it satisfies the site's script-src CSP ('self' is allowed,\n"
               " * new inline scripts are not). */\n\n") + tree_js
    tree_js += OVERLAY_OPEN_CLOSE_JS_BODY

    fragment = (
        OVERLAY_MARKUP_COMMENT +
        '<div id="mt-overlay" class="mt-overlay" hidden>\n'
        '  <button class="mt-close-btn" '
        'aria-label="Close tree view">&#10005;</button>\n'
        '  <div id="mt-scroll">\n' + body_no_scripts.strip() + '\n  </div>\n</div>\n'
        '<script src="metara-tree.js" defer></script>\n'
    )

    site = site_html
    if OLD_FONT_LINK in site:
        site = site.replace(OLD_FONT_LINK, NEW_FONT_LINK, 1)
    else:
        print("NOTE: site's font <link> didn't match the expected string -- "
              "skipped patching font weights. Check manually whether Inter "
              "600 / Cormorant italic 600 are available.", file=sys.stderr)

    if OLD_BUTTON in site:
        site = site.replace(OLD_BUTTON, NEW_BUTTON, 1)
    else:
        print("WARNING: 'Explore the vision' button markup didn't match "
              "the expected string -- the button was NOT wired up to open "
              "the overlay. Find the button in the site and add "
              "id=\"mt-explore-btn\" to it by hand (the click listener is "
              "attached by id from metara-tree.js, not an inline onclick, "
              "to stay CSP-compliant -- see CSP_NOTE above).",
              file=sys.stderr)

    style_block = STYLE_BLOCK_COMMENT + '\n<style id="mt-tree-styles">\n' + style + '\n</style>\n'
    site = site.replace('</head>', style_block + '</head>', 1)
    site = site.replace('</body>', fragment + '\n</body>', 1)

    return site, tree_js


def verify_checklist():
    """Not run automatically -- a reminder of what to actually click
    through in a real browser after regenerating the merged file. Reading
    the diff is not enough; see the module docstring for why."""
    return [
        "Open the file. Confirm the site looks completely normal BEFORE "
        "clicking anything (no layout shift, no color/font changes).",
        "Click 'Explore the vision'. Overlay should cover the full screen, "
        "hero centered, chapter-rail visible on the right, WITH the dots "
        "already spread down the rail at sensible positions -- if they're "
        "all bunched at the very top the instant it opens, that's the "
        "layout-timing bug from module docstring bug (c), not a new one.",
        "Scroll with the mouse wheel (not just programmatically -- real "
        "wheel events, since scroll-behavior:smooth can make programmatic "
        "scrollTop assignments animate instead of jump, which looks like "
        "a bug in testing but isn't one).",
        "Click a branch card ('Collaborations' etc). It should expand, "
        "chevron rotates to an X, full-height accent bar appears.",
        "Click 'The METARA Collective'. Should expand too, but WITHOUT a "
        "left accent bar, and with a visibly bigger title than the branch "
        "cards -- if either of those regress, check CSS specificity first "
        "(see module docstring bug (b)) before assuming the rule is missing.",
        "Move the mouse at all (anywhere on the page) before checking "
        "anything opacity/visibility related -- see module docstring bug "
        "(d). Then hover a chapter-rail dot, then click the text label "
        "that appears next to it (not just the dot) -- both should jump "
        "to that section.",
        "Click the close (X) button. Overlay should disappear, page "
        "should be at the exact scroll position you started from, and "
        "document.body.getAttribute('style') should be empty/null again.",
        "Open devtools console and confirm no real errors (an offline "
        "font-fetch 403 is expected and harmless in local testing).",
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tree', required=True, help='Path to metara-tree-interactive.html (source of truth)')
    p.add_argument('--site', required=True, help='Path to the real site index.html to merge into')
    p.add_argument('--out', required=True,
                    help='Path to write the merged HTML to. The companion '
                         'metara-tree.js is written in the SAME DIRECTORY as '
                         '--out (it must be served from the same origin as '
                         'the HTML -- see CSP_NOTE in build() for why it is '
                         'a separate file at all rather than inline).')
    args = p.parse_args()

    tree_html = open(args.tree, encoding='utf-8').read()
    site_html = open(args.site, encoding='utf-8').read()

    site_result, js_result = build(tree_html, site_html)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    js_path = os.path.join(out_dir, 'metara-tree.js')

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(site_result)
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(js_result)

    print("Wrote %s (%d bytes)." % (args.out, len(site_result)))
    print("Wrote %s (%d bytes)." % (js_path, len(js_result)))
    print("\nBoth files must be deployed together, in the same directory --")
    print("index.html references metara-tree.js by a relative, same-origin")
    print("<script src=\"metara-tree.js\">, which is what keeps it compliant")
    print("with the site's script-src CSP (see build()'s CSP_NOTE).")
    print("\nNow go verify it in an actual browser -- see verify_checklist() "
          "in this script for the specific things to click through.")


if __name__ == '__main__':
    main()
