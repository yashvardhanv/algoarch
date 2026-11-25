'use strict';

// Pure curriculum rules: no database, no file reads.

function parseMinutes(duration) {
  if (typeof duration !== 'string') return 0;
  const m = duration.match(/(\d+)\s*min/);
  return m ? parseInt(m[1], 10) : 0;
}

function rotateToSmallest(cycle) {
  let min = 0;
  for (let i = 1; i < cycle.length; i++) {
    if (cycle[i] < cycle[min]) min = i;
  }
  return cycle.slice(min).concat(cycle.slice(0, min));
}

function findPrereqProblems(lessons) {
  const ids = new Set(lessons.map((l) => l.id));
  const unknown = [];
  const selfLoops = [];
  const edges = new Map();

  for (const l of lessons) {
    const out = [];
    for (const p of l.prereqs || []) {
      if (p === l.id) {
        if (!selfLoops.includes(l.id)) selfLoops.push(l.id);
      } else if (!ids.has(p)) {
        unknown.push({ lesson: l.id, prereq: p });
      } else {
        out.push(p);
      }
    }
    edges.set(l.id, out);
  }

  const cycles = [];
  const seen = new Set();
  const visiting = new Set();
  const done = new Set();
  const stack = [];

  function visit(id) {
    visiting.add(id);
    stack.push(id);
    for (const next of edges.get(id)) {
      if (visiting.has(next)) {
        const cycle = rotateToSmallest(stack.slice(stack.indexOf(next)));
        const key = cycle.join('\u0000');
        if (!seen.has(key)) {
          seen.add(key);
          cycles.push(cycle);
        }
      } else if (!done.has(next)) {
        visit(next);
      }
    }
    stack.pop();
    visiting.delete(id);
    done.add(id);
  }

  for (const l of lessons) {
    if (!done.has(l.id)) visit(l.id);
  }

  return { unknown, selfLoops, cycles };
}

function checkPathways(pathways, lessons) {
  const byId = new Map(lessons.map((l) => [l.id, l]));
  const errors = [];
  const warnings = [];
  const minutes = {};

  for (const p of pathways) {
    if (p.lessons.length === 0) errors.push(`empty pathway ${p.id}`);

    const position = new Map();
    let total = 0;
    p.lessons.forEach((ref, i) => {
      const lesson = byId.get(ref.id);
      if (!lesson) {
        errors.push(`unknown lesson ${ref.id} in ${p.id}`);
        return;
      }
      if (position.has(ref.id)) {
        errors.push(`duplicate lesson ${ref.id} in ${p.id}`);
        return;
      }
      position.set(ref.id, i);
      total += parseMinutes(lesson.duration);
    });
    minutes[p.id] = total;

    for (const [id, i] of position) {
      for (const prereq of byId.get(id).prereqs || []) {
        if (!position.has(prereq)) {
          warnings.push(`${p.id}: ${id} needs ${prereq}, which the pathway does not include`);
        } else if (position.get(prereq) > i) {
          errors.push(`${p.id}: ${id} comes before its prerequisite ${prereq}`);
        }
      }
    }
  }

  return { errors, warnings, minutes };
}

function unreachableLessons(pathways, lessons) {
  const used = new Set();
  for (const p of pathways) {
    for (const ref of p.lessons) used.add(ref.id);
  }
  return lessons.filter((l) => !used.has(l.id)).map((l) => l.id);
}

function checkMigrationMap(baselineIds, currentIds) {
  const base = new Set(baselineIds);
  const cur = new Set(currentIds);
  return {
    missing: baselineIds.filter((id) => !cur.has(id)).sort(),
    added: currentIds.filter((id) => !base.has(id)).sort(),
  };
}

function mergeBaseline(existingIds, currentIds) {
  const cur = new Set(currentIds);
  const missing = [...new Set(existingIds.filter((id) => !cur.has(id)))].sort();
  const ids = [...new Set([...existingIds, ...currentIds])].sort();
  return { ids, missing };
}

function validatePathwaysFile(pathwaysJson, lessons) {
  const known = new Set(lessons.map((l) => l.id));
  const pathways = (pathwaysJson && pathwaysJson.pathways) || [];
  const errors = [];
  for (const p of pathways) {
    if (typeof p.title !== 'string' || !p.title.trim()) errors.push(`pathway ${p.id} has no title`);
    if (!['horizon', 'goal', 'level'].includes(p.kind)) errors.push(`pathway ${p.id} has invalid kind ${p.kind}`);
    for (const l of p.lessons || []) {
      if (!known.has(l.id)) errors.push(`pathway ${p.id} references unknown lesson ${l.id}`);
    }
  }
  const shaped = pathways.map((p) => ({ ...p, lessons: (p.lessons || []).filter((l) => known.has(l.id)) }));
  // an all-unknown pathway is reported as unknown ids, not also as empty
  const nonEmpty = shaped.filter((p, i) => p.lessons.length > 0 || (pathways[i].lessons || []).length === 0);
  errors.push(...checkPathways(nonEmpty, lessons).errors);
  return errors;
}

module.exports = {
  mergeBaseline,
  validatePathwaysFile,
  parseMinutes,
  findPrereqProblems,
  checkPathways,
  unreachableLessons,
  checkMigrationMap,
};
