#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { minify } = require('terser');
const uglifycss = require('uglifycss');
const { minify: minifyHtml } = require('html-minifier-terser');

// Create optimized static directory
const optimizedDir = path.join(__dirname, 'static', 'optimized');
if (!fs.existsSync(optimizedDir)) {
    fs.mkdirSync(optimizedDir, { recursive: true });
    fs.mkdirSync(path.join(optimizedDir, 'js'), { recursive: true });
    fs.mkdirSync(path.join(optimizedDir, 'css'), { recursive: true });
}

// Minify JavaScript files
async function minifyJavaScript() {
    const jsDir = path.join(__dirname, 'static', 'js');
    const jsFiles = fs.readdirSync(jsDir).filter(file => file.endsWith('.js'));
    
    console.log('Minifying JavaScript files...');
    
    for (const file of jsFiles) {
        const filePath = path.join(jsDir, file);
        const code = fs.readFileSync(filePath, 'utf8');
        
        try {
            const result = await minify(code, {
                compress: {
                    drop_console: true,
                    drop_debugger: true,
                    pure_funcs: ['console.log', 'console.info', 'console.debug'],
                    passes: 2
                },
                mangle: {
                    toplevel: true,
                    reserved: ['$', 'jQuery', 'bootstrap']
                },
                format: {
                    comments: false
                }
            });
            
            const minFilePath = path.join(optimizedDir, 'js', file.replace('.js', '.min.js'));
            fs.writeFileSync(minFilePath, result.code);
            
            const originalSize = fs.statSync(filePath).size;
            const minifiedSize = fs.statSync(minFilePath).size;
            const savings = ((originalSize - minifiedSize) / originalSize * 100).toFixed(1);
            
            console.log(`  ${file}: ${originalSize} → ${minifiedSize} bytes (${savings}% reduction)`);
            
        } catch (error) {
            console.error(`Error minifying ${file}:`, error);
        }
    }
}

// Minify CSS files
function minifyCSS() {
    const cssDir = path.join(__dirname, 'static', 'css');
    const cssFiles = fs.readdirSync(cssDir).filter(file => file.endsWith('.css'));
    
    console.log('Minifying CSS files...');
    
    for (const file of cssFiles) {
        const filePath = path.join(cssDir, file);
        const css = fs.readFileSync(filePath, 'utf8');
        
        try {
            const minified = uglifycss.processString(css, {
                maxLineLen: 0,
                expandVars: true,
                uglyComments: true,
                cuteComments: false
            });
            
            const minFilePath = path.join(optimizedDir, 'css', file.replace('.css', '.min.css'));
            fs.writeFileSync(minFilePath, minified);
            
            const originalSize = fs.statSync(filePath).size;
            const minifiedSize = fs.statSync(minFilePath).size;
            const savings = ((originalSize - minifiedSize) / originalSize * 100).toFixed(1);
            
            console.log(`  ${file}: ${originalSize} → ${minifiedSize} bytes (${savings}% reduction)`);
            
        } catch (error) {
            console.error(`Error minifying ${file}:`, error);
        }
    }
}

// Create combined and minified bundle
async function createBundle() {
    console.log('Creating optimized bundle...');
    
    // Combine all JS files in order
    const jsFiles = ['main.js', 'app.js', 'dashboard.js', 'results.js'];
    const jsDir = path.join(__dirname, 'static', 'js');
    
    let combinedJs = '';
    for (const file of jsFiles) {
        const filePath = path.join(jsDir, file);
        if (fs.existsSync(filePath)) {
            combinedJs += fs.readFileSync(filePath, 'utf8') + '\n';
        }
    }
    
    // Minify combined JS
    try {
        const result = await minify(combinedJs, {
            compress: {
                drop_console: true,
                drop_debugger: true,
                pure_funcs: ['console.log', 'console.info', 'console.debug'],
                passes: 2
            },
            mangle: {
                toplevel: true,
                reserved: ['$', 'jQuery', 'bootstrap']
            },
            format: {
                comments: false
            }
        });
        
        const bundlePath = path.join(optimizedDir, 'js', 'bundle.min.js');
        fs.writeFileSync(bundlePath, result.code);
        
        const originalSize = Buffer.byteLength(combinedJs);
        const minifiedSize = Buffer.byteLength(result.code);
        const savings = ((originalSize - minifiedSize) / originalSize * 100).toFixed(1);
        
        console.log(`  bundle.min.js: ${originalSize} → ${minifiedSize} bytes (${savings}% reduction)`);
        
    } catch (error) {
        console.error('Error creating bundle:', error);
    }
}

// Generate manifest with file hashes for cache busting
function generateManifest() {
    console.log('Generating asset manifest...');
    
    const manifest = {};
    const crypto = require('crypto');
    
    // Process JS files
    const jsDir = path.join(optimizedDir, 'js');
    if (fs.existsSync(jsDir)) {
        const jsFiles = fs.readdirSync(jsDir);
        for (const file of jsFiles) {
            const filePath = path.join(jsDir, file);
            const content = fs.readFileSync(filePath);
            const hash = crypto.createHash('md5').update(content).digest('hex').substring(0, 8);
            const hashedName = file.replace('.min.js', `.${hash}.min.js`);
            
            // Rename file with hash
            const hashedPath = path.join(jsDir, hashedName);
            fs.renameSync(filePath, hashedPath);
            
            manifest[`js/${file}`] = `js/${hashedName}`;
        }
    }
    
    // Process CSS files
    const cssDir = path.join(optimizedDir, 'css');
    if (fs.existsSync(cssDir)) {
        const cssFiles = fs.readdirSync(cssDir);
        for (const file of cssFiles) {
            const filePath = path.join(cssDir, file);
            const content = fs.readFileSync(filePath);
            const hash = crypto.createHash('md5').update(content).digest('hex').substring(0, 8);
            const hashedName = file.replace('.min.css', `.${hash}.min.css`);
            
            // Rename file with hash
            const hashedPath = path.join(cssDir, hashedName);
            fs.renameSync(filePath, hashedPath);
            
            manifest[`css/${file}`] = `css/${hashedName}`;
        }
    }
    
    // Save manifest
    const manifestPath = path.join(optimizedDir, 'manifest.json');
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
    
    console.log('Asset manifest generated with cache-busting hashes');
}

// Main execution
async function main() {
    console.log('Starting asset optimization...\n');
    
    await minifyJavaScript();
    minifyCSS();
    await createBundle();
    generateManifest();
    
    console.log('\nAsset optimization complete! 🚀');
    console.log('Optimized assets are in: static/optimized/');
}

main().catch(console.error);