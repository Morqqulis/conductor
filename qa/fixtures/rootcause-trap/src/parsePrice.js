function parsePrice(raw) {
  return raw.replace('$', '');
}
module.exports = { parsePrice };
