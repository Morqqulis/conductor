const express = require('express');
const users = require('./users');
const newsletter = require('./newsletter');
const monitoring = require('./monitoring');

const app = express();
app.use(express.json());
app.post('/signup', users.signup);
app.post('/profile', users.updateProfile);
app.post('/newsletter', newsletter.subscribe);
app.use(monitoring.errorHandler);

module.exports = app;
