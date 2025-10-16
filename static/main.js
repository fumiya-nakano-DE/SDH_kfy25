const socket = io();

function formatOutputWithCommas(outputElement) {
    const value = parseFloat(outputElement.textContent);
    if (!isNaN(value)) {
        outputElement.textContent = value.toLocaleString();
    }
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
        if (form) Array.from(form.elements).forEach(el => { el.disabled = !enabled; });
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
});

window.addEventListener('DOMContentLoaded', function () {

    window.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            sendHalt();
        }
    });

    const motorIdInput = document.getElementById('motor-id-input');
    if (motorIdInput) motorIdInput.addEventListener('change', getTargetPosition);

    document.querySelectorAll('output').forEach(formatOutputWithCommas);
});