const BASE = process.env.PAY_API || 'https://api.paybridge.example';

async function refund(paymentId, amount) {
  const response = await fetch(`${BASE}/v1/refunds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.PAY_KEY}` },
    body: JSON.stringify({ payment: paymentId, amount }),
  });
  if (!response.ok) throw new Error(`refund failed: ${response.status}`);
  return response.json();
}

module.exports = { refund };
