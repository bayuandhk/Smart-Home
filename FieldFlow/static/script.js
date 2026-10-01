/**
 * Smart Home HMI Dashboard — Socket.IO Runtime Client
 * Versi: Data-Driven UI (Dynamic Zones & Active Bidirectional Control)
 */

(function () {
    'use strict';

    const MAX_CHART_POINTS = 20;
    const ALARM_PRIORITY = ['fire', 'gas', 'smoke', 'flood', 'door', 'pir'];

    let powerChart = null;
    const chartLabels = [];
    const voltageData = [];
    const powerData = [];
    const currentData = [];

    let activeAlarm = null;
    let audioCtx = null;
    let oscillator = null;
    let buzzerGain = null;
    let buzzerTimer = null;

    let registeredWidgets = [];
    const socket = typeof io === 'function' ? io({ transports: ['polling'] }) : null;

    // 1. Baca data widget dinamis dari database SQLite (via index.html)
    function loadRegisteredWidgets() {
        try {
            const rawJson = document.getElementById('init-dashboard-widgets')?.textContent;
            registeredWidgets = JSON.parse(rawJson || '[]');
            console.log('[WEB UI] Berhasil memuat widget dinamis:', registeredWidgets.length, 'perangkat');
        } catch (e) {
            console.error('[WEB UI] Gagal membaca data widget dasbor:', e);
            registeredWidgets = [];
        }
    }

    // 2. Render panel kanan dinamis berdasarkan zone_name
    // 2. Render panel kanan dinamis berdasarkan zone_name
    function initDeviceList() {
        const container = document.getElementById('device-list');
        if (!container) return;
        container.innerHTML = '';

        if (!registeredWidgets || registeredWidgets.length === 0) {
            container.innerHTML = '<div style="padding: 14px; text-align: center; color: #7f91ad; font-size: 0.72rem;">Belum ada perangkat dikonfigurasi di SH Studio.</div>';
            return;
        }

        const groupedZones = {};
        registeredWidgets.forEach((w) => {

            if (w.widget_type === 'GATE_CONTROL') {
                return;
            }

            const zone = w.zone_name || 'Area Umum';
            if (!groupedZones[zone]) groupedZones[zone] = [];
            groupedZones[zone].push(w);
        });

        Object.keys(groupedZones).forEach((zone) => {
            const item = document.createElement('div');
            item.className = 'device-room';

            const nameDiv = document.createElement('div');
            nameDiv.className = 'room-name';
            nameDiv.title = zone;
            nameDiv.textContent = zone;

            const rowDiv = document.createElement('div');
            rowDiv.className = 'device-row';

            groupedZones[zone].forEach((w) => {
                const badge = document.createElement('span');
                badge.id = `panel-badge-${w.widget_id}`;
                badge.style.cursor = 'pointer';
                badge.title = `Klik untuk kontrol manual: ${w.label_name}`;

                const isSensor = w.widget_type.startsWith('SENSOR_');
                badge.className = `device-indicator ${isSensor ? 'sensor safe' : 'lamp off'}`;
                badge.innerHTML = `${w.icon} ${w.label_name.toUpperCase()} ${isSensor ? 'AMAN' : 'OFF'}`;

                if (!isSensor) {
                    badge.addEventListener('click', () => {
                        if (!socket || !socket.connected) {
                            alert('⚠️ Koneksi terputus! Tidak dapat mengirim perintah ke server.');
                            return;
                        }
                        const ch = w.mapping ? w.mapping.channel_index : 0;
                        console.log(`[WEB UI] Kontrol manual dari badge: relay_${ch} (${w.label_name})`);
                        socket.emit('control_relay', {
                            device: `relay_${ch}`,
                            state: 'TOGGLE'
                        });
                    });
                }

                rowDiv.appendChild(badge);
            });

            item.appendChild(nameDiv);
            item.appendChild(rowDiv);
            container.appendChild(item);
        });
    }

    // 3. Pembaruan status real-time untuk ikon denah & panel kanan
    // 3. Pembaruan status real-time untuk ikon denah & panel kanan
    function updateDynamicDevices(data = {}) {
        const relays = data.relays || {};
        const alarms = data.alarms || {};

        if (!registeredWidgets || registeredWidgets.length === 0) return;

        registeredWidgets.forEach((w) => {
            const badge = document.getElementById(`panel-badge-${w.widget_id}`);
            
            // Cari ikon di atas denah dengan berbagai kemungkinan nama ID atau atribut title
            const overlay = document.getElementById(`lamp-${w.label_name}`) ||
                            document.getElementById(`sensor-${w.label_name}`) ||
                            document.getElementById(`w_${w.id}`) ||
                            document.getElementById(w.label_name) ||
                            document.querySelector(`[title="${w.label_name}"]`) ||
                            document.querySelector(`[title="${w.label_name.toUpperCase()}"]`);

            if (['LAMP_INDICATOR', 'PUMP_CONTROL', 'FAN_CONTROL', 'SMART_PLUG'].includes(w.widget_type)) {
                const ch = w.mapping ? w.mapping.channel_index : 0;
                const isOn = Boolean(relays[`relay_${ch}`]);

                if (badge) {
                    badge.className = `device-indicator lamp ${isOn ? 'on' : 'off'}`;
                    badge.innerHTML = `${w.icon} ${w.label_name.toUpperCase()} ${isOn ? 'ON' : 'OFF'}`;
                }
                if (overlay) {
                    overlay.classList.toggle('on', isOn);
                    overlay.classList.toggle('off', !isOn);
                    if (w.widget_type === 'PUMP_CONTROL') {
                        overlay.classList.toggle('pos-pompa', isOn);
                    }
                }
                
            // =========================================================
            // KUNCI PERBAIKAN 1: Tambahkan handler dinamis untuk Gerbang
            // =========================================================
            } else if (w.widget_type === 'GATE_CONTROL') {
                const ch = w.mapping ? w.mapping.channel_index : 7;
                const isOpen = Boolean(relays[`relay_${ch}`]);
                updateGate(isOpen ? 'OPEN' : 'CLOSED');
                
                // Update teks keterangan channel di UI Access Control
                const desc = document.querySelector('.gate-description');
                if (desc) desc.textContent = `Relay channel ${ch}`;
            // =========================================================

            } else if (w.widget_type.startsWith('SENSOR_')) {
                let alarmKey = 'pir';
                if (w.widget_type === 'SENSOR_FIRE') alarmKey = 'fire';
                if (w.widget_type === 'SENSOR_GAS') alarmKey = 'gas';

                const isActive = Boolean(alarms[alarmKey]);
                if (badge) {
                    badge.className = `device-indicator sensor ${isActive ? 'active' : 'safe'}`;
                    badge.innerHTML = `${w.icon} ${w.label_name.toUpperCase()} ${isActive ? 'ALARM!' : 'AMAN'}`;
                }
                if (overlay) {
                    overlay.classList.toggle('active', isActive);
                    overlay.classList.toggle('safe', !isActive);
                }
            }
        });
    }

    function updateGate(gateStatus) {
        const isOpen = gateStatus === 'OPEN';
        const overlayGate = document.getElementById('overlay-gate');
        const overlayLabel = document.getElementById('overlay-gate-label');
        const panelVisual = document.getElementById('gate-visual-panel');
        const panelLabel = document.getElementById('gate-label-panel');

        overlayGate?.classList.toggle('open', isOpen);
        panelVisual?.classList.toggle('open', isOpen);

        if (overlayLabel) {
            overlayLabel.textContent = isOpen ? 'OPEN' : 'CLOSED';
            overlayLabel.className = `overlay-gate-label ${isOpen ? 'open' : 'closed'}`;
        }
        if (panelLabel) {
            panelLabel.textContent = isOpen ? '● OPEN' : '● CLOSED';
            panelLabel.className = `gate-label ${isOpen ? 'open' : 'closed'}`;
        }
    }

    function initTooltips() {
        if (!registeredWidgets) return;
        registeredWidgets.forEach(w => {
            if (['SENSOR_TEMP', 'SENSOR_GAS', 'SENSOR_POWER'].includes(w.widget_type)) {
                let widgetEl = document.getElementById('sensor-' + w.label_name);
                if (widgetEl) {
                    let tooltip = document.createElement('div');
                    tooltip.className = 'sensor-tooltip';
                    tooltip.id = 'tooltip_' + w.id;
                    tooltip.innerText = 'WAITING...';
                    
                    widgetEl.appendChild(tooltip);
                    widgetEl.classList.add('has-data');
                    widgetEl.style.position = 'absolute'; 
                }
            }
        });
    }

    function applyWidgetPositions() {
        document.querySelectorAll('#denah-wrapper [data-pos-x][data-pos-y]').forEach((el) => {
            const x = el.getAttribute('data-pos-x');
            const y = el.getAttribute('data-pos-y');
            if (x !== null && y !== null) {
                el.style.left = `${x}%`;
                el.style.top = `${y}%`;
            }
        });
    }

    // 4. Kontrol aktif gerbang
    window.commandGate = function (actionType = 'TOGGLE') {
        if (!socket || !socket.connected) {
            alert('⚠️ Koneksi terputus! Tidak dapat mengirim perintah ke server.');
            return;
        }
        
        // Cari widget gerbang untuk mendapatkan mapping channel-nya secara dinamis
        const gateWidget = registeredWidgets.find(w => w.widget_type === 'GATE_CONTROL');
        const ch = gateWidget && gateWidget.mapping ? gateWidget.mapping.channel_index : 7;
        
        // Optimistic UI Update: Langsung respons visual tanpa jeda round-trip jaringan
        const overlayGate = document.getElementById('overlay-gate');
        const isCurrentlyOpen = overlayGate ? overlayGate.classList.contains('open') : false;
        const nextState = (actionType === 'TOGGLE') ? !isCurrentlyOpen : (actionType === 'OPEN' || actionType === true);
        updateGate(nextState ? 'OPEN' : 'CLOSED');

        console.log('[WEB UI] Mengirim perintah kontrol gerbang:', actionType, 'ke channel', ch);
        
        // Gunakan Universal Relay event agar Backend memprosesnya secara konsisten
        socket.emit('control_relay', {
            device: `relay_${ch}`,
            state: actionType
        });
    };

    function initGateControls() {
        const overlayGate = document.getElementById('overlay-gate');
        const gatePanel = document.getElementById('gate-visual-panel');

        if (overlayGate) {
            overlayGate.style.cursor = 'pointer';
            overlayGate.title = 'Klik untuk Membuka / Menutup Gerbang';
            overlayGate.addEventListener('click', () => window.commandGate('TOGGLE'));
        }
        if (gatePanel) {
            gatePanel.style.cursor = 'pointer';
            gatePanel.title = 'Klik untuk Membuka / Menutup Gerbang';
            gatePanel.addEventListener('click', () => window.commandGate('TOGGLE'));
        }
    }

    // 5. Chart & Telemetry
    function initPowerChart() {
        const canvas = document.getElementById('powerChart');
        if (!canvas || typeof Chart === 'undefined') return;

        const gridColor = 'rgba(145, 174, 218, 0.08)';
        const tickColor = '#7385a0';

        powerChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'Voltage (V)', data: voltageData,
                        borderColor: '#3c8cff', backgroundColor: 'rgba(10, 78, 190, 0.18)',
                        borderWidth: 2, pointRadius: 0, pointHoverRadius: 4,
                        tension: 0.36, fill: true, yAxisID: 'y',
                    },
                    {
                        label: 'Power (W)', data: powerData,
                        borderColor: '#f7b731', backgroundColor: 'rgba(247, 183, 49, 0.05)',
                        borderWidth: 1.8, pointRadius: 0, pointHoverRadius: 4,
                        tension: 0.36, fill: false, yAxisID: 'y1',
                    },
                    {
                        label: 'Current (A)', data: currentData,
                        borderColor: '#22c98b', backgroundColor: 'rgba(34, 201, 139, 0.04)',
                        borderWidth: 1.6, pointRadius: 0, pointHoverRadius: 4,
                        tension: 0.36, fill: false, yAxisID: 'y1',
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 320, easing: 'easeOutQuart' },
                interaction: { mode: 'index', intersect: false },
                normalized: true,
                plugins: {
                    legend: {
                        position: 'bottom', align: 'start',
                        labels: { color: '#8fa0ba', boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle', padding: 14, font: { family: 'Inter', size: 9, weight: '600' } },
                    },
                    tooltip: { backgroundColor: 'rgba(4, 12, 25, 0.96)', borderColor: 'rgba(80, 145, 241, 0.35)', borderWidth: 1, titleColor: '#ffffff', bodyColor: '#c0cce0', padding: 10, displayColors: true },
                },
                scales: {
                    x: { display: true, grid: { color: gridColor, drawBorder: false }, border: { display: false }, ticks: { color: tickColor, maxTicksLimit: 5, font: { family: 'JetBrains Mono', size: 8 } } },
                    y: { type: 'linear', position: 'left', suggestedMin: 210, suggestedMax: 230, grid: { color: gridColor, drawBorder: false }, border: { display: false }, ticks: { color: tickColor, maxTicksLimit: 5, font: { family: 'JetBrains Mono', size: 8 } } },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, border: { display: false }, ticks: { color: tickColor, maxTicksLimit: 5, font: { family: 'JetBrains Mono', size: 8 } } },
                },
            },
        });
    }

    function updateChart(telemetry) {
        if (!powerChart) return;
        const voltage = Number(telemetry.voltage);
        const power = Number(telemetry.power);
        const current = Number(telemetry.current);

        if (![voltage, power, current].every(Number.isFinite)) return;

        const timeLabel = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        chartLabels.push(timeLabel);
        voltageData.push(voltage);
        powerData.push(power);
        currentData.push(current);

        if (chartLabels.length > MAX_CHART_POINTS) {
            chartLabels.shift(); voltageData.shift(); powerData.shift(); currentData.shift();
        }
        powerChart.update('none');
    }

    function updateTelemetry(telemetry) {
        const fields = [
            { id: 'val-voltage', key: 'voltage', unit: 'V', decimals: 1 },
            { id: 'val-current', key: 'current', unit: 'A', decimals: 2 },
            { id: 'val-power', key: 'power', unit: 'W', decimals: 1 },
            { id: 'val-energy', key: 'energy', unit: 'kWh', decimals: 4 },
        ];

        fields.forEach(({ id, key, unit, decimals }) => {
            const element = document.getElementById(id);
            const numericValue = Number(telemetry[key]);
            if (!element || !Number.isFinite(numericValue)) return;

            element.innerHTML = `${numericValue.toFixed(decimals)}<span class="metric-unit">${unit}</span>`;
            element.classList.add('updated');
            window.setTimeout(() => element.classList.remove('updated'), 450);
        });
        updateChart(telemetry);
    }

    function updateTimestamp(timestamp) {
        const element = document.getElementById('timestamp-display');
        if (element) element.textContent = timestamp;
    }

    // 6. Alarm & Buzzer Audio
    function playBuzzer() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass || oscillator) return;
        audioCtx = audioCtx || new AudioContextClass();
        if (audioCtx.state === 'suspended') audioCtx.resume();

        oscillator = audioCtx.createOscillator();
        buzzerGain = audioCtx.createGain();
        oscillator.type = 'square';
        oscillator.frequency.setValueAtTime(850, audioCtx.currentTime);
        buzzerGain.gain.value = 0.12;

        oscillator.connect(buzzerGain);
        buzzerGain.connect(audioCtx.destination);
        oscillator.start();

        buzzerTimer = window.setInterval(() => {
            if (!buzzerGain) return;
            buzzerGain.gain.value = buzzerGain.gain.value > 0 ? 0 : 0.12;
        }, 300);
    }

    function stopBuzzer() {
        if (buzzerTimer) { window.clearInterval(buzzerTimer); buzzerTimer = null; }
        if (oscillator) {
            try { oscillator.stop(); } catch (e) { console.debug(e); }
            oscillator.disconnect(); oscillator = null;
        }
        if (buzzerGain) { buzzerGain.disconnect(); buzzerGain = null; }
    }

    window.acknowledgeAlarm = function acknowledgeAlarm() {
        if (!activeAlarm) return;
        document.getElementById('alarm-overlay')?.classList.remove('active');
        stopBuzzer();
        if (socket) socket.emit('alarm_ack_web', { alarm: activeAlarm });
        activeAlarm = null;
    };

    window.triggerEmergency = function triggerEmergency() {
        const confirmed = window.confirm('⚠️ DANGER: Apakah Anda yakin ingin memicu EMERGENCY ALARM ke seluruh sistem dan pager?');
        if (!confirmed) return;
        if (!socket) {
            window.alert('Koneksi Socket.IO belum tersedia. Perintah emergency tidak dikirim.');
            return;
        }
        console.warn('[WEB UI] Mengirim sinyal emergency ke server.');
        socket.emit('trigger_emergency', { timestamp: Date.now(), initiator: 'web_dashboard' });
    };

    // 7. WebSocket Events Binding
    function bindSocketEvents() {
        const connectionStatus = document.getElementById('connection-status');
        const connectionText = document.getElementById('connection-text');

        if (!socket) {
            connectionStatus?.classList.add('disconnected');
            if (connectionText) connectionText.textContent = 'Library unavailable';
            return;
        }

        socket.on('connect', () => {
            connectionStatus?.classList.remove('disconnected');
            if (connectionText) connectionText.textContent = 'Connected';
        });

        socket.on('disconnect', () => {
            connectionStatus?.classList.add('disconnected');
            if (connectionText) connectionText.textContent = 'Disconnected';
        });

        socket.on('alarm_update', (alarms = {}) => {
            const highestPriority = ALARM_PRIORITY.find((type) => alarms[type] === true) || null;
            const overlay = document.getElementById('alarm-overlay');
            const title = document.getElementById('alarm-title-text');

            if (highestPriority) {
                activeAlarm = highestPriority;
                overlay?.classList.add('active');
                if (title) title.textContent = `${highestPriority.toUpperCase()} ALARM`;
                playBuzzer();
            } else {
                activeAlarm = null;
                overlay?.classList.remove('active');
                stopBuzzer();
            }
        });

        socket.on('update_status', (data = {}) => {
            if (data.telemetry) updateTelemetry(data.telemetry);
            if (data.timestamp) updateTimestamp(data.timestamp);

            updateDynamicDevices(data);
            if (!registeredWidgets) return;
            registeredWidgets.forEach(w => {
                let tooltip = document.getElementById('tooltip_' + w.id);
                if (!tooltip) return;

                let valText = '';
                const inst = (data.instances && w.label_name) ? data.instances[w.label_name] : null;

                if (w.widget_type === 'SENSOR_TEMP') {
                    if (inst && inst.temperature !== undefined && inst.temperature !== null) {
                        valText = Number(inst.temperature).toFixed(1) + ' °C';
                    } else if (data.environment && data.environment.temperature && (!data.instances || Object.keys(data.instances).length === 0)) {
                        valText = Number(data.environment.temperature).toFixed(1) + ' °C';
                    }
                } 
                else if (w.widget_type === 'SENSOR_GAS') {
                    if (inst && (inst.raw !== undefined || inst.val !== undefined)) {
                        const gVal = inst.raw !== undefined ? inst.raw : inst.val;
                        valText = Number(gVal).toFixed(1) + ' ppm';
                    } else if (data.environment && data.environment.gas_ppm) {
                        valText = Number(data.environment.gas_ppm).toFixed(1) + ' ppm';
                    }
                } 
                else if (w.widget_type === 'SENSOR_POWER') {
                    if (inst && inst.val !== undefined) {
                        valText = Number(inst.val).toFixed(1) + ' W';
                    } else if (data.telemetry && data.telemetry.power) {
                        valText = Number(data.telemetry.power).toFixed(1) + ' W';
                    }
                }

                if (valText !== '' && tooltip.innerText !== valText) {
                    tooltip.innerText = valText;
                    
                    // Efek kedip neon saat angka berubah
                    tooltip.classList.remove('tooltip-flash');
                    void tooltip.offsetWidth; 
                    tooltip.classList.add('tooltip-flash');
                }
            });
        });
    }

    // 7b. Penyesuaian Responsif Denah (Fit Tanpa Terpotong pada Display HMI 7 Inci)
    function syncDenahDimensions() {
        const container = document.getElementById('denah-container');
        const wrapper = document.getElementById('denah-wrapper');
        const image = document.getElementById('denah-image');
        if (!container || !wrapper || !image) return;

        // Jika gambar belum selesai loading, pasang listener
        if (!image.naturalWidth || !image.naturalHeight) {
            image.addEventListener('load', syncDenahDimensions, { once: true });
            return;
        }

        const containerStyle = window.getComputedStyle(container);
        const padX = (parseFloat(containerStyle.paddingLeft) || 0) + (parseFloat(containerStyle.paddingRight) || 0);
        const padY = (parseFloat(containerStyle.paddingTop) || 0) + (parseFloat(containerStyle.paddingBottom) || 0);

        const availW = Math.max(100, container.clientWidth - padX);
        const availH = Math.max(100, container.clientHeight - padY);

        const natW = image.naturalWidth;
        const natH = image.naturalHeight;
        const ratio = natW / natH;

        let targetW = availW;
        let targetH = targetW / ratio;

        if (targetH > availH) {
            targetH = availH;
            targetW = targetH * ratio;
        }

        wrapper.style.width = `${Math.floor(targetW)}px`;
        wrapper.style.height = `${Math.floor(targetH)}px`;
    }

    // 7c. Navigasi Cepat Tab HMI (Layar 7 Inci)
    window.switchHmiTab = function (tabName) {
        const btnDenah = document.getElementById('tab-btn-denah');
        const btnTelemetry = document.getElementById('tab-btn-telemetry');
        if (btnDenah && btnTelemetry) {
            if (tabName === 'telemetry') {
                btnDenah.classList.remove('active');
                btnTelemetry.classList.add('active');
                document.body.classList.add('hmi-view-telemetry');
            } else {
                btnTelemetry.classList.remove('active');
                btnDenah.classList.add('active');
                document.body.classList.remove('hmi-view-telemetry');
                setTimeout(syncDenahDimensions, 30);
            }
        }
    };

    document.addEventListener('keydown', (event) => {
        const overlay = document.getElementById('alarm-overlay');
        if (event.key === 'Enter' && overlay?.classList.contains('active')) {
            window.acknowledgeAlarm();
        }
    });

    // 8. Inisialisasi DOM
    document.addEventListener('DOMContentLoaded', () => {
        loadRegisteredWidgets();
        applyWidgetPositions();
        initDeviceList();
        initGateControls();
        initPowerChart();
        initTooltips();
        bindSocketEvents();

        // Inisialisasi auto-scale denah agar pas di layar 7 inci
        syncDenahDimensions();
        window.addEventListener('resize', syncDenahDimensions);
        const denahImg = document.getElementById('denah-image');
        if (denahImg) {
            denahImg.addEventListener('load', syncDenahDimensions);
        }
        if (window.ResizeObserver) {
            const container = document.getElementById('denah-container');
            if (container) {
                new ResizeObserver(() => syncDenahDimensions()).observe(container);
            }
        }

        console.log('[APP] Smart Home HMI Dashboard initialized (Adaptive & Bidirectional Mode)');
    });
})();



