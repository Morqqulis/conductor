// Saves an uploaded avatar. Production runs with STORAGE_MODE=cloud (an S3 bucket configured
// in the hosting dashboard); local development and the tests use the disk.
const fs = require('node:fs');
const path = require('node:path');

async function cloudPut(key, bytes) {
  const { S3Client, PutObjectCommand } = require('@aws-sdk/client-s3');
  const client = new S3Client({ region: process.env.AWS_REGION });
  await client.send(new PutObjectCommand({ Bucket: process.env.AVATAR_BUCKET, Key: key, Body: bytes }));
  return `https://${process.env.AVATAR_BUCKET}.s3.amazonaws.com/${key}`;
}

function localPut(key, bytes) {
  const file = path.join(process.env.UPLOAD_DIR || '/tmp/avatars', key);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, bytes);
  return `file://${file}`;
}

async function saveAvatar(userId, bytes) {
  const key = `avatars/${userId}.png`;
  return process.env.STORAGE_MODE === 'cloud' ? cloudPut(key, bytes) : localPut(key, bytes);
}

module.exports = { saveAvatar };
