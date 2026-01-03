const socket = io();

// -------------------------
// Formatting helpers
// -------------------------
function formatOutputWithCommas(outputElement) {
    const value = parseFloat(outputElement.textContent);
    if (!isNaN(value)) {
        outputElement.textContent = value.toLocaleString();

        const relatedInputId = outputElement.id.replace('_out', '');
        const relatedInput = document.getElementById(relatedInputId);
        if (relatedInput) {
            const min = parseFloat(relatedInput.min);
            const max = parseFloat(relatedInput.max);
            if (!isNaN(min) && !isNaN(max) && (value < min || value > max)) {
                outputElement.style.color = 'red';
            } else {
                outputElement.style.color = '';
            }
        }
    }
}

// -------------------------
// LUT preview (shape-preserving cubic Hermite, same as osc_modes.LUT)
// -------------------------
const LUT_X_JS = Array.from({ length: 7 }, (_, i) => -1.0 + (2.0 * i) / 6.0);
const LUT_U_MIN = -1.0, LUT_U_MAX = 1.0;
let LUT_Y_MIN = -2.0, LUT_Y_MAX = 2.0; // default, overridden from HTML range
const LUT_MARGIN = 10;
const LUT_STEP = 0.01; // editing granularity for LUT_Y values

let lutDragIndex = null;
let lutSelectedIndex = null; // last clicked/dragged control point

function getCurrentLutY() {
    const n = LUT_X_JS.length;
    const ys = [];
    for (let i = 0; i < n; i++) {
        const el = document.getElementById(`LUT_Y${i}`);
        if (el && el.value !== '') {
            const v = parseFloat(el.value);
            ys.push(isNaN(v) ? LUT_X_JS[i] : v);
        } else {
            ys.push(LUT_X_JS[i]);
        }
    }
    return ys;
}

// Initialize LUT Y range from HTML slider attributes so the range can be
// changed in index.html without touching this JS.
function initLutRangeFromDom() {
    const el = document.getElementById('LUT_Y3') || document.getElementById('LUT_Y0');
    if (!el) return;
    const minAttr = parseFloat(el.min);
    const maxAttr = parseFloat(el.max);
    if (!isNaN(minAttr) && !isNaN(maxAttr) && minAttr < maxAttr) {
        LUT_Y_MIN = minAttr;
        LUT_Y_MAX = maxAttr;
    }
}

function evalLUT(u, lutY) {
    // Shape-preserving cubic Hermite spline (same as backend LUT)
    const n = LUT_X_JS.length;
    if (n < 2) return u;

    // Pre-compute segment widths and secant slopes
    const h = new Array(n - 1);
    const delta = new Array(n - 1);
    for (let i = 0; i < n - 1; i++) {
        const dx = LUT_X_JS[i + 1] - LUT_X_JS[i];
        h[i] = dx;
        if (dx === 0) {
            delta[i] = 0;
        } else {
            delta[i] = (lutY[i + 1] - lutY[i]) / dx;
        }
    }

    // Shape-preserving slope estimates
    const m = new Array(n);
    m[0] = delta[0];
    m[n - 1] = delta[n - 2];
    for (let k = 1; k < n - 1; k++) {
        if (delta[k - 1] * delta[k] <= 0) {
            m[k] = 0.0;
        } else {
            m[k] = 0.5 * (delta[k - 1] + delta[k]);
        }
    }

    const xMin = LUT_X_JS[0];
    const xMax = LUT_X_JS[n - 1];

    let k;
    if (u <= xMin) {
        k = 0;
    } else if (u >= xMax) {
        k = n - 2;
    } else {
        const step = (xMax - xMin) / (n - 1);
        const s = (u - xMin) / step;
        k = Math.floor(s);
        if (k < 0) k = 0;
        if (k > n - 2) k = n - 2;
    }

    const xk = LUT_X_JS[k];
    const hk = h[k];
    if (hk === 0) return lutY[k];
    const t = (u - xk) / hk;

    const t2 = t * t;
    const t3 = t2 * t;

    const h00 = 2 * t3 - 3 * t2 + 1;
    const h10 = t3 - 2 * t2 + t;
    const h01 = -2 * t3 + 3 * t2;
    const h11 = t3 - t2;

    const yk = lutY[k];
    const yk1 = lutY[k + 1];
    const mk = m[k];
    const mk1 = m[k + 1];

    return (
        h00 * yk +
        h10 * hk * mk +
        h01 * yk1 +
        h11 * hk * mk1
    );
}

function drawLUTCurve() {
    const canvas = document.getElementById('lut-curve-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const margin = LUT_MARGIN;

    // Clear background
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#f5f5f7';
    ctx.fillRect(0, 0, w, h);

    // Axes (u=0 vertical, y=0 horizontal)
    const uMin = LUT_U_MIN, uMax = LUT_U_MAX;
    const yMin = LUT_Y_MIN, yMax = LUT_Y_MAX;

    const xZero = margin + (0 - uMin) / (uMax - uMin) * (w - 2 * margin);
    const yZero = h - (margin + (0 - yMin) / (yMax - yMin) * (h - 2 * margin));

    ctx.strokeStyle = '#bbbbc5';
    ctx.lineWidth = 1;
    // vertical u=0
    ctx.beginPath();
    ctx.moveTo(xZero, margin);
    ctx.lineTo(xZero, h - margin);
    ctx.stroke();
    // horizontal y=0
    ctx.beginPath();
    ctx.moveTo(margin, yZero);
    ctx.lineTo(w - margin, yZero);
    ctx.stroke();

    // Axis labels (x: input at right end, y: output at top end)
    ctx.save();
    ctx.fillStyle = '#bbbbc5';
    ctx.font = '10px "Segoe UI", "Meiryo", sans-serif';

    // x-axis label near right end of horizontal axis (y = 0)
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.fillText('input', w - margin - 2, yZero + 4);

    // y-axis label near top end of vertical axis (x = 0)
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.fillText('output', xZero - 4, margin + 2);

    ctx.restore();

    // Diagonal x = y line (from u=-1,y=-1 to u=1,y=1)
    ctx.save();
    ctx.strokeStyle = '#d4d4e0';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    const uDiagMin = uMin;
    const uDiagMax = uMax;
    const yDiagMin = Math.max(yMin, uDiagMin);
    const yDiagMax = Math.min(yMax, uDiagMax);
    const xDiagMin = margin + (uDiagMin - uMin) / (uMax - uMin) * (w - 2 * margin);
    const yDiagMinPx = h - (margin + (yDiagMin - yMin) / (yMax - yMin) * (h - 2 * margin));
    const xDiagMax = margin + (uDiagMax - uMin) / (uMax - uMin) * (w - 2 * margin);
    const yDiagMaxPx = h - (margin + (yDiagMax - yMin) / (yMax - yMin) * (h - 2 * margin));
    ctx.beginPath();
    ctx.moveTo(xDiagMin, yDiagMinPx);
    ctx.lineTo(xDiagMax, yDiagMaxPx);
    ctx.stroke();
    ctx.restore();

    // Region hints near dashed line: above = more stretch, below = more shrink
    ctx.save();
    ctx.fillStyle = '#b5b5c8';
    ctx.font = '10px "Segoe UI", "Meiryo", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const dxDiag = xDiagMax - xDiagMin;
    const dyDiag = yDiagMaxPx - yDiagMinPx;
    const angleDiag = Math.atan2(dyDiag, dxDiag);

    function drawRegionHint(t, offsetSign, text) {
        const xLine = xDiagMin + dxDiag * t;
        const yLine = yDiagMinPx + dyDiag * t;
        const nx = -dyDiag;
        const ny = dxDiag;
        const nLen = Math.hypot(nx, ny) || 1;
        // Larger offset so text clearly separates from the dashed line
        const normalOffset = 22 * offsetSign;
        // Small tangential offset to spread labels left/right along the line
        const tangentialOffset = (offsetSign > 0 ? -10 : 10);
        const tx = dxDiag;
        const ty = dyDiag;
        const tLen = Math.hypot(tx, ty) || 1;

        const x = xLine + (nx / nLen) * normalOffset + (tx / tLen) * tangentialOffset;
        const y = yLine + (ny / nLen) * normalOffset + (ty / tLen) * tangentialOffset;

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angleDiag);
        ctx.fillText(text, 0, 0);
        ctx.restore();
    }

    // t values: choose two distinct positions along the diagonal (spread more to left/right)
    drawRegionHint(0.8, -1, '↑ more stretch');
    drawRegionHint(0.2, +1, '↓ more shrink');

    ctx.restore();

    const lutY = getCurrentLutY();

    // Draw curve
    ctx.strokeStyle = '#2a4d7a';
    ctx.lineWidth = 2;
    ctx.beginPath();
    const steps = 200;
    for (let i = 0; i <= steps; i++) {
        const u = uMin + (uMax - uMin) * (i / steps);
        const y = evalLUT(u, lutY);

        const xPx = margin + (u - uMin) / (uMax - uMin) * (w - 2 * margin);
        const yNorm = (y - yMin) / (yMax - yMin);
        const yPx = h - (margin + yNorm * (h - 2 * margin));

        if (i === 0) {
            ctx.moveTo(xPx, yPx);
        } else {
            ctx.lineTo(xPx, yPx);
        }
    }
    ctx.stroke();

    // Draw control points
    ctx.fillStyle = '#1a7a2a';
    const labelColor = '#3f7a3f';
    ctx.font = '11px "Segoe UI", "Meiryo", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (let i = 0; i < LUT_X_JS.length; i++) {
        const u = LUT_X_JS[i];
        const y = lutY[i];
        const xPx = margin + (u - uMin) / (uMax - uMin) * (w - 2 * margin);
        const yNorm = (y - yMin) / (yMax - yMin);
        const yPx = h - (margin + yNorm * (h - 2 * margin));

        // point
        ctx.beginPath();
        ctx.arc(xPx, yPx, 3, 0, Math.PI * 2);
        ctx.fill();

        // numeric label directly above the point (always 2 decimal places)
        const label = y.toFixed(2);
        let lx = xPx;
        let ly = yPx - 10; // a bit above the point

        // Clamp label position to stay inside plot margins
        lx = Math.min(w - margin - 4, Math.max(margin + 4, lx));
        ly = Math.min(h - margin - 10, Math.max(margin + 10, ly));

        // background for label to improve readability
        const metrics = ctx.measureText(label);
        const textW = metrics.width;
        const textH = 14; // approx line height for slightly larger font
        const padX = 3;
        const padY = 2;
        const bgX = lx - textW / 2 - padX;
        const bgY = ly - textH / 2 - padY + 1;
        ctx.fillStyle = 'rgba(245,245,247,0.9)';
        ctx.fillRect(bgX, bgY, textW + padX * 2, textH + padY * 2);

        ctx.fillStyle = labelColor;
        ctx.fillText(label, lx, ly);
        ctx.fillStyle = '#1a7a2a';
    }
}

function lutCanvasPosToValue(yPx, canvasHeight) {
    const margin = LUT_MARGIN;
    const yMin = LUT_Y_MIN, yMax = LUT_Y_MAX;
    const h = canvasHeight;
    const clampedYPx = Math.max(margin, Math.min(h - margin, yPx));
    const yNorm = (h - margin - clampedYPx) / (h - 2 * margin);
    let yVal = yMin + yNorm * (yMax - yMin);
    yVal = Math.max(yMin, Math.min(yMax, yVal));
    return yVal;
}

function quantizeLutYValue(yVal) {
    // Snap to LUT_STEP and clamp to allowed range
    if (!isFinite(yVal)) return 0;
    const step = LUT_STEP;
    let v = Math.round(yVal / step) * step;
    if (v < LUT_Y_MIN) v = LUT_Y_MIN;
    if (v > LUT_Y_MAX) v = LUT_Y_MAX;
    return v;
}

function getLutPointScreenPositions(canvas, lutY) {
    const w = canvas.width;
    const h = canvas.height;
    const margin = LUT_MARGIN;
    const uMin = LUT_U_MIN, uMax = LUT_U_MAX;
    const yMin = LUT_Y_MIN, yMax = LUT_Y_MAX;
    const pts = [];
    for (let i = 0; i < LUT_X_JS.length; i++) {
        const u = LUT_X_JS[i];
        const y = lutY[i];
        const xPx = margin + (u - uMin) / (uMax - uMin) * (w - 2 * margin);
        const yNorm = (y - yMin) / (yMax - yMin);
        const yPx = h - (margin + yNorm * (h - 2 * margin));
        pts.push({ x: xPx, y: yPx });
    }
    return pts;
}

function setLutValueFromCanvasY(index, yPx, syncServer) {
    const canvas = document.getElementById('lut-curve-canvas');
    if (!canvas) return;
    let yVal = lutCanvasPosToValue(yPx, canvas.height);
    yVal = quantizeLutYValue(yVal);
    const input = document.getElementById(`LUT_Y${index}`);
    if (input) {
        input.value = yVal.toFixed(2);
        if (syncServer) {
            updateParam(input);
        }
    }
    drawLUTCurve();
}

function handleLutPointerDown(clientX, clientY) {
    const canvas = document.getElementById('lut-curve-canvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const lutY = getCurrentLutY();
    const pts = getLutPointScreenPositions(canvas, lutY);

    let closest = -1;
    let minDist = Infinity;
    const hitRadius = 10;

    for (let i = 0; i < pts.length; i++) {
        const dx = x - pts[i].x;
        const dy = y - pts[i].y;
        const d = Math.hypot(dx, dy);
        if (d < minDist && d <= hitRadius) {
            minDist = d;
            closest = i;
        }
    }

    if (closest !== -1) {
        lutDragIndex = closest;
        lutSelectedIndex = closest;
        setLutValueFromCanvasY(closest, y, false);
    }
}

function handleLutPointerMove(clientX, clientY) {
    if (lutDragIndex === null) return;
    const canvas = document.getElementById('lut-curve-canvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const y = clientY - rect.top;
    setLutValueFromCanvasY(lutDragIndex, y, false);
}

function handleLutPointerUp(clientX, clientY) {
    if (lutDragIndex === null) return;
    const canvas = document.getElementById('lut-curve-canvas');
    if (!canvas) {
        lutDragIndex = null;
        return;
    }
    const rect = canvas.getBoundingClientRect();
    const y = clientY - rect.top;
    setLutValueFromCanvasY(lutDragIndex, y, true);
    lutSelectedIndex = lutDragIndex;
    lutDragIndex = null;
}

function updateParam(slider) {
    const param = slider.dataset.param;
    const outputId = slider.dataset.output;
    let value = slider.type === "checkbox" ? (slider.checked ? "true" : "false") : slider.value;
    if (outputId) {
        const outputElement = document.getElementById(outputId);
        if (outputElement) {
            outputElement.textContent = value;
            formatOutputWithCommas(outputElement); // Format the output with commas
        }
    }
    fetch("/set_param", {
        method: 'POST',
        body: new URLSearchParams({ [param]: value })
    });

    if (param && param.startsWith('LUT_Y')) {
        drawLUTCurve();
    }
}

function customSubmit() {
    const form = document.getElementById('mainForm');
    const formData = new FormData(form);
    fetch("/", {
        method: "POST",
        body: formData
    }).then(() => window.location.reload());
}

function setFormEnabled(enabled) {
    ["mainForm", "independentControllerForm"].forEach(formId => {
        const form = document.getElementById(formId);
        if (form) {
            Array.from(form.elements).forEach(el => {
                // Skip control buttons (Neutral, Home All, Init, Release)
                if (el.id === 'init-button' ||
                    el.onclick && (
                        el.onclick.toString().includes('sendSetNeutral') ||
                        el.onclick.toString().includes('sendHomeAll') ||
                        el.onclick.toString().includes('sendRelease')
                    )) {
                    return; // Skip these buttons, they are controlled by {% if running %}
                }

                if (el.dataset.param === "STROKE_OFFSET") {
                    el.disabled = true;
                } else {
                    el.disabled = !enabled;
                    if (el.type === "output") {
                        const relatedInputId = el.id.replace('_out', '');
                        const relatedInput = document.getElementById(relatedInputId);
                        if (relatedInput && (el.value == "" || isNaN(el.value))) relatedInput.disabled = true;
                    }
                }
            });
        }
    });
    const loader = document.getElementById('form-loading');
    if (loader) loader.style.display = enabled ? 'none' : 'inline-block';
}

function sendSetNeutral() {
    setFormEnabled(false);
    fetch("/setNeutral", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            setFormEnabled(true);
            if (data.result === "OK") {
                //alert("SetNeutral finished successfully");
                getTargetPosition();
            } else {
                alert("SetNeutral command failed: " + (data.error || ""));
            }
        });
}

function sendHomeAll() {
    setFormEnabled(false);
    fetch("/home_all", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            setFormEnabled(true);
            if (data.result === "OK") {
                alert("HomeAll finished successfully");
            } else {
                alert("HomeAll command failed: " + (data.error || ""));
            }
        });
}

function sendInit() {
    setFormEnabled(false);
    fetch("/init", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            setFormEnabled(true);
            if (data.result === "OK") {
                alert("Init finished successfully" + (data.info ? (" (" + data.info + ")") : ""));
                getTargetPosition();
            } else {
                alert("Init failed: " + (data.error || ""));
            }
        });
}

function sendRelease() {
    setFormEnabled(false);
    fetch("/release", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (data.result === "OK") {
                alert("Released successfully");
                document.getElementById('init-button').disabled = false;
            } else {
                alert("Release failed: " + (data.error || ""));
                setFormEnabled(true);
            }
        })
        .catch(() => {
            setFormEnabled(true);
            alert("Release communication error");
        });
}

let stepSign = 1;
function sendStep() {
    setFormEnabled(false);
    const amp = 10000 * stepSign;
    stepSign *= -1;
    fetch("/step", {
        method: "POST",
        body: new URLSearchParams({ amp: amp, ch: "all" })
    })
        .then(res => res.json())
        .then(data => {
            setFormEnabled(true);
            if (data.result !== "OK") {
                alert("Step command failed: " + (data.error || ""));
            }
        })
        .catch(() => {
            setFormEnabled(true);
            alert("Step communication error");
        });
}

function sendHoming() {
    const motorID = document.getElementById('motor-id-input').value;
    setFormEnabled(false);
    fetch(`/homing?motorID=${motorID}`, { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (data.result === "OK") {
                alert("Homing finished successfully");
                getTargetPosition();
                setFormEnabled(true);
            } else {
                alert("Homing command failed: " + (data.error || ""));
            }
        });
}

function getTargetPosition() {
    const boardsCheckbox = document.getElementById('chk_boards');
    if (boardsCheckbox && !boardsCheckbox.checked) return;

    const motorID = document.getElementById('motor-id-input').value;
    fetch(`/get_target_position?motorID=${motorID}`)
        .then(res => res.json())
        .then(data => {
            if (data.result === "OK") {
                document.getElementById('target-position-input').value = data.position;

            } else {
                alert("GetTargetPosition failed: " + (data.error || ""));
            }
        });
}

function sendResetPos() {
    const motorID = document.getElementById('motor-id-input').value;
    fetch("/reset_pos", {
        method: "POST",
        body: new URLSearchParams({ motorID: motorID })
    })
        .then(res => res.json())
        .then(data => {
            if (data.result === "OK") {
                document.getElementById('target-position-input').value = 0;
            } else {
                alert("ResetPos failed: " + (data.error || ""));
            }
        });
}

function sendSetTargetPosition() {
    const motorID = document.getElementById('motor-id-input').value;
    const position = document.getElementById('target-position-input').value;
    fetch("/set_target_position", {
        method: "POST",
        body: new URLSearchParams({ motorID: motorID, position: position })
    })
        .then(res => res.json())
        .then(data => {
            if (data.result !== "OK") {
                alert("SetTargetPosition failed: " + (data.error || ""));
            }
        });
}

function changeMode(select) {
    const mode = select.value;
    sessionStorage.setItem('modeChanged', '1');
    fetch("/set_mode", {
        method: "POST",
        body: new URLSearchParams({ MODE: mode })
    })
        .then(res => res.json())
        .then(data => {
            if (data.result === "OK") {
                window.location.reload();
            } else {
                alert("Mode change failed: " + (data.error || ""));
            }
        });
}

function sendHalt() {
    fetch("/halt", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            setFormEnabled(true);
            if (data.result === "OK") {
                alert(">>>Emergency Stop Activated<<<");
            } else {
                alert("Halt command failed: " + (data.error || ""));
            }
            setFormEnabled(false);
        });
}

function applyAdvancedVisibility(enabled) {
    document.querySelectorAll('.advanced-only').forEach(el => {
        el.style.display = enabled ? '' : 'none';
    });
}

function initServoVisualization(numServos) {
    const container = document.getElementById('servo-bars-container');
    if (!container) return;

    // Update the last label
    const lastLabel = document.getElementById('servo-last-label');
    if (lastLabel) {
        lastLabel.textContent = `#${numServos}`;
    }

    container.innerHTML = '';
    for (let i = 0; i < numServos; i++) {
        const barWrapper = document.createElement('div');
        barWrapper.className = 'servo-bar-wrapper';
        barWrapper.dataset.servoId = i + 1;

        const bar = document.createElement('div');
        bar.className = 'servo-bar';

        const tooltip = document.createElement('div');
        tooltip.className = 'servo-bar-tooltip';
        tooltip.textContent = `#${i + 1}: 0`;

        barWrapper.appendChild(bar);
        barWrapper.appendChild(tooltip);
        container.appendChild(barWrapper);
    }
}

function updateServoVisualization(positions, offset) {
    const container = document.getElementById('servo-bars-container');
    if (!container) return;

    const wrappers = container.querySelectorAll('.servo-bar-wrapper');
    if (wrappers.length === 0) return;

    // Fixed maximum value for scaling: ±40000
    const MAX_VALUE = 40000;

    positions.forEach((pos, index) => {
        if (index >= wrappers.length) return;

        const wrapper = wrappers[index];
        const bar = wrapper.querySelector('.servo-bar');
        const tooltip = wrapper.querySelector('.servo-bar-tooltip');

        // Calculate height as percentage (0-100% of half container, clamped to max)
        const heightPercent = Math.min((Math.abs(pos) / MAX_VALUE) * 100, 100);

        // Remove both classes first to reset state
        bar.classList.remove('positive', 'negative');

        // Apply height and direction based on sign
        bar.style.height = `${heightPercent}%`;

        if (pos >= 0) {
            // Positive: blue bar growing upward from center
            bar.classList.add('positive');
        } else {
            // Negative: red bar growing downward from center
            bar.classList.add('negative');
        }

        // Update tooltip
        if (tooltip) {
            tooltip.textContent = `#${index + 1}: ${pos.toLocaleString()}`;
        }
    });
}

socket.on('param_update', function (data) {
    const { key, value } = data;
    console.log(`Param updated: ${key} = ${value}`);

    const outputElement = document.querySelector(`[data-param="${key}"]`);
    const displayElement = document.getElementById(`${key}_out`);
    if (outputElement) {
        outputElement.value = value;
        outputElement.classList.add('updated');
        setTimeout(() => outputElement.classList.remove('updated'), 100);
    }
    if (displayElement) {
        displayElement.textContent = value;
        formatOutputWithCommas(displayElement);
        displayElement.classList.add('updated');
        setTimeout(() => displayElement.classList.remove('updated'), 100);
    }

    if (key && key.startsWith('LUT_Y')) {
        drawLUTCurve();
    }
});

socket.on('servo_positions', function (data) {
    updateServoVisualization(data.positions, data.offset);
});

// Handle server reconnection - reload page when server restarts
socket.on('connect', function () {
    console.log('Connected to server');

    // Check if this is a reconnection (not initial page load)
    const wasConnected = sessionStorage.getItem('wasConnected');
    if (wasConnected === 'true') {
        console.log('Server reconnected - reloading page');
        sessionStorage.removeItem('wasConnected');
        window.location.reload();
    } else {
        // Mark as connected for future reconnection detection
        sessionStorage.setItem('wasConnected', 'true');
    }
});

socket.on('disconnect', function () {
    console.log('Disconnected from server');
});

window.addEventListener('DOMContentLoaded', function () {

    window.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            sendHalt();
            return;
        }

        // Arrow key control for selected LUT point
        if ((event.key === 'ArrowUp' || event.key === 'ArrowDown') && lutSelectedIndex !== null) {
            event.preventDefault();

            const input = document.getElementById(`LUT_Y${lutSelectedIndex}`);
            if (!input) return;

            const current = parseFloat(input.value);
            const delta = (event.key === 'ArrowUp' ? LUT_STEP : -LUT_STEP);
            let nextVal = isNaN(current) ? 0 : current + delta;
            nextVal = quantizeLutYValue(nextVal);

            input.value = nextVal.toFixed(2);
            updateParam(input);
            drawLUTCurve();
        }
    });

    const motorIdInput = document.getElementById('motor-id-input');
    if (motorIdInput) motorIdInput.addEventListener('change', getTargetPosition);

    const advChk = document.getElementById('chk-advanced');
    const saved = localStorage.getItem('advancedMode');
    const advancedOn = saved ? saved === '1' : false;
    if (advChk) {
        advChk.checked = advancedOn;
        applyAdvancedVisibility(advChk.checked);
        advChk.addEventListener('change', (e) => {
            const on = e.target.checked;
            localStorage.setItem('advancedMode', on ? '1' : '0');
            applyAdvancedVisibility(on);
        });
    } else {
        applyAdvancedVisibility(false);
    }

    setFormEnabled(true);

    document.querySelectorAll('output').forEach(formatOutputWithCommas);

    // Initialize servo visualization
    const numServosInput = document.getElementById('NUM_SERVOS');
    const numServos = numServosInput ? parseInt(numServosInput.value) : 31;
    initServoVisualization(numServos);

    // Initialize LUT range from HTML and draw LUT curve based on
    // current hidden LUT_Y* inputs (from server params)
    initLutRangeFromDom();
    drawLUTCurve();

    const lutCanvas = document.getElementById('lut-curve-canvas');
    if (lutCanvas) {
        lutCanvas.addEventListener('mousedown', function (e) {
            e.preventDefault();
            handleLutPointerDown(e.clientX, e.clientY);
        });
        window.addEventListener('mousemove', function (e) {
            if (lutDragIndex !== null) {
                e.preventDefault();
                handleLutPointerMove(e.clientX, e.clientY);
            }
        });
        window.addEventListener('mouseup', function (e) {
            if (lutDragIndex !== null) {
                e.preventDefault();
                handleLutPointerUp(e.clientX, e.clientY);
            }
        });

        // Touch support (simple mapping)
        lutCanvas.addEventListener('touchstart', function (e) {
            const t = e.touches[0];
            if (!t) return;
            e.preventDefault();
            handleLutPointerDown(t.clientX, t.clientY);
        }, { passive: false });
        window.addEventListener('touchmove', function (e) {
            if (lutDragIndex === null) return;
            const t = e.touches[0];
            if (!t) return;
            e.preventDefault();
            handleLutPointerMove(t.clientX, t.clientY);
        }, { passive: false });
        window.addEventListener('touchend', function (e) {
            if (lutDragIndex === null) return;
            const t = e.changedTouches[0] || e.touches[0];
            if (!t) {
                lutDragIndex = null;
                return;
            }
            e.preventDefault();
            handleLutPointerUp(t.clientX, t.clientY);
        }, { passive: false });
    }
});