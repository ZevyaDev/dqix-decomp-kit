export const meta = {
  name: 'dqix-naming-round-4',
  description: 'Name DQIX functions and every identifier inside them from ROM evidence; agents write findings to their own file only',
  phases: [{ title: 'Name' }, { title: 'Audit' }],
}

const ENV = typeof process === 'undefined' ? {} : process.env ?? {}
const SP = args?.naming ?? ENV.DQIX_NAMING_DIR ?? 'naming'
const LABEL = args?.label ?? ENV.DQIX_LABEL_REPO ?? '../dqix-label'
const GAME = args?.repo ?? ENV.DQIX_REPO ?? '../dqix-decomp'
const PATHS = `In the brief, $DQIX_LABEL_REPO is ${LABEL} and $DQIX_REPO is ${GAME}.`
const DIR = args?.dir ?? 'chunks4'
const OUT = args?.out ?? 'final4'
const BATCHES = args?.batches ?? [0, 1, 2, 3]

const SUMMARY = {
  type: 'object',
  properties: {
    out_path: { type: 'string' },
    batch: { type: 'number' },
    named: { type: 'number' },
    insufficient: { type: 'number' },
    renames: { type: 'number' },
    hardest: { type: 'string' },
  },
  required: ['out_path', 'batch', 'named', 'insufficient', 'renames', 'hardest'],
}

const VERDICT_SUMMARY = {
  type: 'object',
  properties: {
    out_path: { type: 'string' },
    batch: { type: 'number' },
    kept: { type: 'number' },
    rejected: { type: 'number' },
    rejected_renames: { type: 'number' },
    worst: { type: 'string' },
  },
  required: ['out_path', 'batch', 'kept', 'rejected', 'rejected_renames', 'worst'],
}

const SHAPE =
  `[{"address": "0x…", "current_name": "func_…", "proposed_name": "PascalCase or null", ` +
  `"confidence": "certain|probable|insufficient", "evidence": "…", "comment": "// line\\n// line", ` +
  `"renames": [{"old": "obj", "new": "combatant", "kind": "param|local|struct|field|enum", ` +
  `"scope": "func | struct:Tag | line:unique substring — omit it only when the body spells "old" ` +
  `for one thing and one thing only", "evidence": "…"}], ` +
  `"edits": [{"old": "short slots[1];", "new": "short slots[10];", "evidence": "…"}]}]`

const results = await pipeline(
  BATCHES,
  (n) => {
    const nn = String(n).padStart(2, '0')
    return agent(
      `Read the brief at ${SP}/BRIEF.md in full, then name the functions in ` +
        `${SP}/${DIR}/batch${nn}.json.\n\n` +
        `Most of these have no asset string in the literal pool, so the evidence has to come from ` +
        `the decompiled body, from who calls it and what it calls, and from the game files. They ` +
        `are ranked by fan-in, so a caller sample across different overlays is usually what ` +
        `settles the subject: a function called from the title screen, the menus and battle alike ` +
        `is engine plumbing, not a battle routine. Naming one of these wrongly propagates the ` +
        `error across every call site, so hold the line on confidence "insufficient".\n\n` +
        `Follow the brief exactly: read each decompiled body off the labeling-pass branch first, ` +
        `cite evidence, and name the insides — parameters, locals, struct tags, fields, filler and ` +
        `array extents — as the brief's "Naming the insides" section requires. Quote every "old" ` +
        `spelling exactly as the labeling-pass body spells it. An insufficient function name does ` +
        `not excuse leaving the insides unnamed.\n\n` +
        `Write your findings as JSON to ${SP}/${OUT}/name${nn}.json, one entry per input ` +
        `function, shaped exactly:\n${SHAPE}\n\n` +
        `That output file is the only thing you may write. Never edit anything under ` +
        `${LABEL}. Then return the summary.\n\n${PATHS}`,
      { label: `name4:batch${n}`, phase: 'Name', schema: SUMMARY },
    )
  },
  (res) => {
    const nn = String(res.batch).padStart(2, '0')
    return agent(
      `You are auditing proposed names for a Dragon Quest IX decompilation. The brief used is at ` +
        `${SP}/BRIEF.md — read it, especially what a proper name is and the rules on naming the ` +
        `insides. These functions have high fan-in, so a wrong name misleads every call site. The ` +
        `proposals are in ${res.out_path}.\n\n` +
        `Check each claim against the evidence yourself: read the decompiled body with ` +
        `"git -C ${LABEL} show labeling-pass:<path>", sample the callers in ` +
        `config/${ENV.DQIX_REGION ?? "usa"}/arm9/relocs.txt across modules, and look at the game files under ` +
        `${GAME}/extract/${ENV.DQIX_REGION ?? "usa"}/files/ where a count would settle something. ` +
        `Reject a name that describes the code's shape rather than its game subject, that asserts ` +
        `more than the evidence supports, or whose comment states an inference as fact. Reject a ` +
        `field or parameter name that asserts a purpose nobody established — unknown<offset> is ` +
        `the right name for an unread field — and reject an array extent whose count is not cited. ` +
        `Suggest better_name or better_comment only when you can cite the evidence.\n\n` +
        `Check every unscoped rename for collisions: if the body spells "old" for more than one ` +
        `thing — the function's parameter and a prototype's, a member of two structs — do not ` +
        `simply reject it. Repair it with fix_renames, one entry per meaning, each carrying a ` +
        `scope of "func", "struct:Tag" or "line:<unique substring>". fix_renames replaces every ` +
        `proposed rename with that "old" spelling.\n\n` +
        `Write your verdicts as JSON to ${SP}/${OUT}/verdict${nn}.json, one entry per function:\n` +
        `[{"address": "0x…", "proposed_name": "…", "keep": true, "reason": "…", ` +
        `"better_name": null, "better_comment": null, "reject_renames": ["old", …], ` +
        `"reject_edits": ["old line", …], ` +
        `"fix_renames": [{"old": "obj", "new": "combatant", "scope": "func"}]}]\n` +
        `That output file is the only thing you may write. Never edit anything under ` +
        `${LABEL}. Then return the summary.\n\n${PATHS}`,
      { label: `audit4:batch${res.batch}`, phase: 'Audit', schema: VERDICT_SUMMARY },
    )
  },
)

return { results }
