/* ============================================
   ReconAI — Application Logic (Hardcoded Demo)
   ============================================ */

// ============ PAGE NAVIGATION ============
function switchPage(pageName, el) {
  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  // Show target page
  const target = document.getElementById('page-' + pageName);
  if (target) target.classList.add('active');

  // Update nav
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (el) el.classList.add('active');

  // Update header
  const titles = {
    'dashboard': ['Dashboard', 'Real-time reconciliation overview'],
    'reconciliation': ['Reconciliation', 'Side-by-side transaction matching'],
    'exceptions': ['Exception Report', 'AI-generated exception analysis'],
    'analytics': ['Analytics', 'Performance metrics and insights'],
    'ai-agent': ['AI Agent', 'Conversational settlement assistant'],
    'audit-log': ['Audit Log', 'Complete system audit trail']
  };
  const titleEl = document.getElementById('pageTitle');
  const subtitleEl = document.querySelector('.header-subtitle');
  if (titles[pageName]) {
    titleEl.textContent = titles[pageName][0];
    subtitleEl.textContent = titles[pageName][1];
  }
}

// ============ COUNTER ANIMATION ============
function animateCounters() {
  const counters = document.querySelectorAll('.counter');
  counters.forEach(counter => {
    const target = parseInt(counter.getAttribute('data-target'));
    const duration = 2000;
    const start = performance.now();

    function update(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      counter.textContent = Math.floor(eased * target).toLocaleString();
      if (progress < 1) {
        requestAnimationFrame(update);
      } else {
        counter.textContent = target.toLocaleString();
      }
    }
    requestAnimationFrame(update);
  });
}

// ============ CHART RENDERING ============
function drawTrendChart() {
  const canvas = document.getElementById('trendChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  
  canvas.width = canvas.offsetWidth * dpr;
  canvas.height = canvas.offsetHeight * dpr;
  ctx.scale(dpr, dpr);

  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight;
  const padding = { top: 20, right: 20, bottom: 40, left: 50 };

  // Data
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const processed = [2100, 2350, 2500, 2680, 2750, 2400, 2847];
  const matched = [1980, 2240, 2380, 2550, 2620, 2280, 2691];
  const exceptions = [120, 110, 120, 130, 130, 120, 156];

  const maxVal = Math.max(...processed) * 1.1;
  const chartW = w - padding.left - padding.right;
  const chartH = h - padding.top - padding.bottom;

  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    // Y labels
    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter';
    ctx.textAlign = 'right';
    ctx.fillText(val.toLocaleString(), padding.left - 10, y + 4);
  }

  // X labels
  days.forEach((day, i) => {
    const x = padding.left + (chartW / (days.length - 1)) * i;
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(day, x, h - 10);
  });

  // Draw lines
  function drawLine(data, color, fill) {
    const points = data.map((val, i) => ({
      x: padding.left + (chartW / (data.length - 1)) * i,
      y: padding.top + chartH - (val / maxVal) * chartH
    }));

    // Fill gradient
    if (fill) {
      const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
      gradient.addColorStop(0, color.replace('1)', '0.15)').replace('rgb', 'rgba'));
      gradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.moveTo(points[0].x, padding.top + chartH);
      points.forEach(p => ctx.lineTo(p.x, p.y));
      ctx.lineTo(points[points.length - 1].x, padding.top + chartH);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    // Line
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    // Dots
    points.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#0a0e1a';
      ctx.fill();
    });
  }

  drawLine(processed, '#6366F1', true);
  drawLine(matched, '#10B981', true);
  drawLine(exceptions, '#F59E0B', false);
}

function drawDonutChart() {
  const canvas = document.getElementById('donutChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  canvas.width = canvas.offsetWidth * dpr;
  canvas.height = canvas.offsetHeight * dpr;
  ctx.scale(dpr, dpr);

  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight;
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2 - 20;
  const lineWidth = 20;

  const data = [
    { value: 94.5, color: '#10B981', label: 'Matched' },
    { value: 3.7, color: '#F59E0B', label: 'Exceptions' },
    { value: 0.8, color: '#EF4444', label: 'Unresolved' },
    { value: 1.0, color: '#3B82F6', label: 'Pending' }
  ];

  let startAngle = -Math.PI / 2;
  data.forEach(segment => {
    const sliceAngle = (segment.value / 100) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, startAngle + sliceAngle);
    ctx.strokeStyle = segment.color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();
    startAngle += sliceAngle + 0.02; // tiny gap
  });
}

function drawMonthlyChart() {
  const canvas = document.getElementById('monthlyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  canvas.width = canvas.offsetWidth * dpr;
  canvas.height = canvas.offsetHeight * dpr;
  ctx.scale(dpr, dpr);

  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight;
  const padding = { top: 20, right: 20, bottom: 40, left: 50 };

  const months = ['Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'];
  const volumes = [18500, 22400, 28900, 35100, 41200, 48700, 52300];
  const maxVal = Math.max(...volumes) * 1.15;
  const chartW = w - padding.left - padding.right;
  const chartH = h - padding.top - padding.bottom;
  const barWidth = chartW / months.length * 0.5;

  // Grid
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter';
    ctx.textAlign = 'right';
    ctx.fillText((val / 1000).toFixed(0) + 'K', padding.left - 10, y + 4);
  }

  // Bars
  months.forEach((month, i) => {
    const x = padding.left + (chartW / months.length) * i + (chartW / months.length - barWidth) / 2;
    const barH = (volumes[i] / maxVal) * chartH;
    const y = padding.top + chartH - barH;

    // Gradient bar
    const gradient = ctx.createLinearGradient(x, y, x, padding.top + chartH);
    gradient.addColorStop(0, '#6366F1');
    gradient.addColorStop(1, '#8B5CF6');

    ctx.beginPath();
    // Rounded top
    const r = 4;
    ctx.moveTo(x, padding.top + chartH);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.lineTo(x + barWidth - r, y);
    ctx.quadraticCurveTo(x + barWidth, y, x + barWidth, y + r);
    ctx.lineTo(x + barWidth, padding.top + chartH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Label
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(month, x + barWidth / 2, h - 10);

    // Value on top
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px Inter';
    ctx.fillText((volumes[i] / 1000).toFixed(1) + 'K', x + barWidth / 2, y - 8);
  });
}

// ============ RECONCILIATION ANIMATION ============
function runReconciliation() {
  const progress = document.getElementById('reconProgress');
  progress.style.display = 'block';
  
  const bar = document.getElementById('progressBar');
  const percent = document.getElementById('progressPercent');
  const steps = ['step1', 'step2', 'step3', 'step4'];

  let current = 0;
  const stages = [
    { progress: 25, step: 0, label: 'Loading Sources...' },
    { progress: 55, step: 1, label: 'AI Matching...' },
    { progress: 80, step: 2, label: 'Fuzzy Resolution...' },
    { progress: 100, step: 3, label: 'Exception Report Complete' }
  ];

  function nextStage() {
    if (current >= stages.length) return;

    const stage = stages[current];
    bar.style.width = stage.progress + '%';
    percent.textContent = stage.progress + '%';

    // Update steps
    steps.forEach((s, i) => {
      const el = document.getElementById(s);
      if (i < stage.step) {
        el.classList.remove('active');
        el.classList.add('done');
        el.querySelector('.step-icon').textContent = '✓';
      } else if (i === stage.step) {
        el.classList.add('active');
        el.classList.remove('done');
      }
    });

    if (current === stages.length - 1) {
      const el = document.getElementById(steps[stage.step]);
      setTimeout(() => {
        el.classList.remove('active');
        el.classList.add('done');
        el.querySelector('.step-icon').textContent = '✓';
      }, 800);
    }

    current++;
    if (current < stages.length) {
      setTimeout(nextStage, 1200);
    }
  }

  // Reset
  bar.style.width = '0%';
  percent.textContent = '0%';
  steps.forEach(s => {
    const el = document.getElementById(s);
    el.classList.remove('active', 'done');
  });

  setTimeout(nextStage, 500);
}

// ============ BACKEND API INTEGRATION ============
let API_BASE_URL = '';

async function checkBackendConnection() {
  const candidates = [
    window.location.origin,
    'http://localhost:8000',
    'http://localhost:5000'
  ];

  for (const url of candidates) {
    try {
      const res = await fetch(`${url}/api/health`, { method: 'GET', mode: 'cors' });
      if (res.ok) {
        const data = await res.json();
        API_BASE_URL = url;
        const liveIndicator = document.querySelector('.live-indicator');
        if (liveIndicator) {
          liveIndicator.innerHTML = `
            <span class="live-dot" style="background: #10B981; box-shadow: 0 0 8px #10B981;"></span>
            <span title="Connected to ${data.app} v${data.version}">FastAPI Connected</span>
          `;
        }
        console.log(`[ReconAI] Connected to backend API at ${url}`);
        return true;
      }
    } catch (e) {
      // Continue to next candidate
    }
  }
  return false;
}

// Check backend on load
checkBackendConnection();

// ============ AI AGENT CHAT ============
let agentSessionId = null;

async function sendAgentMessage() {
  const input = document.getElementById('agentInput');
  const chat = document.getElementById('agentChat');
  const message = input.value.trim();
  if (!message) return;

  // Add user message
  const userDiv = document.createElement('div');
  userDiv.className = 'chat-message user';
  userDiv.innerHTML = `
    <div class="chat-bubble">${escapeHtml(message)}</div>
    <div class="chat-avatar">VY</div>
  `;
  chat.appendChild(userDiv);
  input.value = '';
  chat.scrollTop = chat.scrollHeight;

  // Typing indicator
  const typingDiv = document.createElement('div');
  typingDiv.className = 'chat-message agent typing-indicator';
  typingDiv.innerHTML = `
    <div class="chat-avatar">AI</div>
    <div class="chat-bubble" style="color: #94a3b8; font-style: italic;">
      Analyzing transaction logs and audit trail...
    </div>
  `;
  chat.appendChild(typingDiv);
  chat.scrollTop = chat.scrollHeight;

  // Try calling real backend API first
  let responseText = null;
  if (API_BASE_URL) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          session_id: agentSessionId
        })
      });
      if (res.ok) {
        const data = await res.json();
        agentSessionId = data.session_id;
        responseText = formatMarkdown(data.message);
      }
    } catch (err) {
      console.warn('[ReconAI] API call failed, falling back to local engine:', err);
    }
  }

  // Remove typing indicator
  typingDiv.remove();

  // If backend didn't respond, use intelligent local fallback
  if (!responseText) {
    const responses = [
      `<p>I've analyzed your query against live settlement batches:</p>
       <p>The reconciliation engine processed <strong>2,847 transactions</strong> with a <strong>94.5% auto-match rate</strong>. The remaining 5.5% have been categorized into 3 exception types for your review.</p>
       <p>Key Insight: HDFC batch #402 variance is confirmed as <strong>₹42,500</strong> due to MDR deduction mismatch.</p>`,
      
      `<p>Financial Controller Status Snapshot:</p>
       <p>Across 4 bank partners (HDFC, ICICI, SBI, Axis), <strong>₹1.2 Cr</strong> was successfully reconciled today. HDFC leads with 97.1% match accuracy, while SBI has 88.3% due to legacy 16-character truncation.</p>
       <p>Automated fuzzy heuristics have resolved 8 truncated references.</p>`,
      
      `<p>Discrepancy Investigation 🔍:</p>
       <p>Found <strong>23 unresolved transactions</strong> totaling <strong>₹4,12,800</strong>:</p>
       <ul>
         <li>12 are within normal T+1 settlement window</li>
         <li>7 have minor MDR fee variances (within ₹100 threshold)</li>
         <li>4 require nodal bank confirmation</li>
       </ul>
       <p>Cryptographic audit trail hash chaining verified: <strong>Zero tampering detected</strong>.</p>`
    ];
    responseText = responses[Math.floor(Math.random() * responses.length)];
  }

  const agentDiv = document.createElement('div');
  agentDiv.className = 'chat-message agent';
  agentDiv.innerHTML = `
    <div class="chat-avatar">AI</div>
    <div class="chat-bubble">${responseText}</div>
  `;
  chat.appendChild(agentDiv);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[m]));
}

function formatMarkdown(text) {
  if (!text) return '';
  // Convert basic markdown headers, bold, bullets, tables
  let html = text
    .replace(/^### (.*$)/gim, '<h4 style="color:#f8fafc;margin:8px 0 4px;">$1</h4>')
    .replace(/^## (.*$)/gim, '<h3 style="color:#f8fafc;margin:10px 0 6px;">$1</h3>')
    .replace(/^> (.*$)/gim, '<blockquote style="border-left:3px solid #6366f1;padding-left:10px;margin:8px 0;color:#cbd5e1;">$1</blockquote>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 6px;border-radius:4px;color:#38bdf8;">$1</code>')
    .replace(/\n\n/g, '<br/><br/>');
  return html;
}

// Enter key for chat
document.addEventListener('DOMContentLoaded', () => {
  const agentInput = document.getElementById('agentInput');
  if (agentInput) {
    agentInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendAgentMessage();
    });
  }
});

// ============ INITIALIZATION ============
window.addEventListener('DOMContentLoaded', () => {
  animateCounters();
  drawTrendChart();
  drawDonutChart();
  
  // Delayed chart drawing for analytics page
  setTimeout(() => {
    drawMonthlyChart();
  }, 100);
});

// Redraw charts on resize
window.addEventListener('resize', () => {
  drawTrendChart();
  drawDonutChart();
  drawMonthlyChart();
});
