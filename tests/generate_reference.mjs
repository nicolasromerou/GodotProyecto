// Deterministic golden trace from the simulator's real, unmodified JS controller.
// Run with Node.js: node tests/generate_reference.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { TrafficController } from './reference/controller.mjs';

let seed = 0x465449;
function random() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}
function snapshot(c) {
  return {
    mode: c.mode, running_mode: c.runningMode, stage: c.stage,
    active: c.active.slice(), elapsed: c.elapsed,
    counts: c.counts.slice(), queues: c.queues.slice(),
    sensor_age: c.sensorAge, cursor: c.cursor, last_axis: c.lastAxis,
    wait: c.wait.slice(), priority: c.priority ?? '', clearance: c.clearance,
    fallback: c.fallback, reason: c.reason,
  };
}

const scenarios = [];
for (const initial_mode of ['fti', 'adaptive', 'fixed', 'fti']) {
  const changesMode = scenarios.length === 3;
  const c = new TrafficController(initial_mode);
  const steps = [];
  let readings = [0, 0, 0, 0];
  let queues = [0, 0, 0, 0];
  for (let i = 0; i < 3600; i++) {
    // Each trace includes four 10 s sensor outages, restoration, junction
    // occupancy, no demand, asymmetric demand and requests for both axes.
    const sensorsAvailable = i % 900 < 600;
    const entry = {dt: 1 / 30, occupied: i % 450 < 15};
    if (changesMode && i % 900 === 0) {
      entry.mode = ['fti', 'adaptive', 'fixed', 'fti'][Math.floor(i / 900)];
      c.mode = entry.mode;
    }
    entry.priority = i % 700 < 140 ? (i % 1400 < 700 ? 'EW' : 'NS') : null;
    c.priority = entry.priority;
    if (sensorsAvailable && i % 3 === 0) {
      if (i % 90 === 0) {
        readings = Array.from({length: 4}, () => Math.floor(random() * 5));
        queues = readings.map(n => Math.floor(random() * (n + 1)));
        if (i % 900 < 90) readings = queues = [0, 0, 0, 0];
      }
      entry.counts = readings.slice();
      entry.queues = queues.slice();
      c.sense(entry.counts, entry.queues);
    }
    c.step(entry.dt, entry.occupied);
    entry.expected = snapshot(c);
    steps.push(entry);
  }
  scenarios.push({initial_mode, name: changesMode ? 'mode-switches' : initial_mode, steps});
}
const destination = fileURLToPath(new URL('./reference_controller.json', import.meta.url));
mkdirSync(fileURLToPath(new URL('./reference/', import.meta.url)), {recursive: true});
const json = JSON.stringify(scenarios);
writeFileSync(destination, json + '\n');
console.log(`Generated ${scenarios.length} scenarios, ${scenarios.reduce((n,s) => n+s.steps.length, 0)} snapshots, ${(Buffer.byteLength(json)/1024/1024).toFixed(2)} MiB.`);
