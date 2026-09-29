// Build drift-demo.html: inline the engine into the template.
const fs = require("fs");
const path = require("path");
const dir = __dirname;
const engine = fs.readFileSync(path.join(dir, "drift_engine.js"), "utf8");
const template = fs.readFileSync(path.join(dir, "demo-template.html"), "utf8");
if (!template.includes("/*__ENGINE__*/")) throw new Error("placeholder missing");
const out = template.replace("/*__ENGINE__*/", engine);
fs.writeFileSync(path.join(dir, "drift-demo.html"), out);
console.log("wrote drift-demo.html (" + (out.length / 1024).toFixed(1) + " KB)");
