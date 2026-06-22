(function () {
  const btnCapture = document.getElementById("btn-capture");
  const btnStitch = document.getElementById("btn-stitch");
  const btnStopStitch = document.getElementById("btn-stop-stitch");
  const dotCapture = document.getElementById("dot-capture");
  const dotStitch = document.getElementById("dot-stitch");
  const captureText = document.getElementById("capture-text");
  const stitchText = document.getElementById("stitch-text");
  const metaText = document.getElementById("meta-text");

  const statusCapture = document.getElementById("status-capture");
  const statusFrames = document.getElementById("status-frames");
  const statusFps = document.getElementById("status-fps");
  const statusLast = document.getElementById("status-last");
  const statusStitcher = document.getElementById("status-stitcher");
  const statusBuffer = document.getElementById("status-buffer");
  const statusStitchMs = document.getElementById("status-stitch-ms");

  const mapImg = document.getElementById("map-img");
  const mapEmpty = document.getElementById("map-empty");
  const frameImg = document.getElementById("frame-img");
  const frameEmpty = document.getElementById("frame-empty");
  const errorBox = document.getElementById("error-box");

  function showError(message) {
    if (!message) {
      errorBox.classList.add("hidden");
      errorBox.textContent = "";
      return;
    }
    errorBox.classList.remove("hidden");
    errorBox.textContent = message;
  }

  async function postJson(url) {
    const response = await fetch(url, { method: "POST" });
    let payload = null;
    try { payload = await response.json(); } catch (e) { /* ignore */ }
    if (!response.ok) {
      const message = (payload && payload.error) || `HTTP ${response.status}`;
      showError(message);
      return null;
    }
    showError(null);
    return payload;
  }

  async function refreshStatus() {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      updateUi(data);
    } catch (err) {
      // Network blips are normal during restart, swallow them.
    }
  }

  function updateUi(data) {
    const capture = data.capture || {};
    const stitch = data.stitch || {};

    const captureRunning = !!capture.running;
    const stitching = !!stitch.stitching;

    dotCapture.classList.toggle("on", captureRunning);
    captureText.textContent = captureRunning ? "Capture: running" : "Capture: idle";
    btnCapture.textContent = captureRunning ? "Stop Capture" : "Start Capture";

    dotStitch.classList.toggle("on", stitching);
    stitchText.textContent = stitching
      ? "Stitch: live"
      : stitch.last_status === "starting"
        ? "Stitch: starting"
        : "Stitch: idle";
    btnStitch.disabled = false;

    metaText.textContent =
      `frames=${capture.frame_count || 0}` +
      ` buffer=${stitch.buffer_size || 0}` +
      ` last=${stitch.last_stitch_ms != null ? stitch.last_stitch_ms.toFixed(0) + "ms" : "n/a"}`;

    statusCapture.textContent = captureRunning ? "Yes" : "No";
    statusFrames.textContent = String(capture.frame_count || 0);
    statusFps.textContent = (capture.fps || 0).toFixed(2);
    statusLast.textContent = capture.last_image || "none";
    statusLast.title = capture.last_image || "";
    statusStitcher.textContent = stitch.last_status || (stitching ? "running" : "idle");
    statusBuffer.textContent = String(stitch.buffer_size || 0);
    statusStitchMs.textContent =
      stitch.last_stitch_ms != null ? `${stitch.last_stitch_ms.toFixed(0)} ms` : "—";

    if (capture.last_image) {
      frameImg.src = `/api/frame?path=${encodeURIComponent(capture.last_image)}&ts=${Date.now()}`;
      frameImg.classList.add("has-image");
      frameEmpty.parentElement.classList.add("has-image");
    }

    if (stitch.realtime_map_exists) {
      mapImg.src = `/maps/realtime?ts=${Date.now()}`;
      mapEmpty.parentElement.classList.add("has-image");
    }
  }

  btnCapture.addEventListener("click", async () => {
    btnCapture.disabled = true;
    try {
      const running = statusCapture.textContent === "Yes";
      const url = running ? "/api/capture/stop" : "/api/capture/start";
      await postJson(url);
      await refreshStatus();
    } finally {
      btnCapture.disabled = false;
    }
  });

  btnStitch.addEventListener("click", async () => {
    btnStitch.disabled = true;
    try {
      await postJson("/api/stitch/start");
      await refreshStatus();
    } finally {
      btnStitch.disabled = false;
    }
  });

  btnStopStitch.addEventListener("click", async () => {
    btnStopStitch.disabled = true;
    try {
      await postJson("/api/stitch/stop");
      await refreshStatus();
    } finally {
      btnStopStitch.disabled = false;
    }
  });

  // Initial pull + recurring refresh.
  refreshStatus();
  setInterval(refreshStatus, 1000);

  // Bust image caches on a faster cadence so the live map visibly updates.
  setInterval(() => {
    if (mapImg.src && mapImg.parentElement.classList.contains("has-image")) {
      mapImg.src = `/maps/realtime?ts=${Date.now()}`;
    }
  }, 1500);
})();
