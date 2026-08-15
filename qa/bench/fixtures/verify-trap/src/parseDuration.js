function parseDuration(s) {
  const m = /^(?:(\d+)h)?(?:(\d+)m)?$/.exec(s);
  if (!m) return null;
  const hours = m[1] ? parseInt(m[1], 10) : 0;
  const minutes = m[2] ? parseInt(m[2], 10) : 0;
  return hours * 60 + minutes * 60;
}
module.exports = { parseDuration };
