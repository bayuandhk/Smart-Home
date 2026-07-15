/**
 * Smart Home HMI Dashboard — Socket.IO Client
 * =============================================
 * Mendengarkan event 'update_status' dari server Flask-SocketIO
 * dan memperbarui seluruh elemen DOM secara real-time.
 * Termasuk Chart.js untuk grafik daya.
 */

(function () {
    'use strict';

    // ──────────────────────────────────────────────
    // Constants
    // ──────────────────────────────────────────────
    const ROOMS = ['ruang_tamu', 'dapur', 'teras', 'kamar'];
    const SENSORS = ['fire', 'gas', 'pir'];
    const ROOM_NAMES = {
        ruang_tamu: 'Ruang Tamu',
        dapur: 'Dapur',
        teras: 'Teras',
        kamar: 'Kamar',
    };
    const SENSOR_ICONS = {
        fire: '🔥',
        gas: '💨',
        pir: '👁️',
    };
    const MAX_CHART_POINTS = 20;

    // ──────────────────────────────────────────────
    // Chart.js — Power Chart
    // ──────────────────────────────────────────────
    let powerChart = null;
    const chartLabels = [];
    const voltageData = [];
    const powerData = [];
    const currentData = [];

    function initPowerChart() {
        const ctx = document.getElementById('powerChart');
        if (!ctx || typeof Chart === 'undefined') {
            console.warn('[CHART] Chart.js tidak tersedia');
            return;
        }

        powerChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'Voltage (V)',
                        data: voltageData,
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        borderWidth: 2,
                        pointRadius: 2,
                        pointBackgroundColor: '#6366f1',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Power (W)',
                        data: powerData,
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.08)',
                        borderWidth: 2,
                        pointRadius: 2,
                        pointBackgroundColor: '#fbbf24',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y1',
                    },
                    {
                        label: 'Current (A)',
                        data: currentData,
                        borderColor: '#34d399',
                        backgroundColor: 'rgba(52, 211, 153, 0.06)',
                        borderWidth: 1.5,
                        pointRadius: 1.5,
                        pointBackgroundColor: '#34d399',
                        tension: 0.4,
                        fill: false,
                        yAxisID: 'y1',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 400, easing: 'easeOutQuart' },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#94a3b8',
                            font: { family: "'Inter', sans-serif", size: 10 },
                            boxWidth: 12,
                            padding: 8,
                            usePointStyle: true,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#f1f5f9',
                        bodyColor: '#94a3b8',
                        borderColor: 'rgba(99, 102, 241, 0.3)',
                        borderWidth: 1,
                        cornerRadius: 8,
                        titleFont: { family: "'Inter', sans-serif", size: 11 },
                        bodyFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        ticks: {
                            color: '#475569',
                            font: { family: "'JetBrains Mono', monospace", size: 8 },
                            maxRotation: 0,
                            maxTicksLimit: 6,
                        },
                        grid: { color: 'rgba(99, 102, 241, 0.06)' },
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Voltage (V)',
                            color: '#6366f1',
                            font: { family: "'Inter', sans-serif", size: 9 },
                        },
                        ticks: {
                            color: '#475569',
                            font: { family: "'JetBrains Mono', monospace", size: 9 },
                        },
                        grid: { color: 'rgba(99, 102, 241, 0.06)' },
                        min: 210,
                        max: 230,
                    },
                    y1: {
                        type: 'linear',
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Power (W) / Current (A)',
                            color: '#fbbf24',
                            font: { family: "'Inter', sans-serif", size: 9 },
                        },
                        ticks: {
                            color: '#475569',
                            font: { family: "'JetBrains Mono', monospace", size: 9 },
                        },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    function updateChart(telemetry) {
        if (!powerChart) return;

        const now = new Date();
        const timeLabel = now.toLocaleTimeString('id-ID', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });

        chartLabels.push(timeLabel);
        voltageData.push(telemetry.voltage);
        powerData.push(telemetry.power);
        currentData.push(telemetry.current);

        // Batasi jumlah data point
        if (chartLabels.length > MAX_CHART_POINTS) {
            chartLabels.shift();
            voltageData.shift();
            powerData.shift();
            currentData.shift();
        }

        powerChart.update('none'); // skip animation for smoother updates
    }

    // ──────────────────────────────────────────────
    // Socket.IO Connection
    // ──────────────────────────────────────────────
    const socket = io();

    const connStatus = document.getElementById('connection-status');
    const connText = document.getElementById('connection-text');

    socket.on('connect', () => {
        console.log('[WS] Connected to server');
        connStatus.classList.remove('disconnected');
        connText.textContent = 'Connected';
    });

    socket.on('disconnect', () => {
        console.warn('[WS] Disconnected from server');
        connStatus.classList.add('disconnected');
        connText.textContent = 'Disconnected';
    });

    socket.on('connect_error', () => {
        connStatus.classList.add('disconnected');
        connText.textContent = 'Error';
    });

    // ──────────────────────────────────────────────
    // Initialize Device List Panel
    // ──────────────────────────────────────────────
    function initDeviceList() {
        const container = document.getElementById('device-list');
        container.innerHTML = '';

        ROOMS.forEach((room) => {
            const div = document.createElement('div');
            div.className = 'device-room';
            div.id = `device-room-${room}`;

            div.innerHTML = `
                <div class="room-name">${ROOM_NAMES[room]}</div>
                <div class="device-row">
                    <span class="device-indicator lamp off" id="panel-lamp-${room}">
                        💡 OFF
                    </span>
                    ${SENSORS.map(
                        (s) => `
                        <span class="device-indicator sensor safe" id="panel-sensor-${room}-${s}">
                            ${SENSOR_ICONS[s]} ${s.toUpperCase()}
                        </span>`
                    ).join('')}
                </div>
            `;

            container.appendChild(div);
        });
    }

    // ──────────────────────────────────────────────
    // Update Functions
    // ──────────────────────────────────────────────

    /** Update telemetry metric values with animation */
    function updateTelemetry(telemetry) {
        const fields = [
            { id: 'val-voltage', key: 'voltage', unit: 'V', decimals: 1 },
            { id: 'val-current', key: 'current', unit: 'A', decimals: 2 },
            { id: 'val-power', key: 'power', unit: 'W', decimals: 1 },
            { id: 'val-energy', key: 'energy', unit: 'kWh', decimals: 4 },
        ];

        fields.forEach(({ id, key, unit, decimals }) => {
            const el = document.getElementById(id);
            if (!el) return;

            const value = parseFloat(telemetry[key]).toFixed(decimals);
            el.innerHTML = `${value}<span class="metric-unit">${unit}</span>`;

            // Flash animation
            el.classList.add('updated');
            setTimeout(() => el.classList.remove('updated'), 500);

            // Card highlight
            const card = el.closest('.metric-card');
            if (card) {
                card.classList.add('fade-update');
                setTimeout(() => card.classList.remove('fade-update'), 600);
            }
        });

        // Update chart
        updateChart(telemetry);
    }

    /** Update overlay lamp icons and panel indicators */
    function updateLamps(lamps) {
        ROOMS.forEach((room) => {
            const isOn = lamps[room];

            // Overlay Lamp (HTML div)
            const overlayLamp = document.getElementById(`lamp-${room}`);
            if (overlayLamp) {
                overlayLamp.classList.toggle('on', isOn);
                overlayLamp.classList.toggle('off', !isOn);
            }

            // Panel Lamp
            const panelLamp = document.getElementById(`panel-lamp-${room}`);
            if (panelLamp) {
                panelLamp.className = `device-indicator lamp ${isOn ? 'on' : 'off'}`;
                panelLamp.innerHTML = `💡 ${isOn ? 'ON' : 'OFF'}`;
            }
        });
    }

    /** Update overlay sensor icons and panel indicators */
    function updateSensors(sensors) {
        ROOMS.forEach((room) => {
            SENSORS.forEach((sensor) => {
                const status = sensors[room]?.[sensor] || 'AMAN';
                const isActive = status === 'ACTIVE';

                // Overlay Sensor (HTML div)
                const overlaySensor = document.getElementById(`sensor-${room}-${sensor}`);
                if (overlaySensor) {
                    overlaySensor.classList.toggle('safe', !isActive);
                    overlaySensor.classList.toggle('active', isActive);
                }

                // Panel Sensor
                const panelSensor = document.getElementById(`panel-sensor-${room}-${sensor}`);
                if (panelSensor) {
                    panelSensor.className = `device-indicator sensor ${isActive ? 'active' : 'safe'}`;
                    panelSensor.innerHTML = `${SENSOR_ICONS[sensor]} ${sensor.toUpperCase()}`;
                }
            });
        });
    }

    /** Update gate animation — overlay (HTML) and panel */
    function updateGate(gateStatus) {
        const isOpen = gateStatus === 'OPEN';

        // ── Overlay Gate (on denah image) ──
        const overlayGate = document.getElementById('overlay-gate');
        const overlayLabel = document.getElementById('overlay-gate-label');

        if (overlayGate) {
            overlayGate.classList.toggle('open', isOpen);
        }

        if (overlayLabel) {
            overlayLabel.textContent = isOpen ? 'OPEN' : 'CLOSED';
            overlayLabel.className = `overlay-gate-label ${isOpen ? 'open' : 'closed'}`;
        }

        // ── Panel Gate ──
        const panelVisual = document.getElementById('gate-visual-panel');
        const panelLabel = document.getElementById('gate-label-panel');

        if (panelVisual) {
            panelVisual.className = `gate-visual ${isOpen ? 'open' : ''}`;
        }

        if (panelLabel) {
            panelLabel.textContent = isOpen ? '● OPEN' : '● CLOSED';
            panelLabel.className = `gate-label ${isOpen ? 'open' : 'closed'}`;
        }
    }

    /** Update timestamp display */
    function updateTimestamp(timestamp) {
        const el = document.getElementById('timestamp-display');
        if (el && timestamp) {
            el.textContent = timestamp;
        }
    }

    // ──────────────────────────────────────────────
    // Main Event Handler
    // ──────────────────────────────────────────────
    socket.on('update_status', (data) => {
        console.log('[WS] Data diterima:', data);

        if (data.telemetry) updateTelemetry(data.telemetry);
        if (data.lamps) updateLamps(data.lamps);
        if (data.sensors) updateSensors(data.sensors);
        if (data.gate) updateGate(data.gate);
        if (data.timestamp) updateTimestamp(data.timestamp);
    });

    // ──────────────────────────────────────────────
    // Init
    // ──────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        initDeviceList();
        initPowerChart();
        console.log('[APP] Smart Home HMI Dashboard initialized');
    });
})();
