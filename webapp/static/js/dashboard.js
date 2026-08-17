const token = localStorage.getItem('token');
if (!token) {
  window.location.href = '/';
}

function authHeaders() {
  return { 'Authorization': `Bearer ${token}` };
}

async function authFetch(url) {
  const res = await fetch(url, { headers: authHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = '/';
    return null;
  }
  if (!res.ok) {
    console.error('Request failed:', url, res.status);
    return null;
  }
  return res.json();
}

function formatCurrency(n) {
  return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function dateRangeParams(rangeValue) {
  if (rangeValue === 'all') return '';
  if (rangeValue === 'custom') {
    const start = document.getElementById('range-start').value;
    const end = document.getElementById('range-end').value;
    if (!start || !end) return '';
    return `?start=${start}&end=${end}`;
  }
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - Number(rangeValue));
  return `?start=${start.toISOString().slice(0, 10)}&end=${end.toISOString().slice(0, 10)}`;
}

let trendChart, categoryChart;

async function loadDashboard() {
  const rangeValue = document.getElementById('range-select').value;
  const params = dateRangeParams(rangeValue);

  const summary = await authFetch(`/api/summary${params}`);
  if (summary) {
    document.getElementById('total-income').textContent = formatCurrency(summary.total_income);
    document.getElementById('total-expense').textContent = formatCurrency(summary.total_expense);
    document.getElementById('total-balance').textContent = formatCurrency(summary.balance);
  }

  // Custom range -> daily breakdown (a monthly bucket doesn't mean much
  // for e.g. a 10-day window). Presets -> the usual 6-month monthly view.
  if (rangeValue === 'custom' && params) {
    const trend = await authFetch(`/api/trend/daily${params}`);
    document.getElementById('trend-title').textContent = 'Income vs Expense — daily';
    if (trend) renderTrendChart(trend, 'day');
  } else {
    const trend = await authFetch('/api/trend?months=6');
    document.getElementById('trend-title').textContent = 'Income vs Expense — monthly';
    if (trend) renderTrendChart(trend, 'month');
  }

  const categories = await authFetch(`/api/expenses/by-category${params}`);
  if (categories) renderCategoryChart(categories);

  const txnParams = params ? `${params}&limit=20` : '?limit=20';
  const txns = await authFetch(`/api/transactions${txnParams}`);
  if (txns) renderTransactions(txns);
}

function renderTrendChart(data, unitKey) {
  const ctx = document.getElementById('trend-chart');
  const labels = data.map(d => d[unitKey]);
  const income = data.map(d => d.income);
  const expense = data.map(d => d.expense);

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Income', data: income, backgroundColor: '#1FA97D' },
        { label: 'Expense', data: expense, backgroundColor: '#E05A3E' },
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#6B7C73' } } },
      scales: {
        x: { ticks: { color: '#6B7C73' }, grid: { color: '#DFE7E2' } },
        y: { ticks: { color: '#6B7C73' }, grid: { color: '#DFE7E2' } }
      }
    }
  });
}

function renderCategoryChart(data) {
  const ctx = document.getElementById('category-chart');
  const labels = data.map(d => d.category);
  const totals = data.map(d => d.total);
  // Deliberately avoids green/coral - those are reserved for Income/Expense
  // elsewhere on the dashboard, so reusing them here misleadingly implies
  // "green slice = income" in a chart that's actually 100% expenses.
  const palette = ['#4A7FC4', '#C08A2E', '#9A5FC4', '#C45F8A', '#4AA8B8', '#8A8F5F', '#B8734A'];

  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: totals, backgroundColor: palette }]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'bottom', labels: { color: '#6B7C73', boxWidth: 12, font: { size: 11 } } } }
    }
  });
}

function renderTransactions(txns) {
  const tbody = document.querySelector('#txn-table tbody');
  const emptyState = document.getElementById('txn-empty');
  tbody.innerHTML = '';

  if (txns.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }
  emptyState.classList.add('hidden');

  for (const t of txns) {
    const tr = document.createElement('tr');
    const amountClass = t.type === 'Income' ? 'amount-income' : 'amount-expense';
    const sign = t.type === 'Income' ? '+' : '−';
    tr.innerHTML = `
      <td>${t.date}</td>
      <td>${t.type}</td>
      <td>${t.label}</td>
      <td class="${amountClass}">${sign}${formatCurrency(t.amount)}</td>
    `;
    tbody.appendChild(tr);
  }
}

document.getElementById('range-select').addEventListener('change', (e) => {
  const customRangeEl = document.getElementById('custom-range');
  if (e.target.value === 'custom') {
    customRangeEl.classList.remove('hidden');
    // Don't reload yet - wait for the user to pick dates and click Apply.
  } else {
    customRangeEl.classList.add('hidden');
    loadDashboard();
  }
});

document.getElementById('apply-range-btn').addEventListener('click', () => {
  const start = document.getElementById('range-start').value;
  const end = document.getElementById('range-end').value;
  if (!start || !end) {
    alert('Please pick both a start and end date.');
    return;
  }
  if (start > end) {
    alert('Start date must be before end date.');
    return;
  }
  loadDashboard();
});

document.getElementById('logout-btn').addEventListener('click', () => {
  localStorage.removeItem('token');
  window.location.href = '/';
});

// ---------- Reports dropdown ----------

const reportsBtn = document.getElementById('reports-btn');
const reportsDropdown = document.getElementById('reports-dropdown');

reportsBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  reportsDropdown.classList.toggle('hidden');
});

document.addEventListener('click', () => {
  reportsDropdown.classList.add('hidden');
});

async function downloadCsv(endpoint) {
  const rangeValue = document.getElementById('range-select').value;
  const params = dateRangeParams(rangeValue);
  const res = await fetch(`${endpoint}${params}`, { headers: authHeaders() });
  if (!res.ok) {
    alert('Could not generate the report. Please try again.');
    return;
  }
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="(.+)"/);
  const filename = match ? match[1] : 'report.csv';

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

document.getElementById('export-transactions-btn').addEventListener('click', () => {
  downloadCsv('/api/export/transactions.csv');
});

document.getElementById('export-summary-btn').addEventListener('click', () => {
  downloadCsv('/api/export/summary.csv');
});

loadDashboard();
