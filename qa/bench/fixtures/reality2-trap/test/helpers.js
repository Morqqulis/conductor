const calls = [];
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  return { ok: true, status: 200, json: async () => ({ id: 're_1', status: 'succeeded' }) };
};
module.exports = { calls };
