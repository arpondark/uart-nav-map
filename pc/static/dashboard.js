(function () {
  const dotCapture = document.getElementById("dot-capture");
  const dotRealtime = document.getElementById("dot-realtime");
  const dotHq = document.getElementById("dot-hq");
  const captureText = document.getElementById("capture-text");
  const realtimeText = document.getElementById("realtime-text");
  const hqText = document.getElementById("hq-text");
  const metaText = document.getElementById("meta-text");

  const btnCapture = document.getElementById("btn-capture");
  const btnCaptureStop = document.getElementById("btn-capture-stop");
  const btnStitchRealtime = document.getElementById("btn-stitch-realtime");
  const btnStitchHq = document.getElementById("btn-stitch-hq");
  const btnStitchAll = document.getElementById("btn-stitch-all");
  const btnStitchStop = document.getElementById("btn-stitch-stop");

  const statusCapture = document.getElementById("status-capture");
  const statusFrames = document.getElementById("status-frames");
  const statusFps = document.getElementById("status-fps");
  const statusLast = document.getElementById("status-last");
  const statusImageDir = document.getElementById("status-image-dir");
  const statusStitcher = document.getElementById("status-stitcher");
  const statusBuffer = document.getElementById("status-buffer");
  const statusStitchMs = document.getElementById("status-stitch-ms");
  const statusHqState = document.getElementById("status-hq-state");
  const statusHqBuffer = document.getElementById("status-hq-buffer");
  const statusHqMs = document.getElementById("status-hq-ms");
  const statusHqCuda = document.getElementById("status-hq-cuda");
  const statusHqBatch = document.getElementById("status-hq-batch");
  const statusHqPeriod = document.getElementById("status-hq-period");

  const mapImg = document.getElementById("map-img");
  const mapEmpty = document.getElementById("map-empty");
  const hqImg = document.getElementById("hq-img");
  const hqEmpty = document.getElementById("hq-empty");
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
      if (!response.ok) return;
      const data = await response.json();
      updateUi(data);
    } catch (err) {
      // Network blips are normal during restart, swallow them.
    }
  }

  function updateUi(data) {
    const capture = data.capture || {};
    const stitch = data.stitch || {};
    const hq = data.hq || {};

    const captureRunning = !!capture.running;
    const rtRunning = !!stitch.stitching;
    const hqRunning = !!hq.enabled;

    dotCapture.classList.toggle("on", captureRunning);
    captureText.textContent = captureRunning ? "Capture: running" : "Capture: idle";
    btnCapture.textContent = captureRunning ? "Capture on" : "Start Capture";

    dotRealtime.classList.toggle("on", rtRunning);
    realtimeText.textContent = rtRunning ? "Realtime: live" : "Realtime: idle";
    btnStitchRealtime.textContent = rtRunning ? "Realtime on" : "Stitch Realtime";

    dotHq.classList.toggle("on", hqRunning);
    hqText.textContent = hqRunning ? "HQ: running" : "HQ: idle";
    btnStitchHq.textContent = hqRunning ? "HQ on" : "Stitch HQ";

    metaText.textContent =
      `frames=${capture.frame_count || 0}` +
      ` rt=${stitch.last_stitch_ms != null ? stitch.last_stitch_ms.toFixed(0) + "ms" : "n/a"}` +
      ` hq=${hq.last_stitch_ms != null ? hq.last_stitch_ms.toFixed(0) + "ms" : "n/a"}`;

    statusCapture.textContent = captureRunning ? "Yes" : "No";
    statusFrames.textContent = String(capture.frame_count || 0);
    statusFps.textContent = (capture.fps || 0).toFixed(2);
    statusLast.textContent = capture.last_image || "none";
    statusLast.title = capture.last_image || "";
    statusImageDir.textContent = data.image_dir || "—";

    statusStitcher.textContent = stitch.last_status || (rtRunning ? "running" : "idle");
    statusBuffer.textContent = String(stitch.buffer_size || 0);
    statusStitchMs.textContent =
      stitch.last_stitch_ms != null ? `${stitch.last_stitch_ms.toFixed(0)} ms` : "—";

    statusHqState.textContent = hq.last_status || (hqRunning ? "running" : "idle");
    statusHqBuffer.textContent = String(hq.buffer_size || 0);
    statusHqMs.textContent =
      hq.last_stitch_ms != null ? `${hq.last_stitch_ms.toFixed(0)} ms` : "—";
    statusHqCuda.textContent = hq.cuda_available ? "available" : "no";
    if (statusHqBatch) statusHqBatch.textContent = String(hq.batch_size || "—");
    if (statusHqPeriod) statusHqPeriod.textContent = String(hq.trigger_seconds || "—");

    if (capture.last_image) {
      frameImg.src = `/api/frame?path=${encodeURIComponent(capture.last_image)}&ts=${Date.now()}`;
      frameImg.parentElement.classList.add("has-image");
    }

    if (stitch.realtime_map_exists) {
      mapImg.src = `/maps/realtime?ts=${Date.now()}`;
      mapImg.parentElement.classList.add("has-image");
    }

    if (hq.hq_map_exists) {
      hqImg.src = `/maps/hq?ts=${Date.now()}`;
      hqImg.parentElement.classList.add("has-image");
    }
  }

  btnCapture.addEventListener("click", async () => {
    btnCapture.disabled = true;
    try {
      const running = statusCapture.textContent === "Yes";
      await postJson(running ? "/api/capture/stop" : "/api/capture/start");
      await refreshStatus();
    } finally { btnCapture.disabled = false; }
  });

  btnCaptureStop.addEventListener("click", async () => {
    btnCaptureStop.disabled = true;
    try {
      await postJson("/api/capture/stop");
      await refreshStatus();
    } finally { btnCaptureStop.disabled = false; }
  });

  btnStitchRealtime.addEventListener("click", async () => {
    btnStitchRealtime.disabled = true;
    try {
      await postJson("/api/stitch/start");
      await refreshStatus();
    } finally { btnStitchRealtime.disabled = false; }
  });

  btnStitchHq.addEventListener("click", async () => {
    btnStitchHq.disabled = true;
    try {
      await postJson("/api/hq/start");
      await refreshStatus();
    } finally { btnStitchHq.disabled = false; }
  });

  btnStitchAll.addEventListener("click", async () => {
    btnStitchAll.disabled = true;
    try {
      await postJson("/api/all/start");
      await refreshStatus();
    } finally { btnStitchAll.disabled = false; }
  });

  btnStitchStop.addEventListener("click", async () => {
    btnStitchStop.disabled = true;
    try {
      await postJson("/api/all/stop");
      await refreshStatus();
    } finally { btnStitchStop.disabled = false; }
  });

  refreshStatus();
  setInterval(refreshStatus, 1000);

  setInterval(() => {
    if (mapImg.src && mapImg.parentElement.classList.contains("has-image")) {
      mapImg.src = `/maps/realtime?ts=${Date.now()}`;
    }
    if (hqImg.src && hqImg.parentElement.classList.contains("has-image")) {
      hqImg.src = `/maps/hq?ts=${Date.now()}`;
    }
  }, 2000);
})();
