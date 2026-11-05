const https = require('node:https');

function report(payload) {
  const request = https.request({ host: 'ingest.bugtrail.io', path: '/v1/events', method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Project': process.env.BUGTRAIL_PROJECT } });
  request.end(JSON.stringify(payload));
}

function errorHandler(error, req, res, next) {
  report({ message: error.message, stack: error.stack, path: req.path, body: req.body, at: Date.now() });
  res.status(500).json({ error: 'internal error' });
}

module.exports = { errorHandler };
