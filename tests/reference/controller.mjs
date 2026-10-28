// Control determinista: cuatro accesos virtuales, sin cámara ni puerto serial.
export const APPROACHES = ['N', 'E', 'S', 'W'];
export const GROUPS = {NS: ['N', 'S'], EW: ['E', 'W']};
export class TrafficController {
  constructor(mode = 'fti') {
    this.mode = mode; this.runningMode = mode;
    this.stage = 'ALL_RED'; this.active = []; this.elapsed = 0;
    this.counts = [0, 0, 0, 0]; this.queues = [0, 0, 0, 0];
    this.sensorAge = 0; this.cursor = 3; this.lastAxis = 'EW';
    this.wait = [0, 0, 0, 0]; this.priority = null;
    this.clearance = 1; this.fallback = false; this.reason = 'Esperando demanda';
  }
  sense(counts, queues = counts) {
    this.counts = counts.map(x => Math.max(0, Number(x) || 0));
    this.queues = queues.map(x => Math.max(0, Number(x) || 0));
    this.sensorAge = 0;
  }
  light(approach) { return this.active.includes(approach) ? this.stage : 'RED'; }
  get yellowDuration() { return this.runningMode === 'fti' ? 2 : 2.5; }
  get greenDuration() { return this.runningMode === 'fti' ? 5 : this.runningMode === 'fixed' ? 11 : 16; }
  step(dt, occupied = false) {
    this.sensorAge += dt; this.elapsed += dt;
    this.fallback = this.sensorAge >= 5;
    const requested = this.fallback ? 'fixed' : this.mode;
    for (let i = 0; i < 4; i++) {
      this.wait[i] = this.counts[i] > 0 && this.light(APPROACHES[i]) !== 'GREEN' ? this.wait[i] + dt : 0;
    }
    // Cambios de algoritmo y fallos siempre pasan por amarillo y despeje.
    if (requested !== this.runningMode && this.stage === 'GREEN') {
      this.stage = 'YELLOW'; this.elapsed = 0; this.reason = 'Transición de modo';
    }
    if (this.stage === 'YELLOW') {
      if (this.elapsed >= this.yellowDuration) { this.stage = 'ALL_RED'; this.elapsed = 0; this.active = []; }
      return;
    }
    if (this.stage === 'ALL_RED') {
      if (this.elapsed < this.clearance || occupied) {
        this.reason = occupied ? 'Despejando vehículos dentro del cruce' : 'Intervalo de despeje';
        return;
      }
      this.runningMode = requested;
      if (requested === 'fti') {
        for (let offset = 1; offset <= 4; offset++) {
          const idx = (this.cursor + offset) % 4;
          if (this.counts[idx] > 0) {
            this.cursor = idx; this.active = [APPROACHES[idx]];
            this.stage = 'GREEN'; this.elapsed = 0;
            this.reason = `Demanda C${idx + 1}: turno de 5 s`; return;
          }
        }
        this.reason = 'Sin demanda: los cuatro accesos en rojo'; return;
      }
      let axis = this.lastAxis === 'NS' ? 'EW' : 'NS';
      if (requested === 'adaptive') {
        const ns = this.queues[0] + this.queues[2];
        const ew = this.queues[1] + this.queues[3];
        // Alternar si ambas colas esperan evita que una avenida monopolice el verde.
        if (this.priority && GROUPS[this.priority].some(a => this.counts[APPROACHES.indexOf(a)] > 0)) axis = this.priority;
        else if (ns === 0 && ew > 0) axis = 'EW';
        else if (ew === 0 && ns > 0) axis = 'NS';
        else if (!this.active.length && Math.max(...this.wait) > 25) axis = this.wait[0] + this.wait[2] >= this.wait[1] + this.wait[3] ? 'NS' : 'EW';
      }
      this.active = GROUPS[axis].slice(); this.lastAxis = axis;
      this.stage = 'GREEN'; this.elapsed = 0;
      this.reason = this.fallback ? 'Respaldo fijo por pérdida de sensores' : requested === 'fixed' ? 'Alternancia fija de 11 s' : this.priority === axis ? 'Prioridad V2I con transición' : 'Balance de colas y espera';
      return;
    }
    if (this.stage === 'GREEN') {
      let end = this.elapsed >= this.greenDuration;
      if (this.runningMode === 'adaptive') {
        const current = this.active.reduce((s, a) => s + this.queues[APPROACHES.indexOf(a)], 0);
        const other = this.queues.reduce((s, n) => s + n, 0) - current;
        end ||= this.elapsed >= 6.5 && other > current + 1;
        end ||= this.elapsed >= 4 && current === 0 && other > 0;
        end ||= this.elapsed >= 6.5 && this.priority && this.priority !== this.lastAxis;
      }
      if (end) { this.stage = 'YELLOW'; this.elapsed = 0; this.reason = 'Fin de turno: amarillo'; }
    }
  }
}

// heading: 0=sur, 1=este, 2=norte, 3=oeste (convención del HTML original).
export function detectApproach(x, z, heading, interX, interZ, depth = 55) {
  const dx = x - interX, dz = z - interZ;
  const stop = 15.4, far = stop + depth;
  if (heading === 0 && dx <= 0 && dx >= -12 && -dz >= stop && -dz <= far) return 0;
  if (heading === 3 && dz <= 0 && dz >= -12 && dx >= stop && dx <= far) return 1;
  if (heading === 2 && dx >= 0 && dx <= 12 && dz >= stop && dz <= far) return 2;
  if (heading === 1 && dz >= 0 && dz <= 12 && -dx >= stop && -dx <= far) return 3;
  return -1;
}
