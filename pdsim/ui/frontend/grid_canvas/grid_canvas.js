/*
 * grid_canvas.js -- the page of the pdsim grid component `pdsim_grid_canvas`
 * (M11c, spec docs/specs/M11c-grid-component-spec.md sections 2-4;
 * DECISIONS #190, #194, #195, #196). Sub-prompt 1.1 builds VIEW mode only:
 * the Run lab's run-area grid. Paint mode (the tools, the stroke overlay,
 * sending strokes back) is sub-prompt 1.3's.
 *
 * HOW A STREAMLIT CUSTOM COMPONENT WORKS -- for a reader new to web front
 * ends. Streamlit loads this folder's index.html inside an <iframe>: a small
 * web page embedded in the app's page, with its own document and its own
 * JavaScript. The iframe and the app never share variables; they talk only
 * by `window.postMessage`, which hands a plain object from one window to the
 * other. Four message types make up the whole protocol:
 *
 *   page -> app  "streamlit:componentReady"   sent once, first, before
 *                                             anything else ("I am loaded");
 *   app -> page  "streamlit:render"           sent on every script pass that
 *                                             changes the arguments: `args`
 *                                             holds the keyword arguments of
 *                                             the Python call, `theme` the
 *                                             app's current colours and font;
 *   page -> app  "streamlit:setFrameHeight"   how tall the iframe should be
 *                                             (the page decides its height);
 *   page -> app  "streamlit:setComponentValue" a value for Python to read --
 *                                             a WIDGET CHANGE, so it reruns
 *                                             the whole script. View mode
 *                                             never sends one.
 *
 * Every page -> app message must carry `isStreamlitMessage: true`: the
 * installed Streamlit 1.58 frontend silently drops any message without that
 * key (ComponentRegistry.onMessageEvent; DECISIONS #196).
 *
 * Because the Python call passes a `key`, Streamlit keeps the SAME iframe
 * alive across script passes (keyed identity), so this page's variables --
 * the zoom, the pan, the last image -- survive every pass: a new pass only
 * posts a new render message, and the page redraws in place.
 *
 * WHAT THE PAGE DRAWS. `cells` holds one byte per site in row-major order
 * (0 = empty, i = the i-th registered strategy). The page paints them into
 * an OFF-SCREEN canvas at one pixel per site, then scales that image onto
 * the visible canvas with smoothing off, so every cell stays a crisp square
 * at any zoom. Grid lines appear only once a cell is at least
 * `border_min_px` screen pixels wide.
 */

// An "immediately invoked function expression": the whole file runs inside
// one function called right away, so none of its names leak into the
// page's global scope.
(function () {
  "use strict";

  // FIRST, before anything else: announce readiness. (`postToStreamlit` is a
  // function declaration further down; JavaScript "hoists" declarations, so
  // it is callable here. The app's reply -- the first render -- arrives as a
  // separate event after this whole script has run, by which time the
  // message listener below is registered.)
  postToStreamlit({ type: "streamlit:componentReady", apiVersion: 1 });

  var MAX_CELL_PX = 64; // the deepest zoom: 64 CSS pixels per cell
  var MAX_CANVAS_PX = 600; // the canvas is never taller than this at fit
  var ZOOM_STEP = 1.25; // one wheel notch or one "+"/"-" click
  var WHEEL_NOTCH_PX = 100; // a typical wheel notch, in pixel deltas
  var FALLBACK_RGB = [136, 136, 136];
  var DEFAULT_THEME = {
    backgroundColor: "#ffffff",
    secondaryBackgroundColor: "#f0f2f6",
    textColor: "#31333f",
    font: "sans-serif",
  };

  var els = {
    root: document.getElementById("root"),
    stage: document.getElementById("stage"),
    canvas: document.getElementById("grid"),
    zoomIn: document.getElementById("zoom-in"),
    zoomOut: document.getElementById("zoom-out"),
    zoomFit: document.getElementById("zoom-fit"),
    error: document.getElementById("error"),
    hover: document.getElementById("hover"),
    key: document.getElementById("key"),
    debug: document.getElementById("debug"),
  };
  var ctx = els.canvas.getContext("2d");

  var state = {
    // What the last render delivered.
    cells: null, // Uint8Array, rows * cols bytes
    rows: 0,
    cols: 0,
    version: null,
    palette: [],
    names: [],
    borderMinPx: 6,
    debug: false,
    error: null,
    // Colours: the theme's, and one [r, g, b] per palette index.
    theme: DEFAULT_THEME,
    rgb: [],
    paletteKey: "",
    themeKey: "",
    keySignature: "",
    // The off-screen image: one pixel per site.
    image: document.createElement("canvas"),
    imageData: null,
    // Layout, in CSS pixels.
    width: 0,
    height: 0,
    fitScale: 1,
    // The view: CSS pixels per cell, and where the grid's top-left corner
    // sits on the canvas. Kept across renders (keyed identity).
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    atFit: true,
    haveView: false,
    // Pointer state.
    drag: null, // {id, x, y} while a drag pans the view
    pointer: null, // the last hover position, {x, y}, or null
    lastFrameHeight: -1,
  };

  // -------------------------------------------------------------------
  // The protocol.
  // -------------------------------------------------------------------

  /** Post one message to the app, with the key the app requires. */
  function postToStreamlit(message) {
    message.isStreamlitMessage = true;
    window.parent.postMessage(message, "*");
  }

  /**
   * Send a value to Python. RESERVED for paint mode (sub-prompt 1.3): a sent
   * value is a widget change and reruns the whole script, so VIEW MODE NEVER
   * CALLS THIS.
   */
  function sendValue(value) {
    postToStreamlit({ type: "streamlit:setComponentValue", value: value, dataType: "json" });
  }

  /** Size the iframe to the page -- only when the height changed. */
  function syncFrameHeight() {
    if (els.root.clientWidth === 0) {
      return; // a hidden Streamlit tab: never size from a zero width
    }
    var height = Math.ceil(els.root.getBoundingClientRect().height);
    if (height !== state.lastFrameHeight) {
      state.lastFrameHeight = height;
      postToStreamlit({ type: "streamlit:setFrameHeight", height: height });
    }
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) {
      return;
    }
    var data = event.data;
    if (!data || data.type !== "streamlit:render") {
      return;
    }
    onRender(data.args || {}, data.theme || null);
  });

  // -------------------------------------------------------------------
  // Decoding what arrives.
  // -------------------------------------------------------------------

  /**
   * The cells as a Uint8Array. Streamlit 1.58 delivers a Python `bytes`
   * argument as a Uint8Array (DECISIONS #196); a string is base64 text.
   */
  function decodeCells(value) {
    if (value instanceof Uint8Array) {
      return value;
    }
    if (value instanceof ArrayBuffer) {
      return new Uint8Array(value);
    }
    if (ArrayBuffer.isView(value)) {
      return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    }
    if (typeof value === "string") {
      var binary = window.atob(value);
      var out = new Uint8Array(binary.length);
      for (var i = 0; i < binary.length; i++) {
        out[i] = binary.charCodeAt(i);
      }
      return out;
    }
    return null;
  }

  var colourProbe = document.createElement("canvas");
  colourProbe.width = 1;
  colourProbe.height = 1;
  var colourProbeCtx = colourProbe.getContext("2d");
  var colourCache = {};

  /** Any CSS colour string -> [r, g, b] (via a 1 x 1 canvas; cached). */
  function parseColour(css) {
    if (typeof css !== "string" || css === "") {
      return FALLBACK_RGB;
    }
    if (Object.prototype.hasOwnProperty.call(colourCache, css)) {
      return colourCache[css];
    }
    var rgb;
    var hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(css);
    if (hex) {
      rgb = [parseInt(hex[1], 16), parseInt(hex[2], 16), parseInt(hex[3], 16)];
    } else {
      colourProbeCtx.clearRect(0, 0, 1, 1);
      colourProbeCtx.fillStyle = "#000000";
      colourProbeCtx.fillStyle = css;
      colourProbeCtx.fillRect(0, 0, 1, 1);
      var d = colourProbeCtx.getImageData(0, 0, 1, 1).data;
      rgb = [d[0], d[1], d[2]];
    }
    colourCache[css] = rgb;
    return rgb;
  }

  function rgba(rgb, alpha) {
    return "rgba(" + rgb[0] + ", " + rgb[1] + ", " + rgb[2] + ", " + alpha + ")";
  }

  // -------------------------------------------------------------------
  // A render arrives.
  // -------------------------------------------------------------------

  function onRender(args, theme) {
    var start = performance.now();

    if (args.mode === "paint") {
      // PAINT MODE -- sub-prompt 1.3 (spec sections 3-4: the Draw,
      // Rectangle, Lasso and Pan tools, the unacknowledged-stroke overlay,
      // strokes returned on release through sendValue). Not built yet:
      // until then a paint-mode render is drawn exactly like view mode.
    }

    var t = theme || {};
    var nextTheme = {
      backgroundColor: t.backgroundColor || DEFAULT_THEME.backgroundColor,
      secondaryBackgroundColor: t.secondaryBackgroundColor || DEFAULT_THEME.secondaryBackgroundColor,
      textColor: t.textColor || DEFAULT_THEME.textColor,
      font: t.font || DEFAULT_THEME.font,
    };
    var themeKey = [
      nextTheme.backgroundColor,
      nextTheme.secondaryBackgroundColor,
      nextTheme.textColor,
      nextTheme.font,
    ].join("|");

    var rows = Math.floor(Number(args.rows)) || 0;
    var cols = Math.floor(Number(args.cols)) || 0;
    var cells = decodeCells(args.cells);
    var palette = Array.isArray(args.palette) ? args.palette : [];
    var paletteKey = JSON.stringify(palette);
    var version = String(args.version);

    state.names = Array.isArray(args.names) ? args.names : [];
    state.borderMinPx = Number(args.border_min_px) || 6;
    state.debug = args.debug === true;
    els.debug.hidden = !state.debug;
    applyTheme(nextTheme);

    if (rows < 1 || cols < 1 || !cells || cells.length !== rows * cols) {
      // A bug on the Python side, never user error: draw nothing.
      var got = cells ? cells.length : "no";
      showError(
        "Grid data error: expected " + rows + " \u00d7 " + cols + " = " + rows * cols +
          " cells, received " + got + "."
      );
      return;
    }
    var recovered = state.error !== null;
    clearError();

    var sizeChanged = rows !== state.rows || cols !== state.cols;
    var colourChanged = paletteKey !== state.paletteKey || themeKey !== state.themeKey;
    var rebuild = sizeChanged || colourChanged || version !== state.version || !state.cells;

    state.rows = rows;
    state.cols = cols;
    state.cells = cells;
    state.version = version;
    state.palette = palette;
    if (colourChanged) {
      state.paletteKey = paletteKey;
      state.themeKey = themeKey;
      state.rgb = palette.map(function (colour, index) {
        return index === 0 ? parseColour(nextTheme.secondaryBackgroundColor) : parseColour(colour);
      });
    }
    if (rebuild) {
      rebuildImage();
    }
    renderKey(Array.isArray(args.key_entries) ? args.key_entries : []);

    // Zoom and pan survive every render; they reset to Fit only on the
    // first render and when the grid's size changes.
    var viewReset = sizeChanged || !state.haveView;
    var laidOut = layout(viewReset);
    if (laidOut.changed || rebuild || recovered) {
      draw(start);
    } else {
      // Identical version, size and colours: no rebuild and no redraw.
      syncFrameHeight();
    }
  }

  function applyTheme(theme) {
    state.theme = theme;
    els.root.style.color = theme.textColor;
    els.root.style.fontFamily = theme.font;
    var text = parseColour(theme.textColor);
    var buttons = [els.zoomIn, els.zoomOut, els.zoomFit];
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].style.background = theme.backgroundColor;
      buttons[i].style.color = theme.textColor;
      buttons[i].style.borderColor = rgba(text, 0.35);
    }
  }

  function showError(message) {
    state.error = message;
    els.error.textContent = message;
    els.error.hidden = false;
    els.canvas.style.height = "0px";
    els.hover.textContent = "";
    syncFrameHeight();
  }

  function clearError() {
    if (state.error !== null) {
      state.error = null;
      els.error.hidden = true;
      els.error.textContent = "";
    }
  }

  // -------------------------------------------------------------------
  // The off-screen image: one pixel per site.
  // -------------------------------------------------------------------

  function rebuildImage() {
    var rows = state.rows;
    var cols = state.cols;
    var cells = state.cells;
    var table = state.rgb;
    if (state.image.width !== cols || state.image.height !== rows || !state.imageData) {
      state.image.width = cols;
      state.image.height = rows;
      state.imageData = state.image.getContext("2d").createImageData(cols, rows);
    }
    var pixels = state.imageData.data; // r, g, b, a for every site, row-major
    var count = rows * cols;
    for (var i = 0, j = 0; i < count; i++, j += 4) {
      var rgb = table[cells[i]] || FALLBACK_RGB;
      pixels[j] = rgb[0];
      pixels[j + 1] = rgb[1];
      pixels[j + 2] = rgb[2];
      pixels[j + 3] = 255;
    }
    state.image.getContext("2d").putImageData(state.imageData, 0, 0);
  }

  // -------------------------------------------------------------------
  // Layout and the view (zoom and pan).
  // -------------------------------------------------------------------

  /**
   * Measure the container and derive the fit scale and canvas height.
   * Returns {changed}. A zero width (a hidden Streamlit tab) skips sizing;
   * the ResizeObserver lays out again once the width comes back.
   */
  function layout(resetView) {
    var width = els.stage.clientWidth;
    if (width === 0 || state.rows === 0) {
      if (resetView) {
        state.haveView = false; // fit on the first visible layout
      }
      return { changed: false };
    }
    var fit = Math.min(MAX_CELL_PX, width / state.cols, MAX_CANVAS_PX / state.rows);
    var height = state.rows * fit;
    var changed = width !== state.width || height !== state.height || fit !== state.fitScale;
    state.width = width;
    state.height = height;
    state.fitScale = fit;
    if (resetView || !state.haveView) {
      fitView();
      changed = true;
    } else if (state.atFit) {
      if (changed) {
        fitView(); // a view at fit stays at fit
      }
    } else if (changed) {
      // A zoomed view keeps its scale (never below the new fit) and re-clamps.
      state.scale = Math.min(MAX_CELL_PX, Math.max(fit, state.scale));
      clampView();
    }
    state.haveView = true;
    return { changed: changed };
  }

  function fitView() {
    state.scale = state.fitScale;
    state.atFit = true;
    clampView();
  }

  /** Centre an axis the grid does not fill; otherwise keep the grid's edges in view. */
  function clampView() {
    var gridW = state.cols * state.scale;
    var gridH = state.rows * state.scale;
    if (gridW <= state.width) {
      state.offsetX = (state.width - gridW) / 2;
    } else {
      state.offsetX = Math.min(0, Math.max(state.width - gridW, state.offsetX));
    }
    if (gridH <= state.height) {
      state.offsetY = (state.height - gridH) / 2;
    } else {
      state.offsetY = Math.min(0, Math.max(state.height - gridH, state.offsetY));
    }
  }

  /** Zoom by `factor` about the canvas point (x, y): the grid point there stays there. */
  function zoomAbout(x, y, factor, start) {
    if (!state.haveView || state.error !== null) {
      return;
    }
    var target = Math.min(MAX_CELL_PX, Math.max(state.fitScale, state.scale * factor));
    if (target === state.scale) {
      return;
    }
    var gridX = (x - state.offsetX) / state.scale;
    var gridY = (y - state.offsetY) / state.scale;
    state.scale = target;
    state.offsetX = x - gridX * target;
    state.offsetY = y - gridY * target;
    state.atFit = target <= state.fitScale * (1 + 1e-9);
    if (state.atFit) {
      state.scale = state.fitScale;
    }
    clampView();
    draw(start);
  }

  function panBy(dx, dy, start) {
    state.offsetX += dx;
    state.offsetY += dy;
    clampView();
    draw(start);
  }

  // -------------------------------------------------------------------
  // Drawing.
  // -------------------------------------------------------------------

  function draw(start) {
    if (!state.cells || state.error !== null || state.width === 0 || !state.haveView) {
      return;
    }
    var width = state.width;
    var height = state.height;
    var ratio = window.devicePixelRatio || 1;
    var backingW = Math.max(1, Math.round(width * ratio));
    var backingH = Math.max(1, Math.round(height * ratio));
    if (els.canvas.width !== backingW) {
      els.canvas.width = backingW;
    }
    if (els.canvas.height !== backingH) {
      els.canvas.height = backingH;
    }
    els.canvas.style.height = height + "px";

    // Draw in CSS pixels; the transform maps them onto device pixels.
    // (Resizing a canvas resets its context, so these are set every frame.)
    ctx.setTransform(backingW / width, 0, 0, backingH / height, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = state.theme.backgroundColor;
    ctx.fillRect(0, 0, width, height);
    var gridW = state.cols * state.scale;
    var gridH = state.rows * state.scale;
    ctx.drawImage(state.image, 0, 0, state.cols, state.rows, state.offsetX, state.offsetY, gridW, gridH);
    if (state.scale >= state.borderMinPx) {
      drawGridLines(gridW, gridH);
    }

    updateHover();
    if (state.debug) {
      els.debug.textContent = "frame " + (performance.now() - start).toFixed(1) + " ms";
    }
    syncFrameHeight();
  }

  /** Lines between cells, in the theme's background colour, only within view. */
  function drawGridLines(gridW, gridH) {
    var s = state.scale;
    var left = Math.max(0, state.offsetX);
    var right = Math.min(state.width, state.offsetX + gridW);
    var top = Math.max(0, state.offsetY);
    var bottom = Math.min(state.height, state.offsetY + gridH);
    var firstCol = Math.max(1, Math.ceil(-state.offsetX / s));
    var lastCol = Math.min(state.cols - 1, Math.floor((state.width - state.offsetX) / s));
    var firstRow = Math.max(1, Math.ceil(-state.offsetY / s));
    var lastRow = Math.min(state.rows - 1, Math.floor((state.height - state.offsetY) / s));
    ctx.fillStyle = state.theme.backgroundColor;
    for (var c = firstCol; c <= lastCol; c++) {
      ctx.fillRect(state.offsetX + c * s - 0.5, top, 1, bottom - top);
    }
    for (var r = firstRow; r <= lastRow; r++) {
      ctx.fillRect(left, state.offsetY + r * s - 0.5, right - left, 1);
    }
  }

  // -------------------------------------------------------------------
  // Hover text and the colour key.
  // -------------------------------------------------------------------

  /** "row r, col c -- <name>" (counted from 1), or blank off the grid. */
  function updateHover() {
    var text = "";
    var p = state.pointer;
    if (p && state.cells && state.error === null && state.haveView) {
      var col = Math.floor((p.x - state.offsetX) / state.scale);
      var row = Math.floor((p.y - state.offsetY) / state.scale);
      if (row >= 0 && row < state.rows && col >= 0 && col < state.cols) {
        var index = state.cells[row * state.cols + col];
        var name = index === 0 ? "empty" : state.names[index] || "unknown";
        text = "row " + (row + 1) + ", col " + (col + 1) + " \u2014 " + name;
      }
    }
    if (els.hover.textContent !== text) {
      els.hover.textContent = text;
    }
  }

  /** The key: a swatch and a name per entry, Empty last, in the theme's colours. */
  function renderKey(entries) {
    var theme = state.theme;
    var signature = JSON.stringify([entries, state.palette, state.names, state.themeKey]);
    if (signature === state.keySignature) {
      return;
    }
    state.keySignature = signature;
    var outline = rgba(parseColour(theme.textColor), 0.45);
    els.key.textContent = "";
    for (var i = 0; i < entries.length; i++) {
      var index = entries[i];
      var entry = document.createElement("span");
      entry.className = "key-entry";
      var swatch = document.createElement("span");
      swatch.className = "swatch";
      if (index === 0) {
        swatch.style.background = theme.secondaryBackgroundColor;
        swatch.style.border = "1px solid " + outline;
      } else {
        swatch.style.background = state.palette[index] || rgba(FALLBACK_RGB, 1);
      }
      var label = document.createElement("span");
      label.textContent = state.names[index] || "unknown";
      entry.appendChild(swatch);
      entry.appendChild(label);
      els.key.appendChild(entry);
    }
  }

  // -------------------------------------------------------------------
  // Gestures: wheel zoom about the pointer, drag to pan, the three buttons.
  // -------------------------------------------------------------------

  function canvasPoint(event) {
    var rect = els.canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  // `passive: false` is what allows preventDefault, so the wheel zooms the
  // grid instead of scrolling the app's page.
  els.canvas.addEventListener(
    "wheel",
    function (event) {
      event.preventDefault();
      var start = performance.now();
      var delta = event.deltaY;
      if (event.deltaMode === 1) {
        delta *= 33; // lines -> pixels
      } else if (event.deltaMode === 2) {
        delta *= state.height || MAX_CANVAS_PX; // pages -> pixels
      }
      var notches = Math.max(-5, Math.min(5, delta / WHEEL_NOTCH_PX));
      if (notches === 0) {
        return;
      }
      var p = canvasPoint(event);
      zoomAbout(p.x, p.y, Math.pow(ZOOM_STEP, -notches), start);
    },
    { passive: false }
  );

  // Pointer events cover mouse, pen and touch alike; "pointer capture"
  // keeps delivering the drag's moves to the canvas even when the pointer
  // leaves it.
  els.canvas.addEventListener("pointerdown", function (event) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    els.canvas.setPointerCapture(event.pointerId);
    var p = canvasPoint(event);
    state.drag = { id: event.pointerId, x: p.x, y: p.y };
    els.canvas.style.cursor = "grabbing";
  });

  els.canvas.addEventListener("pointermove", function (event) {
    var p = canvasPoint(event);
    if (state.drag && event.pointerId === state.drag.id) {
      var start = performance.now();
      var dx = p.x - state.drag.x;
      var dy = p.y - state.drag.y;
      state.drag.x = p.x;
      state.drag.y = p.y;
      if (dx !== 0 || dy !== 0) {
        panBy(dx, dy, start);
      }
      return;
    }
    if (event.buttons === 0) {
      state.pointer = p;
      updateHover();
    }
  });

  function endDrag(event) {
    if (state.drag && event.pointerId === state.drag.id) {
      state.drag = null;
      els.canvas.style.cursor = "grab";
      if (els.canvas.hasPointerCapture(event.pointerId)) {
        els.canvas.releasePointerCapture(event.pointerId);
      }
    }
  }
  els.canvas.addEventListener("pointerup", endDrag);
  els.canvas.addEventListener("pointercancel", endDrag);
  els.canvas.addEventListener("lostpointercapture", endDrag);
  els.canvas.addEventListener("pointerleave", function () {
    if (!state.drag) {
      state.pointer = null;
      updateHover();
    }
  });

  els.zoomIn.addEventListener("click", function () {
    zoomAbout(state.width / 2, state.height / 2, ZOOM_STEP, performance.now());
  });
  els.zoomOut.addEventListener("click", function () {
    zoomAbout(state.width / 2, state.height / 2, 1 / ZOOM_STEP, performance.now());
  });
  els.zoomFit.addEventListener("click", function () {
    var start = performance.now();
    if (!state.haveView) {
      return;
    }
    fitView();
    draw(start);
  });

  // -------------------------------------------------------------------
  // Resizing: the container's width decides the fit.
  // -------------------------------------------------------------------

  // A ResizeObserver calls back whenever the observed element changes
  // size. A component on a hidden Streamlit tab has zero width: skip it,
  // and lay out again when the width comes back. A view at fit stays at
  // fit; a zoomed view keeps its scale and is re-clamped.
  new ResizeObserver(function () {
    var width = els.stage.clientWidth;
    if (width === 0 || width === state.width || !state.cells || state.error !== null) {
      return;
    }
    var start = performance.now();
    if (layout(!state.haveView).changed) {
      draw(start);
    }
  }).observe(els.root);

  // sendValue is paint mode's (1.3); referenced here so linters see it used.
  void sendValue;
})();
