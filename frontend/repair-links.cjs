// Repair broken pnpm node_modules: pnpm created empty dirs instead of junctions
// because fs.symlink(type='dir'/'file') fails without privilege. Junctions work.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, 'node_modules');
const PNPM = path.join(ROOT, '.pnpm');

function parseNameVersion(dirName) {
  let name, rest;
  if (dirName.startsWith('@')) {
    // @scope+name@ver_peer@pv_...  (pnpm encodes @scope/name as @scope+name)
    const m = dirName.match(/^(@[^+]+)\+([^@]+)@(.+)$/);
    if (!m) return null;
    name = m[1] + '/' + m[2];
    rest = m[3];
  } else {
    const i = dirName.indexOf('@');
    if (i <= 0) return null;
    name = dirName.slice(0, i);
    rest = dirName.slice(i + 1);
  }
  const version = rest.split('_')[0];
  return { name, version };
}

// Build registry: packageName -> [{version, realPath(abs)}]
const registry = new Map();
for (const d of fs.readdirSync(PNPM)) {
  if (d === 'node_modules' || d === 'lock.yaml') continue;
  const p = parseNameVersion(d);
  if (!p) continue;
  const realPath = path.join(PNPM, d, 'node_modules', ...p.name.split('/'));
  try {
    if (fs.statSync(path.join(realPath, 'package.json')).isFile()) {
      if (!registry.has(p.name)) registry.set(p.name, []);
      registry.get(p.name).push({ version: p.version, realPath: path.resolve(realPath) });
    }
  } catch (_) {}
}

// npm alias shells: alias name -> real package name (declared as "npm:<real>@ver")
const ALIASES = {
  '@popperjs/core': '@sxzz/popperjs-es',
};
for (const [alias, real] of Object.entries(ALIASES)) {
  if (registry.has(real) && !registry.has(alias)) registry.set(alias, registry.get(real));
}

// A "broken shell" = a directory that is not a real package (no package.json)
// AND is not a scope container (@scope). pnpm leaves these when linking fails.
function isBrokenShell(p) {
  try {
    const st = fs.statSync(p);
    if (!st.isDirectory()) return false;
    // real package has package.json
    if (fs.existsSync(path.join(p, 'package.json'))) return false;
    // scope container like @vitejs (its children are packages)
    if (path.basename(p).startsWith('@')) return false;
    return true;
  } catch { return false; }
}

let fixed = 0, skipped = 0, ambiguous = [];

function linkEmptyDir(full, name) {
  const cands = registry.get(name);
  if (!cands || !cands.length) { skipped++; return; }
  let target;
  if (cands.length === 1) target = cands[0].realPath;
  else {
    // prefer exact: pick highest version
    cands.sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));
    target = cands[cands.length - 1].realPath;
    ambiguous.push({ path: full, name, versions: cands.map(c => c.version) });
  }
  try {
    fs.rmSync(full, { recursive: true, force: true });
    fs.symlinkSync(target, full, 'junction');
    fixed++;
  } catch (e) {
    console.error('FIX FAIL', full, e.message);
  }
}

function fixNodeModulesDir(nmDir) {
  let entries;
  try { entries = fs.readdirSync(nmDir, { withFileTypes: true }); } catch { return; }
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const full = path.join(nmDir, e.name);
    if (e.name === '.pnpm' || e.name === '.bin') continue;
    if (e.name.startsWith('@')) {
      // scoped: @scope/<name>
      let subs;
      try { subs = fs.readdirSync(full, { withFileTypes: true }); } catch { continue; }
      for (const s of subs) {
        if (!s.isDirectory()) continue;
        const sfull = path.join(full, s.name);
        if (isBrokenShell(sfull)) linkEmptyDir(sfull, e.name + '/' + s.name);
      }
      continue;
    }
    if (isBrokenShell(full)) linkEmptyDir(full, e.name);
  }
}

// 1) each package's own node_modules (dependency shells)
for (const d of fs.readdirSync(PNPM)) {
  if (d === 'node_modules' || d === 'lock.yaml') continue;
  fixNodeModulesDir(path.join(PNPM, d, 'node_modules'));
}
// 2) hoisted hidden dir
fixNodeModulesDir(path.join(PNPM, 'node_modules'));
// 3) top-level
fixNodeModulesDir(ROOT);

console.log(JSON.stringify({ fixed, skipped, ambiguousCount: ambiguous.length }, null, 2));
if (ambiguous.length) console.log('AMBIGUOUS (picked highest):', JSON.stringify(ambiguous.slice(0, 20), null, 2));

// --- Ensure esbuild platform binary sits at bin/esbuild.exe ---
// In this environment the platform pkg's binary sometimes lands at the package
// root instead of bin/, which makes esbuild's require.resolve() fail.
let binFixed = 0;
for (const d of fs.readdirSync(PNPM)) {
  if (!/^@esbuild\+win32-x64@/.test(d)) continue;
  const pkg = path.join(PNPM, d, 'node_modules', '@esbuild', 'win32-x64');
  const rootExe = path.join(pkg, 'esbuild.exe');
  const binDir = path.join(pkg, 'bin');
  const binExe = path.join(binDir, 'esbuild.exe');
  try {
    if (fs.existsSync(rootExe) && !fs.existsSync(binExe)) {
      fs.mkdirSync(binDir, { recursive: true });
      fs.copyFileSync(rootExe, binExe);
      binFixed++;
    }
  } catch (e) {
    console.error('BIN FIX FAIL', pkg, e.message);
  }
}
console.log(JSON.stringify({ esbuildBinFixed: binFixed }));
