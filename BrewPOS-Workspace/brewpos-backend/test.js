const http = require('http');

const req = http.request({
  hostname: '127.0.0.1',
  port: 3001,
  path: '/api/inventory',
  method: 'GET'
}, (res) => {
  let data = '';
  res.on('data', chunk => data += chunk);
  res.on('end', () => console.log('Response:', res.statusCode, data));
});

req.on('error', e => console.error('Error:', e.message));
req.end();
