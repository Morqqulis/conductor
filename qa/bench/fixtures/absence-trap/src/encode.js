function toBase64(text) {
  return new Buffer(text).toString('base64');
}

function slug(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

module.exports = { toBase64, slug };
