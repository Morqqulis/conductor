function slugify(s) {
  return s.toLowerCase().trim().replace(/\s+/g, '-');
}
module.exports = { slugify };
