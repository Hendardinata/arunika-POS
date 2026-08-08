const fs = require('fs');
const path = require('path');

const targetIP = '100.77.229.76';
const searchPatterns = ['127.0.0.1:3001', 'localhost:3001'];
const replaceString = `${targetIP}:3001`;

function walkDir(dir, callback) {
  fs.readdirSync(dir).forEach(f => {
    let dirPath = path.join(dir, f);
    let isDirectory = fs.statSync(dirPath).isDirectory();
    isDirectory ? walkDir(dirPath, callback) : callback(path.join(dir, f));
  });
}

function replaceInFile(filePath) {
  const ext = path.extname(filePath);
  if (['.dart', '.tsx', '.ts'].includes(ext)) {
    let content = fs.readFileSync(filePath, 'utf8');
    let original = content;
    
    searchPatterns.forEach(pattern => {
      // Create a global regex
      const regex = new RegExp(pattern, 'g');
      content = content.replace(regex, replaceString);
    });

    if (content !== original) {
      fs.writeFileSync(filePath, content, 'utf8');
      console.log(`Updated: ${filePath}`);
    }
  }
}

// Update Mobile App (Flutter)
const mobileDir = path.join(__dirname, 'brewpos_mobile', 'lib');
if (fs.existsSync(mobileDir)) {
  console.log('--- Updating Flutter App ---');
  walkDir(mobileDir, replaceInFile);
}

// Update Web App (Next.js)
const webDir = path.join(__dirname, 'brewpos-web', 'src');
if (fs.existsSync(webDir)) {
  console.log('\n--- Updating Next.js Web App ---');
  walkDir(webDir, replaceInFile);
}

console.log('\nAll done! The IP has been updated to ' + targetIP);
