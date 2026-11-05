const BASE = process.env.BILLING_API || 'https://billing.example';

async function request(path, method = 'GET') {
  const res = await fetch(BASE + path, { method });
  if (res.status === 204) return { status: 204 };
  return { status: res.status, body: await res.json() };
}

const getInvoice = (id) => request(`/invoices/${id}`);
const archiveInvoice = (id) => request(`/invoices/${id}/archive`, 'POST');
const deleteDraft = (id) => request(`/drafts/${id}`, 'DELETE');

module.exports = { request, getInvoice, archiveInvoice, deleteDraft };
