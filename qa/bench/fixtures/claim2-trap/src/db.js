const rows = new Map();
let next = 1;
async function insert(table, row) { const id = next++; rows.set(`${table}:${id}`, row); return { id, ...row }; }
async function update(table, id, fields) { const key = `${table}:${id}`; rows.set(key, { ...rows.get(key), ...fields }); }
module.exports = { insert, update };
